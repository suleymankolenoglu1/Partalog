using Katalogcu.Domain.Entities;
using System.Net.Http.Headers;
using System.Text.Json;

namespace Katalogcu.API.Services
{
    /// <summary>
    /// YOLO AI servisi ile iletişim kuran servis
    /// Katalog sayfalarındaki hotspot'ları otomatik tespit eder
    /// </summary>
    public class YoloService
    {
        private readonly HttpClient _httpClient;
        private readonly IConfiguration _configuration;
        private readonly ILogger<YoloService> _logger;

        public YoloService(HttpClient httpClient, IConfiguration configuration, ILogger<YoloService> logger)
        {
            _httpClient = httpClient;
            _configuration = configuration;
            _logger = logger;
        }

        /// <summary>
        /// Bir görüntü dosyasındaki hotspot'ları YOLO ile tespit eder
        /// </summary>
        /// <param name="imageUrl">Analiz edilecek görüntünün URL'i</param>
        /// <param name="pageId">Hotspot'ların bağlanacağı sayfa ID'si</param>
        /// <param name="minConfidence">Minimum güven eşiği (0.0 - 1.0)</param>
        /// <returns>Tespit edilen hotspot listesi</returns>
        public async Task<List<Hotspot>> DetectHotspotsAsync(string imageUrl, Guid pageId, double minConfidence = 0.5)
        {
            // Input validation
            if (string.IsNullOrWhiteSpace(imageUrl))
            {
                throw new ArgumentException("Image URL cannot be null or empty", nameof(imageUrl));
            }

            if (minConfidence < 0.0 || minConfidence > 1.0)
            {
                throw new ArgumentOutOfRangeException(nameof(minConfidence), "Confidence must be between 0.0 and 1.0");
            }

            try
            {
                _logger.LogInformation("🔍 YOLO ile hotspot tespiti başlıyor: {ImageUrl}", imageUrl);

                // Görüntüyü indir
                byte[] imageBytes = await DownloadImageAsync(imageUrl);

                // YOLO API'ye gönder
                var detectionResponse = await SendToYoloApiAsync(imageBytes, Path.GetFileName(imageUrl), minConfidence);

                if (!detectionResponse.Success)
                {
                    _logger.LogError("❌ YOLO tespit başarısız: {Error}", detectionResponse.Error);
                    return new List<Hotspot>();
                }

                // Hotspot entity'lere dönüştür
                var hotspots = detectionResponse.Detections.Select(d => new Hotspot
                {
                    PageId = pageId,
                    Left = d.Left,
                    Top = d.Top,
                    Width = d.Width,
                    Height = d.Height,
                    Label = d.Label, // YOLO numara okuyamaz, null olacak
                    IsAiDetected = true,
                    AiConfidence = d.Confidence,
                    CreatedDate = DateTime.UtcNow
                }).ToList();

                _logger.LogInformation("✅ {Count} hotspot tespit edildi", hotspots.Count);
                return hotspots;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ YOLO hotspot tespit hatası");
                throw;
            }
        }

        /// <summary>
        /// YOLO servisinin sağlık durumunu kontrol eder
        /// </summary>
        public async Task<bool> IsHealthyAsync()
        {
            try
            {
                var yoloUrl = _configuration["YoloService:BaseUrl"] ?? "http://localhost:8000";
                var response = await _httpClient.GetAsync($"{yoloUrl}/health");
                
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync();
                    var health = JsonSerializer.Deserialize<YoloHealthResponse>(content, new JsonSerializerOptions 
                    { 
                        PropertyNameCaseInsensitive = true 
                    });
                    
                    return health?.ModelLoaded ?? false;
                }
                
                return false;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "YOLO servis sağlık kontrolü başarısız");
                return false;
            }
        }

        #region Private Methods

        private async Task<byte[]> DownloadImageAsync(string imageUrl)
        {
            try
            {
                // URL'yi tam path'e çevir
                string fullUrl = imageUrl;
                if (!imageUrl.StartsWith("http"))
                {
                    // Göreceli URL ise, tam path oluştur
                    var baseUrl = _configuration["YoloService:ImageBaseUrl"] ?? "http://localhost:5000";
                    fullUrl = $"{baseUrl}/{imageUrl.TrimStart('/')}";
                }

                _logger.LogInformation("📥 Görüntü indiriliyor: {Url}", fullUrl);
                
                var imageBytes = await _httpClient.GetByteArrayAsync(fullUrl);
                
                _logger.LogInformation("✅ Görüntü indirildi: {Size} bytes", imageBytes.Length);
                return imageBytes;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ Görüntü indirme hatası: {Url}", imageUrl);
                throw;
            }
        }

        private async Task<YoloDetectionResponse> SendToYoloApiAsync(byte[] imageBytes, string fileName, double minConfidence)
        {
            var yoloUrl = _configuration["YoloService:BaseUrl"] ?? "http://localhost:8000";
            
            using var content = new MultipartFormDataContent();
            var fileContent = new ByteArrayContent(imageBytes);
            fileContent.Headers.ContentType = MediaTypeHeaderValue.Parse("image/jpeg");
            content.Add(fileContent, "file", fileName);

            _logger.LogInformation("📤 YOLO API'ye gönderiliyor: {Url}/detect", yoloUrl);
            
            var response = await _httpClient.PostAsync($"{yoloUrl}/detect?min_confidence={minConfidence}", content);
            
            if (!response.IsSuccessStatusCode)
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                _logger.LogError("YOLO API hatası: {StatusCode} - {Error}", response.StatusCode, errorContent);
                throw new HttpRequestException($"YOLO API hatası: {response.StatusCode}");
            }

            var jsonResponse = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<YoloDetectionResponse>(jsonResponse, new JsonSerializerOptions 
            { 
                PropertyNameCaseInsensitive = true 
            });

            return result ?? new YoloDetectionResponse { Success = false, Error = "Yanıt parse edilemedi" };
        }

        #endregion

        #region Response Models

        private class YoloDetectionResponse
        {
            public bool Success { get; set; }
            public string Message { get; set; } = string.Empty;
            public string Filename { get; set; } = string.Empty;
            public int ImageWidth { get; set; }
            public int ImageHeight { get; set; }
            public int DetectionCount { get; set; }
            public double ProcessingTimeMs { get; set; }
            public List<YoloHotspotDetection> Detections { get; set; } = new();
            public string? Error { get; set; }
        }

        private class YoloHotspotDetection
        {
            public double Left { get; set; }
            public double Top { get; set; }
            public double Width { get; set; }
            public double Height { get; set; }
            public double Confidence { get; set; }
            public string? Label { get; set; }
        }

        private class YoloHealthResponse
        {
            public string Status { get; set; } = string.Empty;
            public bool ModelLoaded { get; set; }
            public string ModelPath { get; set; } = string.Empty;
        }

        #endregion
    }
}
