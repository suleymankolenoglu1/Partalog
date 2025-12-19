# Katalogcu - Proje Dosya Yapısı ve İçeriği

## Genel Bakış
Bu belge, Katalogcu projesindeki tüm dosyaların ve dizinlerin detaylı bir haritasını içerir.

## 📁 Ana Dizin Yapısı

```
Katalogcu/
├── backend/          # .NET 9 Web API (Clean Architecture)
├── frontend/         # Angular Frontend Uygulaması
├── yolo-service/     # Python AI Servisi (YOLO Object Detection)
└── README.md         # Proje Ana Dokümantasyonu
```

---

## 🔧 Backend (.NET 9 - Clean Architecture)

### Katmanlar

#### 1. **Katalogcu.API** (Sunum Katmanı)
```
backend/Katalogcu.API/
├── Controllers/
│   ├── AuthController.cs         # Kimlik doğrulama (Login/Register)
│   ├── CatalogsController.cs     # Katalog yönetimi
│   ├── ProductsController.cs     # Ürün yönetimi
│   ├── HotspotsController.cs     # Hotspot (tıklanabilir alan) yönetimi
│   ├── UsersController.cs        # Kullanıcı yönetimi
│   └── FilesController.cs        # Dosya yükleme/indirme
├── Services/
│   ├── PdfService.cs             # PDF işlemleri
│   ├── ExcelService.cs           # Excel export işlemleri
│   └── CloudOcrService.cs        # OCR (Optik Karakter Tanıma) servisi
├── Program.cs                    # Uygulama giriş noktası
├── Katalogcu.API.csproj         # Proje yapılandırma dosyası
└── Properties/
    └── launchSettings.json       # Debug ayarları
```

**Özellikler:**
- JWT Bearer Authentication
- Swagger/OpenAPI dokümantasyonu
- CORS desteği (Angular için)
- PostgreSQL veritabanı entegrasyonu

#### 2. **Katalogcu.Domain** (Domain Katmanı)
```
backend/Katalogcu.Domain/
├── Entities/
│   ├── AppUser.cs                # Kullanıcı modeli
│   ├── Catalog.cs                # Katalog modeli
│   ├── CatalogPage.cs            # Katalog sayfa modeli
│   ├── Product.cs                # Ürün modeli
│   └── Hotspot.cs                # Hotspot modeli
└── Common/
    └── BaseEntity.cs             # Temel entity sınıfı
```

**Domain Modelleri:**
- **AppUser**: Kullanıcı bilgileri ve kimlik doğrulama
- **Catalog**: Katalog ana bilgileri
- **CatalogPage**: Katalog sayfaları (PDF sayfaları)
- **Product**: Ürün detayları
- **Hotspot**: Ürünlere bağlı tıklanabilir alanlar (koordinatlar)

#### 3. **Katalogcu.Infrastructure** (Altyapı Katmanı)
```
backend/Katalogcu.Infrastructure/
├── Persistence/
│   └── AppDbContext.cs           # Entity Framework DbContext
└── Migrations/                   # Veritabanı migration dosyaları
    ├── 20251123122058_InitialCreate.cs
    ├── 20251123124011_AddCatalogDomain.cs
    ├── 20251210144736_AddPageNumberToProduct.cs
    └── 20251218181058_UpdateHotspotForYolo.cs
```

**Veritabanı:**
- PostgreSQL
- Entity Framework Core migrations
- Clean Architecture pattern

#### 4. **Katalogcu.Application** (Uygulama Katmanı)
```
backend/Katalogcu.Application/
└── Katalogcu.Application.csproj
```

**Not:** Bu katman business logic için ayrılmıştır.

### Docker Yapılandırması
```
backend/docker-compose.yml        # PostgreSQL container yapılandırması
```

**Servisler:**
- PostgreSQL 
- Port: 5432
- Database: KatalogcuDb
- User: postgres
- Persistent volume: pgdata_new

---

## 🎨 Frontend (Angular)

```
frontend/katalogcu-frontend/      # Angular uygulaması (Henüz geliştirilme aşamasında)
```

**Teknolojiler:**
- Angular Framework (Planlanmış)
- TypeScript
- Port: 4200 (development)

**Not:** Frontend dizini mevcut ancak Angular projesinin kurulumu henüz tamamlanmamış.

---

## 🤖 YOLO Service (Python AI)

```
yolo-service/
├── api.py                        # Flask/FastAPI API endpoint
├── app/
│   └── main.py                   # Ana uygulama logic
├── best.pt                       # Eğitilmiş YOLO model dosyası
├── requirements.txt              # Python bağımlılıkları
├── .env                          # Ortam değişkenleri
└── .gitignore                    # Git ignore kuralları
```

**Özellikler:**
- YOLO (You Only Look Once) object detection
- REST API endpoint'leri
- Ürün tanıma ve koordinat belirleme
- Katalog sayfalarında otomatik hotspot oluşturma

---

## 📝 Solution Yapısı

```
backend/Katalogcu.sln             # .NET Solution dosyası
```

**Projeler:**
1. Katalogcu.API
2. Katalogcu.Application
3. Katalogcu.Domain
4. Katalogcu.Infrastructure

---

## 🔑 Önemli Özellikler

### Backend API Endpoints

#### Authentication
- `POST /api/auth/login` - Kullanıcı girişi
- `POST /api/auth/register` - Yeni kullanıcı kaydı

#### Catalogs
- `GET /api/catalogs` - Tüm katalogları listele
- `POST /api/catalogs` - Yeni katalog oluştur
- `GET /api/catalogs/{id}` - Katalog detayı
- `PUT /api/catalogs/{id}` - Katalog güncelle
- `DELETE /api/catalogs/{id}` - Katalog sil

#### Products
- `GET /api/products` - Ürünleri listele
- `POST /api/products` - Yeni ürün ekle
- `GET /api/products/{id}` - Ürün detayı
- `PUT /api/products/{id}` - Ürün güncelle
- `DELETE /api/products/{id}` - Ürün sil

#### Hotspots
- `GET /api/hotspots` - Hotspot'ları listele
- `POST /api/hotspots` - Yeni hotspot ekle
- `PUT /api/hotspots/{id}` - Hotspot güncelle
- `DELETE /api/hotspots/{id}` - Hotspot sil

#### Files
- `POST /api/files/upload` - Dosya yükleme
- `GET /api/files/{id}` - Dosya indirme

#### Users
- `GET /api/users` - Kullanıcıları listele
- `GET /api/users/{id}` - Kullanıcı detayı

---

## 🛠️ Teknoloji Stack

### Backend
- **Framework**: .NET 9.0
- **ORM**: Entity Framework Core
- **Veritabanı**: PostgreSQL
- **Authentication**: JWT Bearer
- **API Dokümantasyonu**: Swagger/OpenAPI
- **Mimari**: Clean Architecture

### Frontend
- **Framework**: Angular
- **Dil**: TypeScript

### AI Service
- **Dil**: Python
- **Framework**: Flask/FastAPI
- **AI Model**: YOLO (You Only Look Once)
- **Use Case**: Object Detection & Hotspot Generation

### DevOps
- **Containerization**: Docker
- **Database**: PostgreSQL (Docker)

---

## 📊 Veritabanı Migrations

1. **InitialCreate** (23 Kasım 2025)
   - İlk veritabanı yapısı

2. **AddCatalogDomain** (23 Kasım 2025)
   - Katalog domain modelleri eklendi

3. **AddPageNumberToProduct** (10 Aralık 2025)
   - Ürünlere sayfa numarası özelliği eklendi

4. **UpdateHotspotForYolo** (18 Aralık 2025)
   - YOLO entegrasyonu için Hotspot güncellemeleri

---

## 🚀 Çalıştırma

### Backend
```bash
cd backend/Katalogcu.API
dotnet restore
dotnet run
```

### Database
```bash
cd backend
docker-compose up -d
```

### Frontend
```bash
cd frontend/katalogcu-frontend
npm install
npm start
```

### YOLO Service
```bash
cd yolo-service
pip install -r requirements.txt
python api.py
```

---

## 📦 Dosya Sayıları

- **C# Dosyaları**: Controllers (6), Services (3), Entities (5), Migrations (4+)
- **Python Dosyaları**: API ve ML logic
- **Angular Projesi**: Tam frontend uygulaması
- **Config Dosyaları**: Docker, .NET project files, Python requirements

---

## ✅ Sonuç

**Evet, repodaki tüm dosyalar görülebiliyor ve erişilebilir durumda!**

Bu proje, modern web uygulama geliştirme standartlarına uygun olarak:
- Clean Architecture prensiplerine göre yapılandırılmış
- Mikroservis mimarisine uygun (Backend, Frontend, AI Service ayrımı)
- Docker ile containerize edilmiş
- AI/ML entegrasyonuna sahip (YOLO)
- REST API standardında endpoint'lere sahip

Tüm dosyalar `/home/runner/work/Katalogcu/Katalogcu` dizininde mevcuttur.
