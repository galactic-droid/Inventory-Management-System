from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Date
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Location(Base):
    """Çok Seviyeli Depo Hiyerarşisi (Örn: Depo -> Bölge -> Koridor -> Raf Ünitesi -> Göz)"""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True) # Örn: "Ana Depo", "Koridor 1", "Hücre-A1"
    location_type = Column(String) # Örn: "WAREHOUSE", "ZONE", "AISLE", "RACK", "BIN"
    
    # Kendi kendini referans alan yapı (Hiyerarşi için ebeveyn ID)
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    
    # Sadece en alt seviyedeki (Leaf Node) lokasyonlar için kapasite kullanılır
    max_volume_m3 = Column(Float, default=0.0)
    max_weight_kg = Column(Float, default=0.0)

    sub_locations = relationship("Location", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("Location", back_populates="sub_locations", remote_side=[id])
    placements = relationship("StockPlacement", back_populates="location", cascade="all, delete-orphan")

class StockPlacement(Base):
    """Bir ürünün hangi rafta ne kadar durduğunu belirten yerleşim kaydı."""
    __tablename__ = "stock_placements"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    location_id = Column(Integer, ForeignKey("locations.id"))
    quantity = Column(Integer, default=0)

    product = relationship("Product", back_populates="placements")
    location = relationship("Location", back_populates="placements")
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    stock_quantity = Column(Integer)
    # Bu alan artık kullanıcı tarafından girilmeyecek, satışlara göre hesaplanacak.
    estimated_daily_consumption = Column(Float, default=0.0)
    lead_time_days = Column(Integer)
    # Bir ürün silindiğinde, ona ait tüm satış loglarının da silinmesini sağlıyoruz.
    sale_logs = relationship("SaleLog", back_populates="product", cascade="all, delete-orphan")
    # Ürüne ait tüm stok/raf değişiklik logları
    inventory_logs = relationship("InventoryLog", back_populates="product", cascade="all, delete-orphan")
    # Ürüne ait SKT Partileri (Batch)
    batches = relationship("StockBatch", back_populates="product", cascade="all, delete-orphan")
    # Ürünün raflardaki yerleşimleri
    placements = relationship("StockPlacement", back_populates="product", cascade="all, delete-orphan")
    # Yeni eklenen alanlar
    creation_date = Column(DateTime, default=datetime.datetime.utcnow)
    initial_expected_daily_consumption = Column(Float, default=0.0) # Kullanıcının ilk hafta için girdiği beklenti
    
    size_m3 = Column(Float, default=0.0) # Ürün boyutu (m3 vb.)
    items_per_pallet = Column(Integer, default=0) # Bir paletteki ürün sayısı
    weight_kg = Column(Float, default=0.0) # Ürün ağırlığı (kg)    
    
    has_expiry_tracking = Column(Boolean, default=False) # Bu ürün için SKT takibi yapılıyor mu?
    supplier_name = Column(String, default="") # Tedarikçi Firma Adı
    supplier_email = Column(String, default="") # Tedarikçi E-posta Adresi

class SaleLog(Base):
    """Yapılan her satışı kaydeden tablo."""
    __tablename__ = "sale_logs"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)
    sale_date = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="sale_logs")

class InventoryLog(Base):
    """Ürün üzerindeki stok ve raf değişikliklerini takip eden log tablosu."""
    __tablename__ = "inventory_logs"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    action_type = Column(String) # 'YENİ ÜRÜN', 'STOK GİRİŞİ', 'STOK ÇIKIŞI' vs.
    description = Column(String) # Detaylı açıklama (Raf değişti, stok eklendi vb.)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="inventory_logs")

class StockBatch(Base):
    """Aynı ürünün farklı SKT tarihlerine sahip partilerini (batch) tutan tablo."""
    __tablename__ = "stock_batches"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, default=0)
    expiry_date = Column(Date, nullable=True)
    
    product = relationship("Product", back_populates="batches")