# YOLO Servisi Backend Entegrasyonu

## Genel Bakış

YOLO (You Only Look Once) AI servisi artık Katalogcu backend'i ile tamamen entegre edilmiştir. Bu entegrasyon sayesinde katalog sayfalarındaki ürünlerin konumları otomatik olarak tespit edilebilir ve hotspot'lar oluşturulabilir.

## Mimari

```
┌─────────────────┐      HTTP      ┌──────────────────┐      HTTP      ┌─────────────────┐
│                 │ ───────────────>│                  │ ───────────────>│                 │
│  Frontend       │                 │  .NET Backend    │                 │  YOLO Service   │
│  (Angular)      │<────────────────│  (Katalogcu.API) │<────────────────│  (Python/       │
│                 │                 │                  │                 │   FastAPI)      │
└─────────────────┘                 └──────────────────┘                 └─────────────────┘
                                            │
                                            v
                                    ┌──────────────┐
                                    │  PostgreSQL  │
                                    └──────────────┘
```

## Yeni Bileşenler

### 1. YoloService.cs

**Konum:** `backend/Katalogcu.API/Services/YoloService.cs`

Backend'den YOLO servisi ile iletişim kuran servis sınıfı.

**Yetenekleri:**
- Görüntü indirme ve YOLO API'ye gönderme
- YOLO yanıtlarını Hotspot entity'lere dönüştürme
- Servis sağlık kontrolü
- Hata yönetimi ve loglama

**Kullanım:**
```csharp
var hotspots = await _yoloService.DetectHotspotsAsync(imageUrl, pageId, minConfidence: 0.5);
```

### 2. HotspotsController - Yeni Endpoint

**Endpoint:** `POST /api/hotspots/detect/{pageId}`

**Parametreler:**
- `pageId` (path): Analiz edilecek sayfa ID'si
- `minConfidence` (query, optional): Minimum güven eşiği (0.0-1.0, varsayılan: 0.5)

**Yanıt:**
```json
{
  "message": "5 hotspot tespit edildi ve kaydedildi",
  "pageId": "guid",
  "detectedCount": 5,
  "hotspots": [
    {
      "id": "guid",
      "pageId": "guid",
      "left": 10.5,
      "top": 20.3,
      "width": 5.2,
      "height": 4.8,
      "label": null,
      "isAiDetected": true,
      "aiConfidence": 0.95,
      "createdDate": "2025-12-19T19:00:00Z"
    }
  ]
}
```

**Hata Durumları:**
- `404`: Sayfa bulunamadı
- `400`: Sayfanın görüntüsü yok
- `503`: YOLO servisi çalışmıyor
- `500`: İç hata

### 3. Yapılandırma

**appsettings.json:**
```json
{
  "YoloService": {
    "BaseUrl": "http://localhost:8000",
    "ImageBaseUrl": "http://localhost:5000",
    "MinConfidence": 0.5
  }
}
```

**Açıklamalar:**
- `BaseUrl`: YOLO servisinin çalıştığı adres
- `ImageBaseUrl`: Görüntülerin indirileceği base URL
- `MinConfidence`: Varsayılan güven eşiği

## Kurulum ve Çalıştırma

### 1. YOLO Servisini Başlatın

```bash
cd yolo-service
pip install -r requirements.txt
python api.py
```

YOLO servisi `http://localhost:8000` adresinde çalışacaktır.

### 2. Backend Yapılandırması

`appsettings.json` dosyasını oluşturun:

```bash
cd backend/Katalogcu.API
cp appsettings.example.json appsettings.json
```

Gerekli değerleri düzenleyin (veritabanı, JWT, YOLO URL'leri).

### 3. Backend'i Başlatın

```bash
cd backend/Katalogcu.API
dotnet restore
dotnet run
```

Backend `http://localhost:5000` adresinde çalışacaktır.

## Kullanım Senaryoları

### Senaryo 1: Otomatik Hotspot Tespiti

1. Katalog yükleyin ve sayfalar oluşturulacaktır
2. Bir sayfa seçin ve ID'sini alın
3. Otomatik tespit endpoint'ini çağırın:

```bash
curl -X POST "http://localhost:5000/api/hotspots/detect/{pageId}?minConfidence=0.6" \
  -H "Authorization: Bearer {token}"
```

4. Tespit edilen hotspot'lar otomatik olarak veritabanına kaydedilir
5. Frontend üzerinden görüntüleyebilir ve düzenleyebilirsiniz

### Senaryo 2: Manuel Hotspot Ekleme

Otomatik tespitin yanında manuel hotspot ekleme de desteklenir:

```bash
curl -X POST "http://localhost:5000/api/hotspots" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "pageId": "guid",
    "left": 10.0,
    "top": 20.0,
    "width": 5.0,
    "height": 5.0,
    "label": "12",
    "isAiDetected": false
  }'
```

## API Akış Diyagramı

```
┌──────────┐
│ Frontend │
└────┬─────┘
     │ POST /api/hotspots/detect/{pageId}
     v
┌────────────────┐
│ Backend        │
│ (Hotspots      │
│  Controller)   │
└────┬───────────┘
     │
     v
┌────────────────┐
│ YoloService    │
│ - Görüntü indir│
│ - YOLO'ya gönder
└────┬───────────┘
     │ HTTP POST /detect
     v
┌────────────────┐
│ YOLO Service   │
│ (Python/FastAPI)│
│ - YOLO inference
│ - Koordinatları döndür
└────┬───────────┘
     │ JSON Response
     v
┌────────────────┐
│ YoloService    │
│ - Parse response│
│ - Entity'lere dönüştür
└────┬───────────┘
     │
     v
┌────────────────┐
│ Database       │
│ (PostgreSQL)   │
│ - Hotspot kaydet
└────┬───────────┘
     │
     v
┌────────────────┐
│ Frontend       │
│ - Sonuçları göster
└────────────────┘
```

## Loglama

Backend, YOLO entegrasyonu için detaylı loglar üretir:

```
🔍 YOLO ile hotspot tespiti başlıyor: /uploads/catalog-123/page-1.jpg
📥 Görüntü indiriliyor: http://localhost:5000/uploads/catalog-123/page-1.jpg
✅ Görüntü indirildi: 245678 bytes
📤 YOLO API'ye gönderiliyor: http://localhost:8000/detect
✅ 5 hotspot tespit edildi
```

## Güvenlik

- YOLO endpoint'leri JWT authentication gerektirir
- Görüntü URL'leri doğrulanır
- YOLO servis sağlığı kontrol edilir
- HTTP timeout'lar yapılandırılabilir

## Test

### Manuel Test

1. YOLO servisinin sağlığını kontrol edin:
```bash
curl http://localhost:8000/health
```

2. Backend'in YOLO ile iletişimini test edin:
```bash
# Önce login olun ve token alın
TOKEN=$(curl -X POST "http://localhost:5000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test123"}' | jq -r '.token')

# Hotspot tespiti yapın
curl -X POST "http://localhost:5000/api/hotspots/detect/{pageId}" \
  -H "Authorization: Bearer $TOKEN"
```

## Sorun Giderme

### YOLO servisi çalışmıyor
```
❌ YOLO servisi ile iletişim kurulamadı
```
**Çözüm:** `python api.py` ile YOLO servisini başlatın.

### Model yüklenmemiş
```
❌ YOLO servisi çalışmıyor veya model yüklenmemiş
```
**Çözüm:** `best.pt` dosyasının `yolo-service/` dizininde olduğundan emin olun.

### Görüntü indirilemedi
```
❌ Görüntü indirme hatası
```
**Çözüm:** `YoloService:ImageBaseUrl` yapılandırmasını kontrol edin.

## İleri Geliştirmeler

- [ ] Batch processing (birden fazla sayfa aynı anda)
- [ ] OCR entegrasyonu (hotspot label'ları için)
- [ ] Tespit sonuçlarını önizleme endpoint'i
- [ ] Güven eşiğine göre otomatik onay
- [ ] Performans metrikleri ve monitoring

## Kaynaklar

- [YOLO Servisi API Dokümantasyonu](http://localhost:8000/docs)
- [Backend API Dokümantasyonu](http://localhost:5000/swagger)
- [PROJE_YAPISI.md](../../PROJE_YAPISI.md)
