from fastapi import FastAPI, Depends, Request, HTTPException, UploadFile, File, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from database import engine, Base, SessionLocal
import models.product
import schemas.product_schema as schemas
import services.rebalancing_service as rebalancing_service
import services.inventory_service as inventory_service
import csv
import io
import math
from datetime import datetime, timedelta

# Veritabanı tablolarını oluştur
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Envanter Sistemi")

# HTML şablonlarımızın yerini belirtiyoruz
templates = Jinja2Templates(directory="templates")

# Veritabanı oturumu
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"mesaj": "Sistem Çalışıyor!"}

@app.post("/products/", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, db: Session = Depends(get_db)):
    # Aynı isimde bir ürün var mı diye veritabanını kontrol et
    # Aynı isim ve aynı tedarikçiye sahip bir ürün var mı?
    existing_product = db.query(models.product.Product).filter(
        models.product.Product.name == product.name,
        models.product.Product.supplier_name == product.supplier_name
    ).first()
    if existing_product:
        # Eğer ürün varsa, yeni gelen verilerle alanlarını güncelle
        existing_product.stock_quantity += product.stock_quantity
        existing_product.lead_time_days = product.lead_time_days
        
        # SIKINTI ÇÖZÜLDÜ: Eğer formdan tüketim beklentisi değiştirilirse, Soğuk Başlangıcı SIFIRLA!
        if existing_product.initial_expected_daily_consumption != product.beklenen_gunluk_satis:
            existing_product.initial_expected_daily_consumption = product.beklenen_gunluk_satis
            existing_product.creation_date = datetime.utcnow()
            
        existing_product.size_m3 = product.size_m3
        existing_product.items_per_pallet = product.items_per_pallet
        existing_product.weight_kg = product.weight_kg
        existing_product.has_expiry_tracking = product.has_expiry_tracking
        existing_product.supplier_name = product.supplier_name
        existing_product.supplier_email = product.supplier_email
        
        # HATA DÜZELTİLDİ: Değeri körü körüne ezmek yerine, servisin gerçek satışlara 
        # veya beklentiye bakarak doğru değeri (Soğuk Başlangıç mantığıyla) hesaplamasını sağlıyoruz.
        inventory_service.update_daily_consumption(existing_product, db)
        inventory_service.manage_placements(existing_product, db)
        
        log_desc = f"{product.stock_quantity} adet stok eklendi. Yeni stok: {existing_product.stock_quantity}. "
        new_log = models.product.InventoryLog(product_id=existing_product.id, action_type="STOK GİRİŞİ (GÜNCELLEME)", description=log_desc)
        db.add(new_log)
        
        # Eğer SKT takibi varsa partiye ekle
        if product.has_expiry_tracking and product.stock_quantity > 0:
            existing_batch = db.query(models.product.StockBatch).filter(
                models.product.StockBatch.product_id == existing_product.id, models.product.StockBatch.expiry_date == product.expiry_date
            ).first()
            if existing_batch:
                existing_batch.quantity += product.stock_quantity
            else:
                db.add(models.product.StockBatch(product_id=existing_product.id, quantity=product.stock_quantity, expiry_date=product.expiry_date))

        db.commit()
        db.refresh(existing_product)
        # Terminale sarı renkli güncelleme logu (stok ekleme durumunu belirtir)
        print(f"\033[93m[GÜNCELLEME]\033[0m '{existing_product.name}' ürününe {product.stock_quantity} adet eklendi. Yeni Stok: {existing_product.stock_quantity}. Yeni Tüketim Tahmini: {existing_product.estimated_daily_consumption:.2f}/gün")
        return existing_product
    else:
        # Eğer ürün yoksa, yeni bir tane oluştur
        new_product = models.product.Product(
            name=product.name,
            stock_quantity=product.stock_quantity,
            lead_time_days=product.lead_time_days,
            initial_expected_daily_consumption=product.beklenen_gunluk_satis,
            estimated_daily_consumption=product.beklenen_gunluk_satis, # Başlangıç tüketimi, beklenen değerdir
            size_m3=product.size_m3,
            items_per_pallet=product.items_per_pallet,
            weight_kg=product.weight_kg,
            has_expiry_tracking=product.has_expiry_tracking,
            supplier_name=product.supplier_name,
            supplier_email=product.supplier_email
        )
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        
        # Yeni ürün eklendiği için depoyu yeniden dengele
        change_log = rebalancing_service.rebalance_warehouse(db)
        db.commit()
        
        # Yeni ürün partisini oluştur
        if product.has_expiry_tracking and product.stock_quantity > 0:
            db.add(models.product.StockBatch(product_id=new_product.id, quantity=product.stock_quantity, expiry_date=product.expiry_date))
            db.commit()
        
        new_log = models.product.InventoryLog(product_id=new_product.id, action_type="YENİ ÜRÜN", description=f"Ürün sisteme {new_product.stock_quantity} stokla eklendi.")
        db.add(new_log)
        db.commit()
        
        # Terminale yeşil renkli yeni ürün logu
        print(f"\033[92m[YENİ ÜRÜN]\033[0m '{new_product.name}' eklendi. Depo yeniden denetlendi.")
        return {"product": new_product, "rebalance_log": change_log}

@app.get("/products/{product_id}/status")
def check_stock_status(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.product.Product).filter(models.product.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return inventory_service.calculate_stock_status(product)

@app.post("/products/{product_id}/dispatch")
def dispatch_stock(product_id: int, data: schemas.ProductDispatch, db: Session = Depends(get_db)):
    product = db.query(models.product.Product).filter(models.product.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
        
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Çıkış yapılacak miktar 0'dan büyük olmalıdır.")

    if product.stock_quantity < data.quantity:
        raise HTTPException(status_code=400, detail="Yetersiz stok! O kadar ürünümüz yok.")
        
    # Mevcut dolu raf sayısını al
    occupied_location_ids_before = {p.location_id for p in db.query(models.product.StockPlacement.location_id).distinct()}

    product.stock_quantity -= data.quantity
    
    if getattr(product, 'has_expiry_tracking', False):
        remaining_to_dispatch = data.quantity
        batches = db.query(models.product.StockBatch).filter(
            models.product.StockBatch.product_id == product.id, models.product.StockBatch.quantity > 0
        ).order_by(models.product.StockBatch.expiry_date.asc()).all()
        
        for batch in batches:
            if remaining_to_dispatch <= 0: break
            if batch.quantity <= remaining_to_dispatch:
                remaining_to_dispatch -= batch.quantity
                db.delete(batch)
            else:
                batch.quantity -= remaining_to_dispatch
                remaining_to_dispatch = 0
                
    new_sale_log = models.product.SaleLog(
        product_id=product_id,
        quantity=data.quantity
    )
    db.add(new_sale_log)
    
    inventory_service.update_daily_consumption(product, db)
    inventory_service.manage_placements(product, db)
    
    # Yerleşimler güncellendikten sonra dolu raf sayısını tekrar al
    occupied_location_ids_after = {p.location_id for p in db.query(models.product.StockPlacement.location_id).distinct()}
    
    rebalance_log = None
    if len(occupied_location_ids_after) < len(occupied_location_ids_before):
        print("Bir lokasyon boşaldı, depo yeniden denetlenecek.")
        rebalance_log = rebalancing_service.rebalance_warehouse(db)

    log_desc = f"{data.quantity} adet stok çıkışı yapıldı. Kalan stok: {product.stock_quantity}."
    new_log = models.product.InventoryLog(product_id=product.id, action_type="STOK ÇIKIŞI", description=log_desc)
    db.add(new_log)
    
    db.commit()
    
    print(f"\033[96m[SATIŞ]\033[0m '{product.name}' ürününden {data.quantity} adet satıldı! Kalan: {product.stock_quantity}, Yeni Hız: {product.estimated_daily_consumption:.2f}/gün")
    
    return {"mesaj": "Stok başarıyla güncellendi.", "rebalance_log": rebalance_log}

# --- STOK EKLEME ENDPOINT'İ ---
@app.post("/products/{product_id}/add_stock")
def add_stock(product_id: int, data: schemas.ProductAddStock, db: Session = Depends(get_db)):
    product = db.query(models.product.Product).filter(models.product.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Eklenecek miktar 0'dan büyük olmalıdır.")

    # Eğer SKT takibi varsa yeni gelen stoğu doğru partiye (Batch) ekle
    if getattr(product, 'has_expiry_tracking', False):
        if not data.expiry_date:
            raise HTTPException(status_code=400, detail="Bu ürün için SKT takibi aktiftir, lütfen bir SKT tarihi seçin.")
        existing_batch = db.query(models.product.StockBatch).filter(
            models.product.StockBatch.product_id == product.id, models.product.StockBatch.expiry_date == data.expiry_date
        ).first()
        if existing_batch:
            existing_batch.quantity += data.quantity
        else:
            db.add(models.product.StockBatch(product_id=product.id, quantity=data.quantity, expiry_date=data.expiry_date))
            
    product.stock_quantity += data.quantity
    inventory_service.manage_placements(product, db) # Stok eklendiği için yerleşimleri güncelle
    
    log_desc = f"{data.quantity} adet stok girişi yapıldı. Yeni stok: {product.stock_quantity}. "
    new_log = models.product.InventoryLog(product_id=product.id, action_type="STOK GİRİŞİ", description=log_desc)
    db.add(new_log)
    db.commit()
    db.refresh(product)

    # Terminale mavi renkli stok ekleme logu
    print(f"\033[94m[STOK EKLENDİ]\033[0m '{product.name}' ürününe {data.quantity} adet eklendi. Yeni Stok: {product.stock_quantity}")
    return {"mesaj": "Stok başarıyla güncellendi."}

# --- ÜRÜN SİLME ENDPOINT'İ ---
@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.product.Product).filter(models.product.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    
    product_name = product.name
    # Ürün silinmeden önce dolu olan rafları bul
    occupied_location_ids_before = {p.location_id for p in db.query(models.product.StockPlacement.location_id).distinct()}

    db.delete(product)
    db.flush() # Silme işlemini veritabanı oturumuna yansıt

    # Ürün silindikten sonra dolu olan rafları tekrar bul
    occupied_location_ids_after = {p.location_id for p in db.query(models.product.StockPlacement.location_id).distinct()}

    rebalance_log = None
    if len(occupied_location_ids_after) < len(occupied_location_ids_before):
        print("Bir ürün silindi ve lokasyon boşaldı, depo yeniden denetlenecek.")
        rebalance_log = rebalancing_service.rebalance_warehouse(db)

    db.commit()
    
    print(f"\033[91m[SİLİNDİ]\033[0m '{product_name}' adlı ürün ve tüm satış geçmişi sistemden silindi.")
    return {"mesaj": "Ürün başarıyla silindi.", "rebalance_log": rebalance_log}

# --- GEÇMİŞ (LOG) ENDPOINT'İ ---
@app.get("/products/{product_id}/logs", response_model=list[schemas.InventoryLogResponse])
def get_product_logs(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.product.Product).filter(models.product.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    logs = db.query(models.product.InventoryLog).filter(models.product.InventoryLog.product_id == product_id).order_by(models.product.InventoryLog.created_at.desc()).all()
    return logs

# --- SATIŞ TRENDİ GRAFİĞİ ENDPOINT'İ ---
@app.get("/products/{product_id}/sales_trend")
def get_sales_trend(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.product.Product).filter(models.product.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    # Son 7 günün takvimini oluştur (Bugünden geriye doğru)
    today = datetime.utcnow().date()
    dates = [(today - timedelta(days=i)).strftime("%d-%m-%Y") for i in range(6, -1, -1)]
    sales_data = {date: 0 for date in dates} # Tüm günleri önce 0 satışla doldur

    # Veritabanından son 7 günün satışlarını çek
    start_datetime = datetime.combine(today - timedelta(days=6), datetime.min.time())
    logs = db.query(models.product.SaleLog).filter(
        models.product.SaleLog.product_id == product_id,
        models.product.SaleLog.sale_date >= start_datetime
    ).all()

    for log in logs:
        log_date = log.sale_date.date().strftime("%d-%m-%Y")
        if log_date in sales_data:
            sales_data[log_date] += log.quantity
            
    return {"labels": list(sales_data.keys()), "data": list(sales_data.values())}

# --- CSV İŞLEMLERİ (İÇE VE DIŞA AKTAR) ---
@app.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    products = db.query(models.product.Product).order_by(models.product.Product.name, models.product.Product.supplier_name).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    # Sütun başlıkları
    writer.writerow(["Ürün İsmi", "Mevcut Stok", "Günlük Tüketim (Ort)", "Tedarik Süresi (Gün)", "Birim Boyutu (m3)", "Birim Paletteki Ürün Sayısı", "Toplam Palet", "Birim Ağırlık (kg)", "Tedarikçi Adı", "Tedarikçi Email"])
    
    for p in products:
        total_pallets = math.ceil(p.stock_quantity / p.items_per_pallet) if p.items_per_pallet and p.stock_quantity > 0 else 0
        writer.writerow([
            p.name, p.stock_quantity, p.estimated_daily_consumption, p.lead_time_days, 
            p.size_m3, p.items_per_pallet, total_pallets, p.weight_kg, p.supplier_name, p.supplier_email
        ])
        
    output.seek(0)
    # Bilgisayara dosya olarak inmesi için gereken header'ı ekliyoruz
    return Response(
        content=output.getvalue().encode('utf-8-sig'), # Türkçe karakter desteği için utf-8-sig
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=envanter_durumu.csv"}
    )

@app.post("/import/csv")
def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(contents))
    
    for row in reader:
        name = row.get("Ürün İsmi")
        if not name:
            continue
            
        # Hatalı/Boş verileri korumak için hata yakalama (try/except)
        try:
            stock = int(float(row.get("Mevcut Stok", 0)))
            consumption = float(row.get("Günlük Tüketim (Ort)", 0.0))
            lead_time = int(float(row.get("Tedarik Süresi (Gün)", 1)))
            size = float(row.get("Birim Boyutu (m3)", 0.0))
            pallet = int(float(row.get("Birim Paletteki Ürün Sayısı", 0)))
            weight = float(row.get("Birim Ağırlık (kg)", 0.0))
            supplier_n = row.get("Tedarikçi Adı", "")
            supplier_e = row.get("Tedarikçi Email", "")
        except ValueError:
            continue # Sayısal olmayan satırları atla
            
        existing_product = db.query(models.product.Product).filter(
            models.product.Product.name == name,
            models.product.Product.supplier_name == supplier_n
        ).first()
        if existing_product:
            # Eğer ürün varsa stoklarını üzerine ekle ve güncel ayarlarla ez
            existing_product.stock_quantity += stock
            existing_product.lead_time_days = lead_time
            existing_product.size_m3 = size
            existing_product.items_per_pallet = pallet
            existing_product.weight_kg = weight
            existing_product.supplier_name = supplier_n
            existing_product.supplier_email = supplier_e
            inventory_service.manage_placements(existing_product, db)
            
            log_desc = f"CSV içe aktarımı ile {stock} adet eklendi. Yeni stok: {existing_product.stock_quantity}."
            new_log = models.product.InventoryLog(product_id=existing_product.id, action_type="CSV GÜNCELLEME", description=log_desc)
            db.add(new_log)
        else:
            # Yeni ürün oluştur
            new_product = models.product.Product(
                name=name, stock_quantity=stock, lead_time_days=lead_time,
                initial_expected_daily_consumption=consumption, estimated_daily_consumption=consumption,
                size_m3=size, items_per_pallet=pallet, weight_kg=weight,
                supplier_name=supplier_n, supplier_email=supplier_e
            )
            db.add(new_product)
            db.commit() # ID'nin oluşması için commit
            db.refresh(new_product)
            inventory_service.manage_placements(new_product, db)
            
            new_log = models.product.InventoryLog(product_id=new_product.id, action_type="CSV YENİ ÜRÜN", description=f"CSV dosyası üzerinden {stock} stok ile eklendi.")
            db.add(new_log)
            
    db.commit()
    return {"mesaj": "Ürünler başarıyla içe aktarıldı."}

# --- SANAL DEPO YÖNETİMİ ENDPOINT'LERİ ---
@app.post("/locations/")
def create_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    db_location = db.query(models.product.Location).filter(
        models.product.Location.name == location.name,
        models.product.Location.parent_id == location.parent_id
    ).first()
    if db_location:
        raise HTTPException(status_code=400, detail="Bu konum zaten mevcut.")
    new_location = models.product.Location(**location.model_dump())
    db.add(new_location)
    db.commit()
    db.refresh(new_location)
    
    # Yeni konum eklendiği için depoyu yeniden dengele
    change_log = rebalancing_service.rebalance_warehouse(db)
    db.commit()

    return {"location": new_location, "rebalance_log": change_log}

@app.get("/warehouse-map", response_class=HTMLResponse)
def get_warehouse_map(request: Request, db: Session = Depends(get_db)):
    # Sadece en üst seviye lokasyonları (Ana Depolar) çekiyoruz
    locations = db.query(models.product.Location).filter(
        models.product.Location.parent_id == None
    ).order_by(models.product.Location.name).all()
    
    # Formda "Üst Konum" seçebilmek için tüm lokasyonları çekiyoruz
    all_locations = db.query(models.product.Location).order_by(models.product.Location.name).all()

    return templates.TemplateResponse(
        request=request, name="warehouse_map.html", context={"locations": locations, "all_locations": all_locations}
    )
# --- ÖZET İSTATİSTİKLER API ENDPOINT'İ ---
@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    products = db.query(models.product.Product).all()
    unique_names = set(p.name for p in products) # Toplam ürün çeşidini gruplayarak say
    
    critical_groups = set()
    total_stock = 0
    for p in products:
        status = inventory_service.calculate_stock_status(p)
        total_stock += p.stock_quantity
        if status["needs_reorder"]:
            critical_groups.add(p.name)
            
    return {
        "total_products": len(unique_names),
        "total_stock": total_stock,
        "total_critical": len(critical_groups)
    }

# --- KULLANICI DOSTU WEB ARAYÜZÜ (GÜNCELLENDİ) ---
@app.get("/dashboard", response_class=HTMLResponse)
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    # Ürünleri isme ve sonra tedarikçiye göre sıralayarak gruplanmış gibi görünmelerini sağla
    db_products = db.query(models.product.Product).order_by(models.product.Product.name, models.product.Product.supplier_name).all()
    
    grouped_data = {}
    critical_groups = set()
    total_stock = 0
    
    for p in db_products:
        status = inventory_service.calculate_stock_status(p)
        name = status["product_name"]
        
        if name not in grouped_data:
            grouped_data[name] = {"product_name": name, "total_stock": 0, "product_list": []}
            
        grouped_data[name]["total_stock"] += status["current_stock"]
        grouped_data[name]["product_list"].append(status)
        
        total_stock += p.stock_quantity
        
        if status["needs_reorder"]:
            critical_groups.add(name)
        
    # Yeni sürümlere tam uyumlu TemplateResponse kullanımı:
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "grouped_products": list(grouped_data.values()),
            "total_products": len(grouped_data),
            "total_stock": total_stock,
            "total_critical": len(critical_groups)
        }
    )