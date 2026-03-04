import json
from typing import List
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import os
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc, func

import models, schemas, auth_utils
from database import engine, get_db
from schemas import MessageCreate, MessageRead, UserUpdate, ProductUpdate
from models import Message, User, Product, Order
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

# โหลดค่าตัวแปรจากไฟล์ .env
load_dotenv()

# ตั้งค่าการเชื่อมต่อ Cloudinary
cloudinary.config(
  cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
  api_key = os.getenv('CLOUDINARY_API_KEY'),
  api_secret = os.getenv('CLOUDINARY_API_SECRET'),
  secure = True
)

# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        # เก็บการเชื่อมต่อในรูปแบบ {user_id: websocket_connection}
        self.active_connections: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

# สั่งให้ SQLAlchemy สร้างตารางทั้งหมดในฐานข้อมูล (ถ้ายังไม่มี)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="UniShare API")

# 🟢 ตั้งค่า CORS เพื่ออนุญาตให้ Frontend (React) เรียกใช้ API นี้ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # URL ของ React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to UniShare API! 🚀"}

# --- 👤 ระบบ User & Authentication ---

# 🟢 เอา response_model ออก เพื่อให้ส่งข้อมูลแบบ Nested ได้ตามที่ Frontend ต้องการ
@app.post("/api/register")
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. เช็คอีเมลซ้ำ
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="อีเมลนี้มีในระบบแล้วครับ")
    
    # 2. เข้ารหัสผ่าน
    hashed_pwd = auth_utils.hash_password(user.password)
    
    # 3. กำหนดสถานะการเปิดใช้งาน (ศิษย์ปัจจุบันเข้าได้เลย ศิษย์เก่าต้องรออนุมัติ)
    is_active_status = True if user.account_type == 'student' else False
    
    new_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_pwd,
        uni=user.uni,
        account_type=user.account_type,
        role="user",
        is_active=is_active_status,
        verification_document=user.verification_document
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 📦 4. เตรียมก้อนข้อมูลส่งกลับให้ Frontend (React)
    response_data = {
        "user": {
            "id": new_user.id,
            "name": new_user.name,
            "email": new_user.email,
            "uni": new_user.uni,
            "role": new_user.role
        }
    }

    # 🔑 5. เฉพาะศิษย์ปัจจุบัน: สร้าง Token ส่งกลับไปเพื่อให้ Login อัตโนมัติทันที
    if new_user.is_active:
        access_token = auth_utils.create_access_token(data={"sub": new_user.email})
        response_data["access_token"] = access_token
        response_data["token_type"] = "bearer"

    return response_data

@app.post("/api/login")
def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    
    if not auth_utils.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    
    # เช็คสถานะการเปิดใช้งาน (สำหรับศิษย์เก่า)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="บัญชีของคุณอยู่ระหว่างการตรวจสอบโดยแอดมินครับ ⏳")
    
    access_token = auth_utils.create_access_token(data={"sub": user.email})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "uni": user.uni,
            "role": user.role,
            "verification_document": getattr(user, 'verification_document', None)
        }
    }

# --- 🛍️ ระบบสินค้า (Products) & คำสั่งซื้อ (Orders) ---

@app.get("/api/products", response_model=List[schemas.Product])
def get_all_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()

@app.get("/api/products/{product_id}")
async def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้ในระบบ")
    return product

@app.post("/api/products", response_model=schemas.Product)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    new_product = models.Product(
        name=product.name,
        price=product.price,
        image_url=product.image_url,
        uni=product.uni,
        condition=product.condition,
        category=product.category,
        description=product.description,
        seller_id=product.seller_id 
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return new_product

@app.post("/api/orders")
async def create_order(order_data: dict, db: Session = Depends(get_db)):
    # 1. สร้าง Order ใหม่
    new_order = models.Order(
        product_id=order_data['product_id'],
        buyer_id=order_data['buyer_id'],
        seller_id=order_data['seller_id']
    )
    db.add(new_order)
    
    # 2. อัปเดตสถานะสินค้าเป็น 'sold' (ขายแล้ว)
    product = db.query(models.Product).filter(models.Product.id == order_data['product_id']).first()
    if product:
        product.status = 'sold'
        
    db.commit()
    return {"message": "Order created successfully"}

# --- 💬 ระบบแชท (Chat) & WebSocket ---

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        
@app.post("/api/messages", response_model=MessageRead)
async def create_message(message: MessageCreate, db: Session = Depends(get_db)):
    new_message = Message(
        sender_id=message.sender_id,
        receiver_id=message.receiver_id,
        product_id=message.product_id,
        content=message.content
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    message_json = {
        "id": new_message.id,
        "sender_id": new_message.sender_id,
        "receiver_id": new_message.receiver_id,
        "content": new_message.content,
        "timestamp": str(new_message.timestamp)
    }
    await manager.send_personal_message(json.dumps(message_json), message.receiver_id)
    return new_message

@app.get("/api/messages/contacts/{user_id}")
async def get_contacts(user_id: int, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        or_(Message.sender_id == user_id, Message.receiver_id == user_id)
    ).order_by(desc(Message.timestamp)).all()

    contacts = {}
    for msg in messages:
        peer_id = msg.receiver_id if msg.sender_id == user_id else msg.sender_id
        if peer_id not in contacts:
            peer = db.query(User).filter(User.id == peer_id).first()
            if peer:
                contacts[peer_id] = {
                    "user_id": peer.id,
                    "name": peer.name,
                    "last_message": msg.content
                }
    return list(contacts.values())

@app.get("/api/messages/{user_id}/{peer_id}")
async def get_chat_history(user_id: int, peer_id: int, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == peer_id)) |
        ((Message.sender_id == peer_id) & (Message.receiver_id == user_id))
    ).order_by(Message.timestamp.asc()).all()
    return messages 

@app.put("/api/messages/read/{user_id}/{peer_id}")
async def mark_messages_as_read(user_id: int, peer_id: int, db: Session = Depends(get_db)):
    unread_messages = db.query(Message).filter(
        Message.receiver_id == user_id,
        Message.sender_id == peer_id,
        Message.is_read == False
    ).all()
    for msg in unread_messages:
        msg.is_read = True
    db.commit()
    return {"status": "success", "marked_read": len(unread_messages)}

@app.get("/api/notifications/count/{user_id}")
async def get_notifications_count(user_id: int, db: Session = Depends(get_db)):
    count = db.query(Message).filter(
        Message.receiver_id == user_id, 
        Message.is_read == False
    ).count()
    return {"unread_count": count}

# --- 🛡️ ระบบจัดการหลังบ้าน (Admin) ---

@app.get("/api/admin/stats")
async def get_admin_stats(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    product_count = db.query(Product).count()
    message_count = db.query(Message).count()
    # สถิติคำขออนุมัติศิษย์เก่า
    pending_alumni = db.query(User).filter(User.account_type == 'alumni', User.is_active == False).count()
    
    return {
        "totalUsers": user_count,
        "totalProducts": product_count,
        "totalMessages": message_count,
        "pendingAlumni": pending_alumni
    }

@app.get("/api/admin/alumni-requests")
async def get_alumni_requests(db: Session = Depends(get_db)):
    # ดึงรายชื่อศิษย์เก่าที่ยังไม่ได้รับอนุมัติ
    requests = db.query(User).filter(User.account_type == 'alumni', User.is_active == False).all()
    return requests

@app.put("/api/admin/verify-user/{user_id}")
async def verify_user(user_id: int, action: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งาน")
    
    if action == "approve":
        user.is_active = True
    elif action == "reject":
        db.delete(user)
        
    db.commit()
    return {"message": f"บัญชีถูก {action} เรียบร้อยแล้ว"}

# 1. เช็คและสร้างโฟลเดอร์ static/uploads ไว้เก็บรูปภาพ
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 2. ตั้งค่าให้ FastAPI ปล่อยไฟล์ Static ออกไปให้ Frontend เรียกดูรูปได้
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3. สร้าง API รับไฟล์
# 🟢 API รับไฟล์และอัปโหลดขึ้น Cloudinary
@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    try:
        # 1. อ่านข้อมูลไฟล์ภาพที่ส่งมาจาก Frontend
        contents = await file.read()
        
        # 2. อัปโหลดขึ้น Cloudinary (ตั้งชื่อโฟลเดอร์ว่า unishare_uploads)
        upload_result = cloudinary.uploader.upload(
            contents, 
            folder="unishare_uploads"
        )
        
        # 3. ดึง URL ของรูปภาพที่อัปโหลดเสร็จแล้ว
        file_url = upload_result.get("secure_url")
        
        # 4. ส่ง URL กลับไปให้ React นำไปบันทึกลงฐานข้อมูล
        return {"url": file_url}
        
    except Exception as e:
        return {"error": str(e)}

# หมายเหตุ: คุณสามารถลบโค้ดส่วน os.makedirs(UPLOAD_DIR, exist_ok=True) 
# และส่วน shutil ตัวเก่าทิ้งไปได้เลยครับ เพราะเราไม่ได้เก็บรูปลงโฟลเดอร์ static ในเครื่องแล้ว
    
@app.put("/api/users/{user_id}")
async def update_user_profile(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    try:
        # 1. ค้นหา User จาก Database
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้งานนี้ในระบบ")
            
        # 2. อัปเดตชื่อผู้ใช้
        user.name = user_update.name
        
        # 3. ยืนยันการบันทึกลง Database
        db.commit()
        db.refresh(user) 
        
        return {"message": "Profile updated successfully", "new_name": user.name}
        
    except Exception as e:
        db.rollback() # ป้องกัน Database ค้างกรณีเกิด Error
        return {"error": str(e)}
    
@app.put("/api/products/{product_id}")
async def update_product(product_id: int, product_update: ProductUpdate, db: Session = Depends(get_db)):
    try:
        # ค้นหาสินค้าที่ต้องการแก้ไข
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้ในระบบ")

        # อัปเดตข้อมูลเฉพาะส่วนที่มีการส่งมา
        if product_update.name is not None:
            product.name = product_update.name
        if product_update.price is not None:
            product.price = product_update.price
        if product_update.condition is not None:
            product.condition = product_update.condition
        if product_update.category is not None:
            product.category = product_update.category
        if product_update.description is not None:
            product.description = product_update.description

        # บันทึกลง Database
        db.commit()
        db.refresh(product)
        return {"message": "Product updated successfully"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    
@app.put("/api/products/{product_id}/sold")
async def mark_product_as_sold(product_id: int, db: Session = Depends(get_db)):
    try:
        # 1. ค้นหาสินค้าจาก Database
        product = db.query(Product).filter(Product.id == product_id).first()
        
        if not product:
            raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้ในระบบ")
            
        # 2. เปลี่ยนสถานะเป็น sold
        product.status = 'sold'
        
        # 3. บันทึกลง Database
        db.commit()
        db.refresh(product)
        
        return {"message": "Product marked as sold successfully"}
        
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    
# 🟢 API ดึงประวัติการสั่งซื้อของ User
@app.get("/api/orders/user/{user_id}")
async def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    try:
        # 1. ค้นหา Order ทั้งหมดที่ผู้ใช้คนนี้เป็นคนซื้อ (buyer_id) เรียงจากล่าสุด
        orders = db.query(models.Order).filter(models.Order.buyer_id == user_id).order_by(models.Order.id.desc()).all()
        
        result = []
        for order in orders:
            # 2. ดึงข้อมูลสินค้า (Product) ที่เกี่ยวข้องกับออเดอร์นี้มาด้วย
            product = db.query(models.Product).filter(models.Product.id == order.product_id).first()
            
            # 3. ประกอบร่างข้อมูลส่งกลับให้ Frontend
            order_info = {
                "id": order.id,
                "product_id": order.product_id,
                "buyer_id": order.buyer_id,
                "seller_id": order.seller_id,
                # ป้องกัน Error กรณี Database บางคนไม่มีคอลัมน์ status หรือ created_at
                "status": getattr(order, 'status', 'completed'), 
                "created_at": str(getattr(order, 'created_at', '2024-01-01')) 
            }
            
            if product:
                order_info["product"] = {
                    "id": product.id,
                    "name": product.name,
                    "price": product.price,
                    "imageUrl": product.image_url,
                    "uni": product.uni
                }
                
            result.append(order_info)
            
        return result
    except Exception as e:
        return {"error": str(e)}