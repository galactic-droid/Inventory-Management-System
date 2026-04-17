# Envanter Sistemi

Bu proje, FastAPI ve Docker kullanılarak geliştirilmiş bir envanter ve depo yönetim sistemidir. Stok takibi, talep tahminlemesi, çok seviyeli depo hiyerarşisi ve otomatik raf optimizasyonu gibi özellikler sunar.

## Temel Özellikler

- **Çok Seviyeli Depo Hiyerarşisi:** Depoları; Bölge, Koridor, Raf ve Göz gibi sınırsız alt kırılımda yönetebilme.
- **Akıllı Stok Yönetimi:** Satış verilerine dayalı olarak ürünlerin günlük tüketim hızını otomatik hesaplar ve stokların ne zaman biteceğini tahmin eder.
- **Otomatik Depo Dengeleme:** Yeni bir ürün veya lokasyon eklendiğinde, tüm depoyu en verimli (hacim/ağırlık) şekilde kullanmak için ürünleri otomatik olarak yeniden yerleştirir.
- **Soğuk Zincir Yönetimi:** Soğuk zincir gerektiren ürünlerin (örn: süt, et) yalnızca bu özelliğe sahip lokasyonlara yerleştirilmesini zorunlu kılar.
- **SKT ve Parti Takibi (FIFO):** Son kullanma tarihi (SKT) olan ürünleri parti (batch) bazında takip eder ve stok çıkışlarında ilk giren ilk çıkar (FIFO) mantığını uygular.
- **Görsel Dashboard:** Anlık stok durumu, kritik seviyedeki ürünler ve temel istatistikler için canlı bir kontrol paneli sunar.
- **Raporlama ve Analiz:** Ürün satış trendlerini gösteren dinamik grafikler ve tüm envanter durumunu CSV formatında dışa aktarma imkanı.
- **Docker ile Kolay Kurulum:** Projeyi tek bir komutla, bağımlılık sorunları yaşamadan ayağa kaldırma.

## Kullanılan Teknolojiler

- **Backend:** Python, FastAPI, SQLAlchemy (ORM)
- **Frontend:** Jinja2, HTML, CSS, Bootstrap 5, JavaScript, Chart.js
- **Veritabanı:** SQLite
- **Containerization:** Docker, Docker Compose

## Veri Yapısı (Schema)

Sistem temel olarak iki ana model üzerine kuruludur:

- **`Location` (Konum):** Kendi kendini referans alabilen bir modeldir. Bu sayede `Depo > Bölge > Koridor > Raf` gibi iç içe geçmiş bir ağaç yapısı oluşturulur. Kapasite (hacim, ağırlık) ve `is_cold_chain` gibi özellikler sadece en alt seviyedeki lokasyonlarda tanımlanır.
- **`Product` (Ürün):** Stok miktarı, tedarik süresi, boyutları ve `is_cold_chain` gibi temel bilgileri içerir. `SaleLog`, `InventoryLog` ve `StockBatch` gibi alt tablolarla ilişkilidir.

## Kurulum ve Çalıştırma

### Gereksinimler
- Git
- Docker

### Docker ile Kurulum (Önerilen)

1.  **Projeyi Klonlayın:**
    ```bash
    git clone https://github.com/galactic-droid/Inventory-Management-System
    cd Inventory-Management-System
    ```

2.  **Uygulamayı Başlatın:**
    Projenin ana dizinindeyken aşağıdaki komutu çalıştırarak Docker konteynerini inşa edin ve arka planda başlatın.
    ```bash
    docker-compose up -d --build
    ```

3.  **Test Verilerini Yükleyin (Opsiyonel):**
    Sistemi hızlıca test etmek için örnek depo hiyerarşisi ve ürünleri (teknoloji, mobilya, soğuk zincir vb.) içeren başlangıç scriptini çalıştırabilirsiniz.
    ```bash
    docker exec -it envanter-app python seed.py
    ```

4.  **Erişim:**
    Kurulum tamamlandığında, tarayıcınızdan aşağıdaki adrese giderek uygulamayı kullanmaya başlayabilirsiniz:
    **http://localhost:8000/dashboard**

### Sistemi Durdurma
Uygulamayı durdurmak için terminalde aynı dizindeyken şu komutu girin:
```bash
docker-compose down
```

### Manuel Kurulum
1. `python -m venv venv` ile sanal ortam oluşturun ve aktif edin.
2. `pip install -r requirements.txt` ile bağımlılıkları kurun.
3. `python seed.py` komutu ile test verilerini yükleyin (opsiyonel).
4. `uvicorn main:app --reload` komutu ile sunucuyu başlatın.

## Proje Yapısı

```
.
├── templates/          # HTML şablonları (Jinja2)
├── services/           # İş mantığı (stok hesaplama, dengeleme vb.)
├── schemas/            # Veri doğrulama şemaları (Pydantic)
├── models/             # Veritabanı modelleri (SQLAlchemy)
├── main.py             # Ana FastAPI uygulaması ve API endpoint'leri
├── seed.py             # Test verilerini oluşturan başlangıç scripti
├── database.py         # Veritabanı bağlantı ayarları
├── Dockerfile          # Docker imajı oluşturma reçetesi
├── docker-compose.yml  # Docker servislerini yönetme dosyası
└── requirements.txt    # Python bağımlılıkları
```