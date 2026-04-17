import datetime
from database import SessionLocal, engine, Base
from models.product import Location, Product, InventoryLog
from services.rebalancing_service import rebalance_warehouse

def reset_and_seed_database():
    print("⏳ Veritabanı sıfırlanıyor (Tüm eski veriler silinecek)...")
    # Tüm tabloları sil ve yeniden oluştur
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        print("🏢 Hiyerarşik Lokasyonlar (Depo Ağacı) oluşturuluyor...")
        
        ana_depo = Location(name="Ana Merkez Depo", location_type="WAREHOUSE")
        db.add(ana_depo)
        db.commit()

        soguk_hava = Location(name="Soğuk Hava Bölgesi", location_type="ZONE", parent_id=ana_depo.id)
        kuru_gida = Location(name="Kuru Gıda Bölgesi", location_type="ZONE", parent_id=ana_depo.id)
        db.add_all([soguk_hava, kuru_gida])
        db.commit()

        koridor_1 = Location(name="Koridor 1 (Süt Ürünleri)", location_type="AISLE", parent_id=soguk_hava.id)
        koridor_2 = Location(name="Koridor 2 (Bakliyat)", location_type="AISLE", parent_id=kuru_gida.id)
        db.add_all([koridor_1, koridor_2])
        db.commit()

        raf_a = Location(name="Raf A", location_type="RACK", parent_id=koridor_1.id)
        raf_b = Location(name="Raf B", location_type="RACK", parent_id=koridor_2.id)
        db.add_all([raf_a, raf_b])
        db.commit()

        # Raf Gözleri (Leaf Nodes - Kapasiteli olan en alt seviyeler)
        goz_a1 = Location(name="Göz A1", location_type="BIN", parent_id=raf_a.id, max_volume_m3=5.0, max_weight_kg=1000.0)
        goz_a2 = Location(name="Göz A2", location_type="BIN", parent_id=raf_a.id, max_volume_m3=5.0, max_weight_kg=1000.0)
        goz_b1 = Location(name="Göz B1", location_type="BIN", parent_id=raf_b.id, max_volume_m3=10.0, max_weight_kg=2000.0)
        db.add_all([goz_a1, goz_a2, goz_b1])
        db.commit()

        print("📦 Örnek (Dummy) Ürünler oluşturuluyor...")
        products_data = [
            Product(name="Tam Yağlı Süt 1L", stock_quantity=400, initial_expected_daily_consumption=40, estimated_daily_consumption=40, lead_time_days=2, size_m3=0.001, weight_kg=1.05, supplier_name="Sütçü A.Ş.", has_expiry_tracking=True),
            Product(name="Kaşar Peyniri 500g", stock_quantity=150, initial_expected_daily_consumption=15, estimated_daily_consumption=15, lead_time_days=3, size_m3=0.002, weight_kg=0.5, supplier_name="Sütçü A.Ş.", has_expiry_tracking=True),
            Product(name="Baldo Pirinç 1kg", stock_quantity=800, initial_expected_daily_consumption=50, estimated_daily_consumption=50, lead_time_days=5, size_m3=0.0015, weight_kg=1.0, supplier_name="Bakliyat Ltd.", has_expiry_tracking=False),
            Product(name="Burgu Makarna 500g", stock_quantity=60, initial_expected_daily_consumption=20, estimated_daily_consumption=20, lead_time_days=4, size_m3=0.002, weight_kg=0.5, supplier_name="Bakliyat Ltd.", has_expiry_tracking=False) # Kritik stok durumu yaratmak için az eklendi
        ]
        
        for p in products_data:
            db.add(p)
            db.commit()
            db.refresh(p)
            db.add(InventoryLog(product_id=p.id, action_type="YENİ ÜRÜN", description="Sistem test verisi (dummy) olarak eklendi."))
            db.commit()

        print("⚙️ Ürünler uygun kapasitelere göre raflara yerleştiriliyor...")
        rebalance_warehouse(db)
        db.commit()

        print("\n✅ İŞLEM BAŞARILI!")
        print("Tüm veritabanı sıfırlandı ve test verileri yüklendi.")
        print("Şimdi sunucuyu çalıştırıp arayüzü kontrol edebilirsiniz.")

    except Exception as e:
        print(f"\n❌ Bir hata oluştu: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset_and_seed_database()