# Katalogcu

Katalog yönetim ve ürün tanıma sistemi. AI destekli katalog oluşturma ve hotspot yönetimi.

## 📋 Proje Hakkında

Katalogcu, dijital kataloglar oluşturmak ve yönetmek için geliştirilmiş modern bir web uygulamasıdır. YOLO (You Only Look Once) AI modeli kullanarak katalog sayfalarındaki ürünleri otomatik olarak tanıyabilir ve tıklanabilir alanlar (hotspot) oluşturabilir.

## 🏗️ Mimari

Bu proje Clean Architecture prensiplerine uygun olarak 3 ana bileşenden oluşur:

- **Backend**: .NET 9 Web API
- **Frontend**: Angular uygulaması  
- **YOLO Service**: Python tabanlı AI servisi

## 📚 Detaylı Dokümantasyon

Proje dosya yapısı ve tüm bileşenlerin detaylı açıklaması için:
👉 **[PROJE_YAPISI.md](./PROJE_YAPISI.md)** dosyasına bakınız.

## 🚀 Hızlı Başlangıç

### Gereksinimler
- .NET 9 SDK
- Node.js ve npm
- Python 3.8+
- Docker ve Docker Compose
- PostgreSQL

### Kurulum

1. **Veritabanını başlatın:**
```bash
cd backend
docker-compose up -d
```

2. **Backend'i çalıştırın:**
```bash
cd backend/Katalogcu.API
dotnet restore
dotnet run
```

3. **Frontend'i çalıştırın:**
```bash
cd frontend/katalogcu-frontend
npm install
npm start
```

4. **YOLO servisini çalıştırın:**
```bash
cd yolo-service
pip install -r requirements.txt
python api.py
```

## 🔑 Özellikler

- ✅ Katalog yönetimi (Oluştur, Güncelle, Sil)
- ✅ Ürün yönetimi
- ✅ Kullanıcı kimlik doğrulama (JWT)
- ✅ PDF yükleme ve işleme
- ✅ Excel export
- ✅ **YOLO AI entegrasyonu** - Backend ile tam entegre
- ✅ **Otomatik hotspot tespiti** - YOLO servisi üzerinden
- ✅ OCR desteği

## 🛠️ Teknolojiler

- **Backend**: .NET 9, Entity Framework Core, PostgreSQL, HttpClient
- **Frontend**: Angular, TypeScript
- **AI**: Python, YOLO, FastAPI, OpenCV
- **DevOps**: Docker, Docker Compose

## 📖 API Dokümantasyonu

Backend çalıştığında Swagger UI'a erişebilirsiniz:
```
http://localhost:5000/swagger
```

## 🤝 Katkıda Bulunma

Pull request'ler memnuniyetle karşılanır. Büyük değişiklikler için lütfen önce bir issue açarak neyi değiştirmek istediğinizi tartışın.

## 📄 Lisans

[MIT](https://choosealicense.com/licenses/mit/)
