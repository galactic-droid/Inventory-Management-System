# Stok durumunu ve sipariş uyarısını hesaplayan servis
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import math
from models.product import Product, SaleLog, Location, StockPlacement

def manage_placements(product: Product, db: Session):
    """
    Bir ürünün stoğunu, raflardaki yerleşimleriyle senkronize eder.
    Stok artışı: Yeni yer bulur veya mevcut yerleşime ekler.
    Stok azalışı: Yerleşimlerden düşer ve boşalan rafları temizler.
    """
    total_placed_quantity = sum(p.quantity for p in product.placements)
    difference = product.stock_quantity - total_placed_quantity

    if difference > 0: # STOK EKLENMESİ GEREKİYOR
        quantity_to_place = difference
        unit_volume = product.size_m3
        unit_weight = product.weight_kg

        # Öncelik 1: Bu ürünü zaten barındıran raflarda yer var mı?
        for placement in sorted(product.placements, key=lambda p: p.quantity):
            if quantity_to_place <= 0: break
            location = placement.location
            
            # Bu lokasyondaki diğer ürünlerin kapladığı alan
            current_location_volume = sum(p.product.size_m3 * p.quantity for p in location.placements)
            current_location_weight = sum(p.product.weight_kg * p.quantity for p in location.placements)

            location_remaining_volume = location.max_volume_m3 - current_location_volume
            location_remaining_weight = location.max_weight_kg - current_location_weight

            can_place_by_vol = math.floor(location_remaining_volume / unit_volume) if unit_volume > 0 else float('inf')
            can_place_by_wgt = math.floor(location_remaining_weight / unit_weight) if unit_weight > 0 else float('inf')
            
            possible_to_add = min(can_place_by_vol, can_place_by_wgt)
            if possible_to_add > 0:
                add_amount = min(quantity_to_place, possible_to_add)
                placement.quantity += add_amount
                quantity_to_place -= add_amount

        # Öncelik 2: Hala yerleştirilecek ürün varsa, ağaçta boş bir "En Alt Seviye (Leaf)" ara
        if quantity_to_place > 0:
            occupied_location_ids = {p.location_id for p in db.query(StockPlacement.location_id).distinct()}
            
            # Ağaç yapısında (recursive) gezinerek boş "Leaf" (Yaprak/En alt) lokasyonları bulma
            def get_empty_leaf_locations(loc, empty_list):
                if not loc.sub_locations:
                    if loc.max_volume_m3 > 0 and loc.id not in occupied_location_ids:
                        if getattr(loc, "is_cold_chain", False) == getattr(product, "is_cold_chain", False):
                            empty_list.append(loc)
                else:
                    for sub in loc.sub_locations:
                        get_empty_leaf_locations(sub, empty_list)
                        
            top_locations = db.query(Location).filter(Location.parent_id == None).order_by(Location.name).all()
            empty_locations = []
            for loc in top_locations:
                get_empty_leaf_locations(loc, empty_locations)

            for loc in empty_locations:
                if quantity_to_place <= 0: break
                
                can_place_by_vol = math.floor(loc.max_volume_m3 / unit_volume) if unit_volume > 0 else float('inf')
                can_place_by_wgt = math.floor(loc.max_weight_kg / unit_weight) if unit_weight > 0 else float('inf')
                loc_capacity = min(can_place_by_vol, can_place_by_wgt)

                if loc_capacity > 0:
                    place_amount = min(quantity_to_place, loc_capacity)
                    new_placement = StockPlacement(product_id=product.id, location_id=loc.id, quantity=place_amount)
                    db.add(new_placement)
                    quantity_to_place -= place_amount

    elif difference < 0: # STOK AZALTILMASI GEREKİYOR
        quantity_to_remove = abs(difference)
        # En dolu raftan başlayarak stoğu düş (daha hızlı raf boşaltmak için)
        for placement in sorted(product.placements, key=lambda p: p.quantity, reverse=True):
            if quantity_to_remove <= 0: break
            
            if placement.quantity <= quantity_to_remove:
                quantity_to_remove -= placement.quantity
                db.delete(placement)
            else:
                placement.quantity -= quantity_to_remove
                quantity_to_remove = 0


def calculate_stock_status(product):
    # Güvenlik payı: Tedarik süresinin üzerine 2 gün daha ekliyoruz ki tamamen sıfırlanmayalım
    safety_stock_days = 2 
    
    estimated_finish_date_str = None
    days_until_empty = float('inf')

    # Stokta ürün kalmadıysa, bitiş günü her zaman 0'dır. Bu, tüketim 0 olsa bile "sonsuz" gösterilmesini engeller.
    if product.stock_quantity <= 0:
        days_until_empty = 0
        estimated_finish_date_str = "Tükendi"
    # Eğer ürün için bir tüketim tahmini varsa (0'dan büyükse) bitiş gününü ve tarihini hesapla
    elif product.estimated_daily_consumption > 0:
        days_until_empty = product.stock_quantity / product.estimated_daily_consumption
        
        # Çok düşük tüketimlerde timedelta OverflowError (çökme) verebilir.
        # Bunu engellemek için 10 yıl (3650 gün) sınırı koyuyoruz.
        if days_until_empty > 3650:
            estimated_finish_date_str = "10+ Yıl Sonra"
        else:
            # Bitiş tarihini saatlik değil, takvim gününe tam gün ekleyerek buluyoruz.
            estimated_finish_date = datetime.utcnow().date() + timedelta(days=int(days_until_empty))
            estimated_finish_date_str = estimated_finish_date.strftime("%d-%m-%Y")
        
    # Sipariş verme eşiğimiz (Tedarik süresi + Güvenlik payı)
    reorder_threshold = product.lead_time_days + safety_stock_days
    
    # Kalan gün, sipariş eşiğimizden küçük veya eşitse uyarı ver!
    needs_reorder = days_until_empty <= reorder_threshold
    
    # Ekranda göstermek için küsuratlı saatleri atıp tam gün (integer) gösterelim
    display_days = int(days_until_empty) if days_until_empty != float('inf') else "Belirsiz"

    if needs_reorder:
        if product.stock_quantity <= 0:
            message = "🚨 STOK TÜKENDİ! Acil sipariş verilmelidir."
        else:
            message = f"🚨 KRİTİK UYARI! Tahmini {display_days} gün içinde stok bitecek. Sipariş gerekli!"
    else:
        if estimated_finish_date_str not in ["Belirsiz", "Tükendi"]:
            message = f"✅ Stok durumu iyi. Tahmini bitiş tarihi: {estimated_finish_date_str}."
        else:
            message = "✅ Stok durumu iyi. Henüz yeterli tüketim verisi yok."
            
    # Raf konumlarını al
    placements_info = []
    if hasattr(product, 'placements') and product.placements:
        # Hiyerarşik tam yolu bulmak için yardımcı fonksiyon (Örn: Ana Depo > A-Blok > Raf 1)
        def get_full_path(loc):
            path = []
            current = loc
            while current:
                path.insert(0, current.name)
                current = current.parent
            return " > ".join(path)
            
        # Rafları isme göre sıralayarak tutarlı bir görünüm sağla
        for pl in sorted(product.placements, key=lambda p: p.location.name):
            full_path = get_full_path(pl.location)
            placements_info.append(f"{full_path} ({pl.quantity})")

            
    # --- SKT (Son Kullanma Tarihi) Analizi ---
    batch_list = []
    expiry_message = ""
    if getattr(product, 'has_expiry_tracking', False) and product.batches:
        today = datetime.utcnow().date()
        has_expired = False
        has_expiring_soon = False
        
        for batch in product.batches:
            if batch.quantity > 0:
                b_date_str = batch.expiry_date.strftime("%d-%m-%Y") if batch.expiry_date else "Tarihsiz"
                batch_list.append({"quantity": batch.quantity, "expiry_date": b_date_str})
                if batch.expiry_date:
                    if batch.expiry_date <= today:
                        has_expired = True
                    elif (batch.expiry_date - today).days <= 30: # 30 gün kala uyarı
                        has_expiring_soon = True
                        
        if has_expired:
            message += " | ❌ DİKKAT: SKT'Sİ GEÇMİŞ ÜRÜN VAR!"
        elif has_expiring_soon:
            message += " | ⚠️ 30 Günden az kalan SKT var!"
            
    total_pallets = math.ceil(product.stock_quantity / product.items_per_pallet) if product.items_per_pallet and product.stock_quantity > 0 else 0
        
    return {
        "product_id": product.id,
        "product_name": product.name,
        "current_stock": product.stock_quantity,
        "days_until_empty": display_days,
        "estimated_finish_date": estimated_finish_date_str,
        "needs_reorder": needs_reorder,
        "message": message,        
        "shelf_locations": placements_info,
        "size_m3": product.size_m3,
        "items_per_pallet": product.items_per_pallet,
        "total_pallets": total_pallets,
        "weight_kg": product.weight_kg,
        "has_expiry_tracking": getattr(product, 'has_expiry_tracking', False),
        "batches": batch_list,
        "supplier_name": getattr(product, 'supplier_name', ""),
        "supplier_email": getattr(product, 'supplier_email', ""),
        "is_cold_chain": getattr(product, 'is_cold_chain', False)
    }

def update_daily_consumption(product: Product, db: Session):
    """
    Tahmini günlük tüketimi hesaplar.
    Tam TAKVİM GÜNÜ (Calendar Day) mantığıyla çalışarak saatlik dalgalanmaları önler.
    """
    now = datetime.utcnow()
    # Bugünün ve ürünün oluşturulma tarihinin gece yarısı (00:00:00) saatlerini alıyoruz
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    creation_start = product.creation_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Ürünün takvim bazında tam yaşı (Bugün oluşturulduysa 0, dün ise 1...)
    calendar_age_days = (today_start - creation_start).days

    if calendar_age_days >= 7:
        # Tam 7 takvim günü öncesinin gece yarısından itibaren olan satışlar
        start_date = today_start - timedelta(days=7)
        total_sales = db.query(
            func.sum(SaleLog.quantity)
        ).filter(
            SaleLog.product_id == product.id,
            SaleLog.sale_date >= start_date
        ).scalar() or 0
        
        # Satışları tam 7 güne böl
        actual_speed = total_sales / 7.0
        
        # SIKINTI ÇÖZÜLDÜ: 7 gün geçmiş olsa bile hiç satış yoksa 0'a düşüp sistemi 'Belirsiz' yapmasını engelle.
        if actual_speed == 0 and product.initial_expected_daily_consumption > 0:
            product.estimated_daily_consumption = product.initial_expected_daily_consumption
        else:
            product.estimated_daily_consumption = actual_speed
    else:
        # 7 günden yeni ürünler için (Soğuk Başlangıç)
        new_daily_consumption = product.initial_expected_daily_consumption
        
        total_sales = db.query(func.sum(SaleLog.quantity)).filter(
            SaleLog.product_id == product.id,
            SaleLog.sale_date >= creation_start
        ).scalar() or 0
        
        # Bölen gün sayısı: Bugün dahil olduğu için takvim yaşına +1 ekliyoruz.
        # (Örn: Bugün eklendiyse 1 tam günmüş gibi, dün eklendiyse 2 tam güne bölünür)
        divisor_days = calendar_age_days + 1
        actual_speed = total_sales / divisor_days
        
        # Eğer beklenen değerden hızlı satılıyorsa veya beklenti girilmemişse gerçek hızı yakala
        if actual_speed > new_daily_consumption or new_daily_consumption == 0:
            new_daily_consumption = actual_speed
            
        product.estimated_daily_consumption = new_daily_consumption