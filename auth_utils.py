import bcrypt
import jwt
from datetime import datetime, timedelta

# ตั้งค่าสำหรับ JWT
SECRET_KEY = "unishare_super_secret_key" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 1 วัน

# 1. ฟังก์ชันสำหรับเข้ารหัสผ่าน
def hash_password(password: str):
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

# 2. ฟังก์ชันสำหรับตรวจสอบรหัสผ่าน (ที่หายไป!)
def verify_password(plain_password: str, hashed_password: str):
    password_byte = plain_password.encode('utf-8')
    hashed_byte = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte, hashed_byte)

# 3. ฟังก์ชันสำหรับสร้าง Token
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt