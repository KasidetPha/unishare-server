from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# --- User Schemas ---
class UserBase(BaseModel):
    name: str
    email: EmailStr
    uni: str
    account_type: str # student หรือ alumni
    verification_document: Optional[str] = None

class UserCreate(UserBase):
    password: str # รับรหัสผ่านตอนสมัครสมาชิก

class User(UserBase):
    id: int
    role: str
    is_active: bool
    verification_document: Optional[str] = None #

    class Config:
        from_attributes = True

# --- Product Schemas ---
class ProductBase(BaseModel):
    name: str
    price: float
    image_url: str
    uni: str
    condition: str
    category: str
    description: Optional[str] = None

class ProductCreate(ProductBase):
    seller_id: int

class Product(ProductBase):
    id: int
    status: str
    seller_id: int

    class Config:
        from_attributes = True
        
class UserLogin(BaseModel):
    email: EmailStr
    password: str
    
# 🟢 เพิ่ม Schema สำหรับระบบ Chat
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
        
class UserUpdate(BaseModel):
    name: str
    
class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    condition: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None