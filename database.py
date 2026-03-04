from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 🟢 นำ Connection String ที่ได้จาก Neon.tech (หรือ DB ของคุณ) มาใส่ตรงนี้
SQLALCHEMY_DATABASE_URL = "postgresql://neondb_owner:npg_8M5FXqQirkOn@ep-proud-cloud-a15hbgze-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # 👈 ให้ SQLAlchemy เช็กก่อนว่า DB ยังต่อติดไหม ถ้าหลุดจะต่อให้ใหม่
    pool_recycle=300     # 👈 รีเฟรช Connection ทุกๆ 5 นาที (300 วินาที) ป้องกัน Neon ตัดสาย
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()