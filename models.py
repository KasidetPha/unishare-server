from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float
from sqlalchemy.sql import func
from database import Base
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# 🟢 เหลือ User แค่ตัวเดียว (ที่มี hashed_password) และลบฟิลด์ที่ประกาศซ้ำออก
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    uni = Column(String)
    role = Column(String, default="user")
    
    # ฟิลด์สำหรับจัดการศิษย์เก่า
    account_type = Column(String, default="student") 
    verification_document = Column(String, nullable=True) 
    is_active = Column(Boolean, default=True) # สถานะเอาไว้ให้ Admin กดอนุมัติ
    
class UserCreate(BaseModel):
    name: str
    email: str # หรือใช้ EmailStr ถ้ามีการ import จาก pydantic
    password: str
    uni: str
    
    # 🟢 เพิ่มตัวแปรให้ตรงกับที่ React ส่งมา
    account_type: str = "student"
    verification_document: Optional[str] = None

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    image_url = Column(String)
    uni = Column(String)
    condition = Column(String)
    category = Column(String)
    description = Column(String, nullable=True)
    seller_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="available") # available, reserved, sold
    
class MessageCreate(BaseModel):
    sender_id: int
    receiver_id: int
    product_id: Optional[int] = None
    content: str

class MessageRead(MessageCreate):
    id: int
    timestamp: datetime
    is_read: bool

    class Config:
        from_attributes = True
        
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    is_read = Column(Boolean, default=False)
    
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    buyer_id = Column(Integer, ForeignKey("users.id"))
    seller_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending") # pending, completed, cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())