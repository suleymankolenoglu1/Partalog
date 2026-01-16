# Backend ve Partalog-AI Entegrasyon Kılavuzu

## Genel Bakış

Bu belge, Backend (.NET) ve Partalog-AI (Python/FastAPI) servisleri arasındaki entegrasyonu açıklar.

## Servis Mimarisi

```
┌─────────────────┐         ┌──────────────────┐
│   Backend       │◄────────┤   Partalog-AI    │
│   (.NET 9)      │ HTTP    │   (FastAPI)      │
│   Port: 5000    │─────────►  Port: 8000      │
└─────────────────┘         └──────────────────┘
```

## Endpoint'ler

### 1. Health Check Endpoint

**URL:** `GET http://localhost:8000/health`

**Backend Tarafından Kullanımı:**
- Backend başlangıçta ve YOLO servisi kullanmadan önce bu endpoint'i çağırır
- YOLO modelinin yüklenip yüklenmediğini kontrol eder

**Response:**
```json
{
  "status": "healthy",           // "healthy" veya "degraded"
  "modelLoaded": true,           // YOLO modeli yüklü mü?
  "modelPath": "models/best.pt", // Model dosyası yolu
  "ocrLoaded": true              // OCR yüklü mü?
}
```

**Backend Kod:**
```csharp
// YoloService.cs - IsHealthyAsync() metodu
var response = await _httpClient.GetAsync($"{yoloUrl}/health");
var health = JsonSerializer.Deserialize<YoloHealthResponse>(content);
return health?.ModelLoaded ?? false;
```

### 2. Hotspot Detection Endpoint

**URL:** `POST http://localhost:8000/detect?min_confidence=0.5`

**Backend Tarafından Kullanımı:**
- Backend, katalog sayfası görüntüsünü bu endpoint'e gönderir
- YOLO modeli görüntüdeki hotspot'ları tespit eder
- OCR varsa, hotspot'ların içindeki numaraları okur

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: `file` (görüntü dosyası)
- Query Parameter: `min_confidence` (0.0-1.0 arası, default: 0.5)

**Response:**
```json
{
  "success": true,
  "message": "3 hotspot(s) detected",
  "filename": "catalog-page.jpg",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "detectionCount": 3,
  "processingTimeMs": 123.45,
  "detections": [
    {
      "left": 10.5,      // Yüzde cinsinden (%)
      "top": 20.3,       // Yüzde cinsinden (%)
      "width": 5.2,      // Yüzde cinsinden (%)
      "height": 4.8,     // Yüzde cinsinden (%)
      "confidence": 0.95,
      "label": "A123"    // OCR ile okunan numara (varsa)
    }
  ],
  "error": null
}
```

**Backend Kod:**
```csharp
// YoloService.cs - DetectHotspotsAsync() metodu
var response = await _httpClient.PostAsync(
    $"{yoloUrl}/detect?min_confidence={minConfidence}", 
    content
);
var result = JsonSerializer.Deserialize<YoloDetectionResponse>(jsonResponse);
```

## Konfigürasyon

### Backend (appsettings.json)

```json
{
  "YoloService": {
    "BaseUrl": "http://localhost:8000",
    "ImageBaseUrl": "http://localhost:5000",
    "MinConfidence": 0.5
  }
}
```

**Not:** `appsettings.Development.json` dosyası local development için kullanılır ve `.gitignore`'da bulunur. `appsettings.example.json` dosyasını referans alarak oluşturulmalıdır.

### Partalog-AI (config.py)

```python
class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    YOLO_MODEL_PATH: str = "models/best.pt"
    YOLO_CONFIDENCE: float = 0.25
    YOLO_IMG_SIZE: int = 1280
```

## Servisler Arası İletişim Akışı

### Hotspot Tespiti Senaryosu:

1. **Kullanıcı İsteği:**
   - Frontend → Backend: `POST /api/hotspots/detect/{pageId}`

2. **Backend İşlemleri:**
   - Veritabanından sayfa bilgilerini çeker
   - YOLO servis health check yapar: `GET /health`
   - Sayfa görüntüsünü indirir
   - YOLO servisine gönderir: `POST /detect?min_confidence=X`

3. **Partalog-AI İşlemleri:**
   - Görüntüyü alır
   - YOLO modeli ile hotspot'ları tespit eder
   - Her hotspot için OCR ile numara okumayı dener
   - Backend-uyumlu formatta response döner

4. **Backend İşlemleri:**
   - Response'u parse eder
   - Hotspot entity'lere dönüştürür
   - **OCR ile okunan label'ı Product RefNo ile eşleştirir**
   - Eşleşme bulunursa `Hotspot.ProductId` set edilir
   - Veritabanına kaydeder
   - Frontend'e sonucu döner (eşleştirme sayısı dahil)

## Otomatik Ürün Eşleştirme

Backend, hotspot'lar tespit edildikten sonra OCR ile okunan numaraları otomatik olarak Product tablosu ile eşleştirir.

### Eşleştirme Mantığı:

```csharp
foreach (var hotspot in detectedHotspots)
{
    if (!string.IsNullOrEmpty(hotspot.Label))
    {
        if (int.TryParse(hotspot.Label, out int refNo))
        {
            var product = await _context.Products
                .FirstOrDefaultAsync(p => p.CatalogId == page.CatalogId 
                                       && p.RefNo == refNo);
            
            if (product != null)
            {
                hotspot.ProductId = product.Id;
            }
        }
    }
}
```

### Eşleştirme Senaryoları:

1. **Başarılı Eşleştirme:**
   - Hotspot Label: `"12"`
   - Product RefNo: `12`
   - Sonuç: `Hotspot.ProductId` set edilir ✅
   - Log: `✅ Hotspot label '12' → Product RefNo 12 (ProductId: ...)`

2. **Ürün Bulunamadı:**
   - Hotspot Label: `"99"`
   - Product RefNo: Yok
   - Sonuç: `Hotspot.ProductId = null`
   - Log: `⚠️ Hotspot label '99' için eşleşen ürün bulunamadı (RefNo: 99)`

3. **Label Sayı Değil:**
   - Hotspot Label: `"A1"` veya `"12-B"`
   - Sonuç: `Hotspot.ProductId = null`
   - Log: `ℹ️ Hotspot label 'A1' sayıya çevrilemedi, eşleştirme yapılmadı`

### Frontend Kullanımı:

Hotspot'a tıklandığında:
```javascript
// Hotspot'un ProductId'si varsa
if (hotspot.productId) {
    // Product detaylarını göster
    const product = await fetchProduct(hotspot.productId);
    displayProductDetails(product);
}
```

## Geriye Uyumluluk

Partalog-AI, iki farklı endpoint sağlar:

1. **Backend-Compatible:** `/detect` (camelCase response)
   - Backend (.NET) tarafından kullanılır
   - Response field'ları: `imageWidth`, `detectionCount`, `detections`

2. **Legacy/Alternative:** `/api/detect` (snake_case response)
   - Diğer istemciler tarafından kullanılabilir
   - Response field'ları: `image_width`, `hotspot_count`, `hotspots`

## Hata Yönetimi

### Backend Tarafında:

```csharp
try
{
    var detectedHotspots = await _yoloService.DetectHotspotsAsync(...);
}
catch (HttpRequestException ex)
{
    // YOLO servisi ile iletişim hatası
    return StatusCode(503, new { error = "YOLO servisi ile iletişim kurulamadı" });
}
```

### Partalog-AI Tarafında:

```python
if detector is None:
    return BackendCompatibleResponse(
        success=False,
        message="YOLO model not loaded",
        error="YOLO model not loaded. Check models/best.pt file."
    )
```

## Test Senaryoları

### 1. Health Check Testi:

```bash
curl -X GET http://localhost:8000/health
```

**Beklenen Response:**
```json
{
  "status": "healthy",
  "modelLoaded": true,
  "modelPath": "models/best.pt",
  "ocrLoaded": true
}
```

### 2. Hotspot Detection Testi:

```bash
curl -X POST "http://localhost:8000/detect?min_confidence=0.5" \
  -F "file=@test-image.jpg"
```

**Beklenen Response:**
```json
{
  "success": true,
  "message": "X hotspot(s) detected",
  "filename": "test-image.jpg",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "detectionCount": X,
  "processingTimeMs": 123.45,
  "detections": [...]
}
```

### 3. Backend Entegrasyon Testi (Ürün Eşleştirme ile):

**Ön Koşullar:**
1. Veritabanında bir katalog oluşturun
2. Kataloğa ürünler ekleyin (RefNo: 12, 25, 30, vb.)
3. Kataloga PDF yükleyin (sayfalar oluşsun)

**Test:**
```bash
curl -X POST "http://localhost:5000/api/hotspots/detect/{pageId}?minConfidence=0.5" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Beklenen Response:**
```json
{
  "message": "5 hotspot tespit edildi ve kaydedildi (3 ürün ile eşleştirildi)",
  "pageId": "...",
  "detectedCount": 5,
  "matchedCount": 3,
  "hotspots": [
    {
      "id": "...",
      "label": "12",
      "productId": "...",  // ✅ Eşleşti!
      "isAiDetected": true,
      "aiConfidence": 0.95
    },
    {
      "id": "...",
      "label": "99",
      "productId": null,  // ⚠️ Ürün bulunamadı
      "isAiDetected": true,
      "aiConfidence": 0.88
    }
  ]
}
```

**Backend Log Çıktıları:**
```
🔍 Sayfa ... için YOLO ile hotspot tespiti başlıyor
✅ 5 hotspot tespit edildi
✅ Hotspot label '12' → Product RefNo 12 (ProductId: ...)
✅ Hotspot label '25' → Product RefNo 25 (ProductId: ...)
✅ Hotspot label '30' → Product RefNo 30 (ProductId: ...)
⚠️ Hotspot label '99' için eşleşen ürün bulunamadı (RefNo: 99)
ℹ️ Hotspot label 'A1' sayıya çevrilemedi, eşleştirme yapılmadı
✅ 5 hotspot başarıyla kaydedildi, 3 ürün ile eşleştirildi
```

## Servisler Çalıştırma

### 1. Partalog-AI Servisi:

```bash
cd partalog-ai
pip install -r requirements.txt
python main.py
```

Servis `http://localhost:8000` adresinde başlar.

### 2. Backend Servisi:

```bash
cd backend/Katalogcu.API
dotnet restore
dotnet run
```

Servis `http://localhost:5000` adresinde başlar.

### 3. Swagger/API Docs:

- Backend: http://localhost:5000/swagger
- Partalog-AI: http://localhost:8000/docs

## Sorun Giderme

### "YOLO servisi çalışmıyor" Hatası:

1. Partalog-AI servisinin çalıştığını kontrol edin
2. `/health` endpoint'ine istek atarak modelin yüklü olduğunu doğrulayın
3. `models/best.pt` dosyasının mevcut olduğunu kontrol edin

### "Model yüklenmemiş" Hatası:

1. `partalog-ai/models/best.pt` dosyasının var olduğunu kontrol edin
2. Dosya izinlerini kontrol edin
3. Partalog-AI loglarında YOLO model yükleme hatalarını kontrol edin

### Backend-Partalog-AI İletişim Hatası:

1. Her iki servisin de çalıştığını kontrol edin
2. Port çakışması olmadığını kontrol edin
3. Firewall kurallarını kontrol edin
4. `appsettings.json` içindeki URL'leri kontrol edin

## İlgili Dosyalar

### Backend:
- `backend/Katalogcu.API/Services/YoloService.cs` - YOLO servisi iletişim katmanı
- `backend/Katalogcu.API/Controllers/HotspotsController.cs` - Hotspot endpoint'leri
- `backend/Katalogcu.API/appsettings.example.json` - Konfigürasyon örneği

### Partalog-AI:
- `partalog-ai/main.py` - Ana uygulama ve backend-compatible endpoint'ler
- `partalog-ai/api/hotspot.py` - Legacy hotspot detection endpoint'i
- `partalog-ai/config.py` - Konfigürasyon
- `partalog-ai/core/detector.py` - YOLO detection logic
- `partalog-ai/core/ocr.py` - OCR logic

## Güvenlik Notları

- `appsettings.Development.json` dosyası `.gitignore`'da bulunur ve commit edilmemelidir
- Üretim ortamında, servislerin HTTPS üzerinden iletişim kurması önerilir
- API key/token tabanlı kimlik doğrulama eklenebilir
- Rate limiting uygulanabilir
