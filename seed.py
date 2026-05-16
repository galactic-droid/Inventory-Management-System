import datetime
from database import SessionLocal, engine, Base
from models.product import Location, Product, InventoryLog, StockBatch, StockPlacement
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

        soguk_hava = Location(name="Soğuk Hava Bölgesi", location_type="ZONE", parent_id=ana_depo.id, is_cold_chain=True, category="Soğuk Zincir")
        kuru_gida = Location(name="Kuru Gıda Bölgesi", location_type="ZONE", parent_id=ana_depo.id, is_cold_chain=False, category="Kuru Gıda")
        teknoloji = Location(name="Teknoloji Bölgesi", location_type="ZONE", parent_id=ana_depo.id, is_cold_chain=False, category="Teknoloji")
        mobilya = Location(name="Mobilya Bölgesi", location_type="ZONE", parent_id=ana_depo.id, is_cold_chain=False, category="Mobilya")
        db.add_all([soguk_hava, kuru_gida, teknoloji, mobilya])
        db.commit()

        koridor_1 = Location(name="Koridor 1 (Soğuk)", location_type="AISLE", parent_id=soguk_hava.id, is_cold_chain=True, category="Soğuk Zincir")
        koridor_2 = Location(name="Koridor 2 (Kuru Gıda)", location_type="AISLE", parent_id=kuru_gida.id, is_cold_chain=False, category="Kuru Gıda")
        koridor_3 = Location(name="Koridor 3 (Elektronik)", location_type="AISLE", parent_id=teknoloji.id, is_cold_chain=False, category="Teknoloji")
        koridor_4 = Location(name="Koridor 4 (Mobilya)", location_type="AISLE", parent_id=mobilya.id, is_cold_chain=False, category="Mobilya")
        db.add_all([koridor_1, koridor_2, koridor_3, koridor_4])
        db.commit()

        raf_a = Location(name="Raf A (Soğuk)", location_type="RACK", parent_id=koridor_1.id, is_cold_chain=True, category="Soğuk Zincir")
        raf_b = Location(name="Raf B", location_type="RACK", parent_id=koridor_2.id, is_cold_chain=False, category="Kuru Gıda")
        raf_c = Location(name="Raf C", location_type="RACK", parent_id=koridor_3.id, is_cold_chain=False, category="Teknoloji")
        raf_d = Location(name="Raf D", location_type="RACK", parent_id=koridor_4.id, is_cold_chain=False, category="Mobilya")
        db.add_all([raf_a, raf_b, raf_c, raf_d])
        db.commit()

        # Raf Gözleri (Leaf Nodes - Kapasiteli olan en alt seviyeler)
        goz_a1 = Location(name="Göz A1 (Soğuk)", location_type="BIN", parent_id=raf_a.id, max_volume_m3=15.0, max_weight_kg=2000.0, is_cold_chain=True, category="Soğuk Zincir")
        goz_a2 = Location(name="Göz A2 (Soğuk)", location_type="BIN", parent_id=raf_a.id, max_volume_m3=15.0, max_weight_kg=2000.0, is_cold_chain=True, category="Soğuk Zincir")
        goz_b1 = Location(name="Göz B1", location_type="BIN", parent_id=raf_b.id, max_volume_m3=20.0, max_weight_kg=3000.0, is_cold_chain=False, category="Kuru Gıda")
        goz_c1 = Location(name="Göz C1", location_type="BIN", parent_id=raf_c.id, max_volume_m3=20.0, max_weight_kg=1500.0, is_cold_chain=False, category="Teknoloji")
        goz_d1 = Location(name="Göz D1", location_type="BIN", parent_id=raf_d.id, max_volume_m3=50.0, max_weight_kg=4000.0, is_cold_chain=False, category="Mobilya")
        db.add_all([goz_a1, goz_a2, goz_b1, goz_c1, goz_d1])
        db.commit()

        print("📦 Örnek (Dummy) Ürünler oluşturuluyor...")
        
        skt_kisa = datetime.date.today() + datetime.timedelta(days=12)
        skt_uzun = datetime.date.today() + datetime.timedelta(days=180)

        products_data = [
            # Soğuk Zincir Ürünleri
            Product(name="Tam Yağlı Süt", stock_quantity=400, initial_expected_daily_consumption=40, estimated_daily_consumption=40, lead_time_days=2, size_m3=0.001, weight_kg=1.05, category="Soğuk Zincir", supplier_name="Sütçü A.Ş.", supplier_email="siparis@sutcu.com", has_expiry_tracking=True, is_cold_chain=True),
            Product(name="Taze Dana Kıyma", stock_quantity=120, initial_expected_daily_consumption=15, estimated_daily_consumption=15, lead_time_days=2, size_m3=0.003, weight_kg=1.0, category="Soğuk Zincir", supplier_name="Et ve Et Ürünleri A.Ş.", supplier_email="et@kasap.com", has_expiry_tracking=True, is_cold_chain=True),
            # Kuru Gıda
            Product(name="Baldo Pirinç", stock_quantity=800, initial_expected_daily_consumption=50, estimated_daily_consumption=50, lead_time_days=5, size_m3=0.0015, weight_kg=1.0, category="Kuru Gıda", supplier_name="Bakliyat Ltd.", supplier_email="depo@bakliyat.com", has_expiry_tracking=True, is_cold_chain=False),
            # Teknoloji
            Product(name="Laptop", stock_quantity=45, initial_expected_daily_consumption=2, estimated_daily_consumption=2, lead_time_days=7, size_m3=0.02, weight_kg=3.5, category="Teknoloji", supplier_name="Bilişim A.Ş.", supplier_email="satis@bilisim.com", has_expiry_tracking=False, is_cold_chain=False),
            Product(name="Telefon", stock_quantity=15, initial_expected_daily_consumption=3, estimated_daily_consumption=3, lead_time_days=5, size_m3=0.005, weight_kg=0.4, category="Teknoloji", supplier_name="Bilişim A.Ş.", supplier_email="satis@bilisim.com", has_expiry_tracking=False, is_cold_chain=False), # Kritik stok (15 stok, bitiş 5 gün, tedarik 5 gün)
            # Mobilya
            Product(name="Ofis Koltuğu", stock_quantity=60, initial_expected_daily_consumption=5, estimated_daily_consumption=5, lead_time_days=10, size_m3=0.15, weight_kg=12.0, category="Mobilya", supplier_name="Mobilya Dünyası", supplier_email="info@mobilyadunyasi.com", has_expiry_tracking=False, is_cold_chain=False),
            Product(name="Ahşap Çalışma Masası", stock_quantity=30, initial_expected_daily_consumption=2, estimated_daily_consumption=2, lead_time_days=14, size_m3=0.4, weight_kg=25.0, category="Mobilya", supplier_name="Mobilya Dünyası", supplier_email="info@mobilyadunyasi.com", has_expiry_tracking=False, is_cold_chain=False)
        ]
        
        for p in products_data:
            db.add(p)
            db.commit()
            db.refresh(p)
            
            # SKT'si olanlara batch ekle
            if p.has_expiry_tracking:
                expiry = skt_kisa if "Süt" in p.name or "Kıyma" in p.name else skt_uzun
                db.add(StockBatch(product_id=p.id, quantity=p.stock_quantity, expiry_date=expiry))
                db.commit()
                
            db.add(InventoryLog(product_id=p.id, action_type="YENİ ÜRÜN", description="Sistem test verisi (dummy) olarak eklendi."))
            db.commit()

        print("⚙️ Ürünler kategorilerine (Soğuk, Kuru Gıda, Teknoloji, Mobilya) göre mantıksal raflara yerleştiriliyor...")
        # Rastgele dağılmasını önlemek için ürünleri test verisindeki ait oldukları raflara sabitliyoruz.
        placements = [
            StockPlacement(product_id=products_data[0].id, location_id=goz_a1.id, quantity=products_data[0].stock_quantity), # Süt -> Soğuk
            StockPlacement(product_id=products_data[1].id, location_id=goz_a2.id, quantity=products_data[1].stock_quantity), # Kıyma -> Soğuk
            StockPlacement(product_id=products_data[2].id, location_id=goz_b1.id, quantity=products_data[2].stock_quantity), # Pirinç -> Kuru Gıda
            StockPlacement(product_id=products_data[3].id, location_id=goz_c1.id, quantity=products_data[3].stock_quantity), # Laptop -> Teknoloji
            StockPlacement(product_id=products_data[4].id, location_id=goz_c1.id, quantity=products_data[4].stock_quantity), # Telefon -> Teknoloji
            StockPlacement(product_id=products_data[5].id, location_id=goz_d1.id, quantity=products_data[5].stock_quantity), # Koltuk -> Mobilya
            StockPlacement(product_id=products_data[6].id, location_id=goz_d1.id, quantity=products_data[6].stock_quantity)  # Masa -> Mobilya
        ]
        db.add_all(placements)
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