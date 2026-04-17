# 📦 Envanter Sistemi

Bu proje, ürünlerinizi, stok durumlarınızı, tedarik sürelerinizi ve fiziksel depo/raf kapasitelerinizi takip edebileceğiniz FastAPI tabanlı akıllı bir sistemdir.

---

## 🐳 Docker ile Çalıştırma (Önerilen)

Projeyi bilgisayarınıza herhangi bir kütüphane kurmadan, bağımlılık sorunları yaşamadan tek tıkla çalıştırmak için Docker kullanabilirsiniz.

### Gereksinimler
- Bilgisayarınızda **Docker Desktop**'ın yüklü ve arka planda açık olması gerekir.

### Çalıştırma Adımları
1. Projenin ana klasöründe (`MTH132_workspace_1`) bir terminal (komut satırı) açın.
2. Sistemi inşa edip arka planda başlatmak için aşağıdaki komutu çalıştırın:
   ```bash
   docker-compose up -d --build
   ```
3. Sistem ayağa kalktığında tarayıcınızdan panele erişebilirsiniz:
   👉 **http://localhost:8000/dashboard**

### Sistemi Durdurma
Uygulamayı kapatmak için terminalde aynı dizindeyken şu komutu girin:
```bash
docker-compose down
```
*⚠️ Önemli: `docker-compose.yml` içindeki `volumes` ayarı sayesinde, konteyner silinse dahi verileriniz bilgisayarınızdaki `envanter.db` dosyasında güvende kalır, veri kaybı yaşamazsınız.*

---

## 🛠️ Manuel (Sanal Ortam) Kurulumu
1. `python -m venv venv` ile sanal ortam oluşturun ve aktif edin (`.\venv\Scripts\activate`).
2. `pip install -r requirements.txt` ile kütüphaneleri kurun.
3. `uvicorn main:app --reload` komutu ile sunucuyu başlatın.