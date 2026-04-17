from pydantic import BaseModel, Field, AliasChoices
from datetime import datetime, date

# Kullanıcıdan ürün eklerken isteyeceğimiz bilgiler
class ProductCreate(BaseModel):
    name: str
    stock_quantity: int
    # Tahmini tüketim artık kullanıcıdan alınmıyor, sistem tarafından hesaplanıyor.
    lead_time_days: int
    # Yeni ürünler için "soğuk başlangıç" sorununu çözmek adına kullanıcıdan bir başlangıç değeri alıyoruz.
    beklenen_gunluk_satis: float = Field(
        default=0.0, 
        validation_alias=AliasChoices('beklenen_gunluk_satis', 'estimated_daily_consumption', 'daily_burn_rate')
    )
    size_m3: float = 0.0
    items_per_pallet: int = 0
    weight_kg: float = 0.0
    has_expiry_tracking: bool = False
    expiry_date: date | None = None
    supplier_name: str = ""
    supplier_email: str = ""

# Kullanıcıya cevap olarak döneceğimiz bilgiler (id dahil)
class ProductResponse(ProductCreate):
    id: int
    estimated_daily_consumption: float # Hesaplanan değeri cevapta göstermek için ekliyoruz.    

    class Config:
        from_attributes = True
    
class ProductDispatch(BaseModel):
    quantity: int

class ProductAddStock(BaseModel):
    quantity: int
    expiry_date: date | None = None

class InventoryLogResponse(BaseModel):
    id: int
    action_type: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- ÇOK SEVİYELİ DEPO HİYERARŞİSİ ŞEMALARI ---
class LocationBase(BaseModel):
    name: str
    location_type: str
    parent_id: int | None = None
    max_volume_m3: float = 0.0
    max_weight_kg: float = 0.0

class LocationCreate(LocationBase):
    pass

class Location(LocationBase):
    id: int
    class Config:
        from_attributes = True

class LocationResponse(Location):
    sub_locations: list['LocationResponse'] = []
    class Config:
        from_attributes = True