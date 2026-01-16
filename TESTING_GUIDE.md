# Quick Start: Testing Backend-Partalog-AI Integration

## Prerequisites
- .NET 9 SDK installed
- Python 3.8+ installed
- YOLO model file: `partalog-ai/models/best.pt`

## Step 1: Start Partalog-AI Service

```bash
cd partalog-ai
pip install -r requirements.txt
python main.py
```

Expected output:
```
🚀 Partalog AI Service v2.0.0 başlatılıyor...
✅ YOLO Detector yüklendi
✅ OCR Reader yüklendi
🎯 Servis hazır!
📍 API Docs: http://localhost:8000/docs
```

## Step 2: Test Partalog-AI Health

```bash
curl -X GET http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "modelLoaded": true,
  "modelPath": "models/best.pt",
  "ocrLoaded": true
}
```

## Step 3: Test Partalog-AI Detection (Optional)

```bash
curl -X POST "http://localhost:8000/detect?min_confidence=0.5" \
  -F "file=@/path/to/test-image.jpg"
```

Expected response:
```json
{
  "success": true,
  "message": "X hotspot(s) detected",
  "filename": "test-image.jpg",
  "imageWidth": 1920,
  "imageHeight": 1080,
  "detectionCount": X,
  "processingTimeMs": 123.45,
  "detections": [
    {
      "left": 10.5,
      "top": 20.3,
      "width": 5.2,
      "height": 4.8,
      "confidence": 0.95,
      "label": "A123"
    }
  ]
}
```

## Step 4: Configure Backend

Create `backend/Katalogcu.API/appsettings.Development.json`:

```json
{
  "YoloService": {
    "BaseUrl": "http://localhost:8000",
    "ImageBaseUrl": "http://localhost:5000",
    "MinConfidence": 0.5
  }
}
```

Or use the existing `appsettings.example.json` as a template.

## Step 5: Start Backend Service

```bash
cd backend/Katalogcu.API
dotnet restore
dotnet run
```

Expected output:
```
Now listening on: http://localhost:5000
Application started. Press Ctrl+C to shut down.
```

## Step 6: Test Backend Health Check

The backend automatically checks YOLO service health on startup.

Look for logs like:
```
[Information] YOLO servisi sağlık kontrolü başarılı
```

## Step 7: Test End-to-End Integration

### Via Swagger UI:

1. Open: http://localhost:5000/swagger
2. Authenticate (if needed)
3. Find: `POST /api/hotspots/detect/{pageId}`
4. Execute with a valid pageId

### Via curl:

```bash
# First, create a catalog page with an image
# Then use the pageId:
curl -X POST "http://localhost:5000/api/hotspots/detect/{pageId}?minConfidence=0.5" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Expected response:
```json
{
  "message": "X hotspot tespit edildi ve kaydedildi",
  "pageId": "...",
  "detectedCount": X,
  "hotspots": [...]
}
```

## Troubleshooting

### "YOLO servisi çalışmıyor" Error:
- Check if partalog-ai is running on port 8000
- Verify: `curl http://localhost:8000/health`

### "Model yüklenmemiş" Error:
- Check if `partalog-ai/models/best.pt` exists
- Check partalog-ai logs for model loading errors

### Backend can't connect to Partalog-AI:
- Verify both services are running
- Check port conflicts (8000 and 5000)
- Check firewall settings
- Verify `appsettings.json` YoloService.BaseUrl

## API Documentation

- **Backend Swagger**: http://localhost:5000/swagger
- **Partalog-AI Docs**: http://localhost:8000/docs
- **Partalog-AI Test Page**: http://localhost:8000/static/test.html

## Integration Flow

```
User/Frontend
    ↓
    POST /api/hotspots/detect/{pageId}
    ↓
Backend (.NET)
    ↓ GET /health (check if YOLO ready)
    ↓ Download image
    ↓ POST /detect?min_confidence=X
    ↓
Partalog-AI (Python/FastAPI)
    ↓ YOLO detection
    ↓ OCR number reading
    ↓ Return camelCase response
    ↓
Backend (.NET)
    ↓ Parse response
    ↓ Convert to Hotspot entities
    ↓ Save to database
    ↓
User/Frontend
```

## Success Indicators

✅ Partalog-AI starts without errors  
✅ `/health` endpoint returns `{"modelLoaded": true}`  
✅ Backend logs show successful YOLO service health check  
✅ Hotspot detection creates records in database  
✅ Detected hotspots have correct coordinates (percentages)  
✅ OCR labels are read (if available)

## Next Steps

After successful testing:
1. Review and merge PR
2. Deploy to staging/production
3. Update production configuration
4. Monitor logs for any integration issues
5. Consider adding automated integration tests
