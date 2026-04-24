from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Veritabanının tutulacağı klasörü oluştur (Docker çakışmalarını önler)
os.makedirs("./data", exist_ok=True)

# SQLite veritabanı dosyamızın adı ve yeni yolu
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/envanter.db"

# Veritabanı motorunu oluşturuyoruz
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()