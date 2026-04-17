"""
Depo Raf Optimizasyonu ve Yeniden Dengeleme Servisi

Bu servis, depodaki ürün yerleşimlerini daha verimli hale getirmek için
gelişmiş yeniden dengeleme algoritmalarını içerir. 

Tetikleyiciler:
- Yeni bir raf eklendiğinde
- Bir ürün veya ürün grubu tamamen silindiğinde ve raf boşaldığında
- Periyodik olarak (gelecekte eklenebilir)
- Manuel olarak çağrıldığında

Amaçlar:
1. Raf kapasitelerini (hacim, ağırlık) en iyi şekilde kullanmak.
2. Ürünleri mantıksal gruplara göre (örn. tedarikçi) bir arada tutmak.
3. Hızlı tükenen ürünleri daha erişilebilir yerlere koymak (gelecekte eklenebilir).
4. Değişiklikleri raporlamak ve kullanıcıya sunmak.
"""
from sqlalchemy.orm import Session, joinedload
import math
from models.product import Product, Location, StockPlacement

def rebalance_warehouse(db: Session):
    """
    Tüm depoyu analiz eder ve ürünleri en verimli şekilde yeniden yerleştirir.
    
    Bu fonksiyon oldukça ağır bir operasyondur ve sadece gerekli durumlarda
    (örn. yeni raf eklenmesi gibi büyük yapısal değişikliklerde) çağrılmalıdır.
    
    Returns:
        list[str]: Yapılan değişikliklerin bir listesi. Örn: 
                   ["'Ürün A' Raf-01'den Raf-02'ye taşındı.", ...]
    """
    print("Depo yeniden dengeleme işlemi başlatılıyor...")

    # 1. Mevcut durumu al
    products_to_place = db.query(Product).filter(Product.stock_quantity > 0).all()
    
    # Ağaç yapısında (recursive) gezinerek tüm "Leaf" (Yaprak) lokasyonları bul
    def get_all_leaf_locations(loc, leaf_list):
        if not loc.sub_locations:
            if loc.max_volume_m3 > 0:
                leaf_list.append(loc)
        else:
            for sub in loc.sub_locations:
                get_all_leaf_locations(sub, leaf_list)
                
    top_locations = db.query(Location).filter(Location.parent_id == None).order_by(Location.name).all()
    all_leaf_locations = []
    for loc in top_locations:
        get_all_leaf_locations(loc, all_leaf_locations)
    
    # 2. Eski yerleşimleri kaydet
    old_placements = {} # {product_id: {location_name: quantity}}
    for p in db.query(StockPlacement).options(joinedload(StockPlacement.location)).all():
        if p.product_id not in old_placements:
            old_placements[p.product_id] = {}
        old_placements[p.product_id][p.location.name] = p.quantity

    # 3. Mevcut tüm yerleşimleri sil (önce silmek daha temiz bir başlangıç sağlar)
    db.query(StockPlacement).delete()
    db.flush() # Değişiklikleri veritabanına gönder ama commit etme
    
    # 4. Ürünleri yeniden yerleştir
    
    # Rafların kalan kapasitelerini takip etmek için bir yapı
    location_capacities = {
        loc.id: {
            "remaining_volume": loc.max_volume_m3,
            "remaining_weight": loc.max_weight_kg
        } for loc in all_leaf_locations
    }

    # Ürünleri, en çok yer kaplayandan başlayarak sırala (büyükleri önce yerleştirmek daha verimli olabilir)
    sorted_products = sorted(products_to_place, key=lambda p: p.size_m3 * p.stock_quantity, reverse=True)

    for product in sorted_products:
        quantity_to_place = product.stock_quantity
        unit_volume = product.size_m3
        unit_weight = product.weight_kg

        # Bu ürün için yeni yerleşimler oluşturulacak
        for loc in all_leaf_locations:
            # Soğuk zincir kuralı: Ürün soğuk zincirse sadece soğuk rafa, değilse normal rafa konur
            if getattr(loc, "is_cold_chain", False) != getattr(product, "is_cold_chain", False):
                continue
                
            if quantity_to_place <= 0:
                break

            # Rafın mevcut kalan kapasitesini al
            rem_vol = location_capacities[loc.id]["remaining_volume"]
            rem_wgt = location_capacities[loc.id]["remaining_weight"]

            # Bu rafa bu üründen kaç tane sığabileceğini hesapla
            can_place_by_vol = math.floor(rem_vol / unit_volume) if unit_volume > 0 else float('inf')
            can_place_by_wgt = math.floor(rem_wgt / unit_weight) if unit_weight > 0 else float('inf')
            
            possible_to_add = min(can_place_by_vol, can_place_by_wgt)

            if possible_to_add > 0:
                # Ne kadar yerleştireceğimizi belirle (istenen miktar ve raftaki boş yer kadar)
                add_amount = min(quantity_to_place, possible_to_add)
                
                # Yeni yerleşim kaydı oluştur
                new_placement = StockPlacement(
                    product_id=product.id,
                    location_id=loc.id,
                    quantity=add_amount
                )
                db.add(new_placement)

                # Kalan kapasiteleri güncelle
                location_capacities[loc.id]["remaining_volume"] -= add_amount * unit_volume
                location_capacities[loc.id]["remaining_weight"] -= add_amount * unit_weight
                
                # Yerleştirilecek miktarı azalt
                quantity_to_place -= add_amount

    db.flush() # Yeni yerleşimleri ID alması için flusla

    # 5. Değişiklik günlüğünü oluştur
    change_log = []
    new_placements = {} # {product_id: {location_name: quantity}}
    for p in db.query(StockPlacement).options(joinedload(StockPlacement.location)).all():
        if p.product_id not in new_placements:
            new_placements[p.product_id] = {}
        new_placements[p.product_id][p.location.name] = p.quantity

    # Tüm ürünleri döngüye alarak her birinin durumunu karşılaştır
    all_product_ids = set(old_placements.keys()) | set(new_placements.keys())

    for pid in all_product_ids:
        old_locs = old_placements.get(pid, {})
        new_locs = new_placements.get(pid, {})
        product_name = db.query(Product.name).filter(Product.id == pid).scalar()

        # Eski ve yeni yerleşimleri set'e çevirerek farkları bul
        old_locations = set(old_locs.keys())
        new_locations = set(new_locs.keys())

        # Eğer yerleşimler tamamen aynıysa, bir sonraki ürüne geç
        if old_locs == new_locs:
            continue

        # Basit format: "Ürün X eski rafları [A,B], yeni rafları [C,D]"
        old_str = ", ".join(sorted(list(old_locations))) or "YOK"
        new_str = ", ".join(sorted(list(new_locations))) or "YOK"
        
        change_log.append(f"'{product_name}' ürünü yeniden konumlandırıldı: Eski Konumlar [{old_str}] -> Yeni Konumlar [{new_str}]")

    print(f"Depo yeniden dengeleme tamamlandı. {len(change_log)} değişiklik yapıldı.")
    return change_log
