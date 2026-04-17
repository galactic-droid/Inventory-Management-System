# Hafif bir Python sürümü kullanıyoruz
FROM python:3.11-slim

# Konteyner içindeki çalışma dizinimizi /app olarak belirliyoruz
WORKDIR /app

# Önce kütüphane listesini kopyalayıp kuruyoruz (Önbelleği verimli kullanmak için)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Projedeki tüm kodları konteynerin içine kopyalıyoruz
COPY . .

# Uygulamanın 8000 portunda çalışacağını belirtiyoruz
EXPOSE 8000

# Konteyner ayağa kalktığında çalıştırılacak komut
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]