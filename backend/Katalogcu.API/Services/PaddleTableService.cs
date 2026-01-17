using System. Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;
using Katalogcu.Domain. Entities;

namespace Katalogcu.API. Services
{
    /// <summary>
    /// PaddleOCR Python servisi ile iletişim kuran servis
    /// PDF ve görüntülerden tablo okuma işlemlerini gerçekleştirir
    /// </summary>
    public class PaddleTableService
    {
        private readonly HttpClient _httpClient;
        private readonly IConfiguration _configuration;
        private readonly ILogger<PaddleTableService> _logger;
        private readonly IWebHostEnvironment _env;

        public PaddleTableService(
            HttpClient httpClient,
            IConfiguration configuration,
            ILogger<PaddleTableService> logger,
            IWebHostEnvironment env)
        {
            _httpClient = httpClient;
            _configuration = configuration;
            _logger = logger;
            _env = env;

            // Timeout ayarı - tablo okuma uzun sürebilir
            _httpClient.Timeout = TimeSpan.FromMinutes(2);
        }

        #region Public Methods

        /// <summary>
        /// Katalog sayfasını analiz eder
        /// </summary>
        public async Task<(List<Product> products, List<Hotspot> hotspots)> AnalyzeCatalogPageAsync(
            string pdfFileName,
            int tablePageNumber,
            int imagePageNumber,
            string imageFilePath,
            Guid catalogId,
            Guid imagePageId,
            RectObj tableRect,
            RectObj imageRect)
        {
            var products = new List<Product>();
            var hotspots = new List<Hotspot>();
            var foundRefNumbers = new HashSet<int>();

            _logger.LogInformation("🐼 PaddleOCR Analizi Başlıyor");
            _logger.LogInformation("   📋 Tablo Sayfası: {TablePage}, Resim Sayfası: {ImagePage}",
                tablePageNumber, imagePageNumber);

            try
            {
                // ADIM 1: PDF'den tablo çıkar
                var webRoot = _env.WebRootPath ??  Path.Combine(Directory.GetCurrentDirectory(), "wwwroot");
                var fullPdfPath = ResolvePdfPath(webRoot, pdfFileName);

                if (string.IsNullOrEmpty(fullPdfPath))
                {
                    _logger.LogError("❌ PDF dosyası bulunamadı:  {FileName}", pdfFileName);
                    return (products, hotspots);
                }

                // Tablo çıkarma
                var tableProducts = await ExtractTableFromPdfAsync(
                    fullPdfPath,
                    tablePageNumber,
                    catalogId,
                    tableRect
                );

                products.AddRange(tableProducts);
                
                // RefNo'ları topla (Label olarak kullanılacak)
                foundRefNumbers = tableProducts
                    .Where(p => p.RefNo > 0)
                    .Select(p => p.RefNo)
                    .ToHashSet();

                _logger.LogInformation("   📦 Tablodan {Count} ürün çıkarıldı", products.Count);

                // ADIM 2: Hotspot tespiti (görüntüden numara okuma)
                if (foundRefNumbers.Count > 0 && ! string.IsNullOrEmpty(imageFilePath))
                {
                    var fullImagePath = ResolveImagePath(webRoot, imageFilePath);

                    if (! string.IsNullOrEmpty(fullImagePath))
                    {
                        hotspots = await DetectHotspotsFromImageAsync(
                            fullImagePath,
                            imagePageId,
                            imageRect,
                            foundRefNumbers
                        );

                        _logger.LogInformation("   🎯 {Count} hotspot oluşturuldu", hotspots.Count);
                    }
                }

                _logger.LogInformation("✅ PaddleOCR Analizi Tamamlandı:  {Products} ürün, {Hotspots} hotspot",
                    products.Count, hotspots.Count);

                return (products, hotspots);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "❌ PaddleOCR Analiz Hatası");
                throw;
            }
        }

        /// <summary>
        /// PDF dosyasından tablo çıkarır
        /// </summary>
        public async Task<List<Product>> ExtractTableFromPdfAsync(
            string pdfPath,
            int pageNumber,
            Guid catalogId,
            RectObj?  tableRect = null)
        {
            if (! File.Exists(pdfPath))
            {
                _logger.LogError("PDF dosyası bulunamadı:  {Path}", pdfPath);
                return new List<Product>();
            }

            try
            {
                _logger.LogInformation("📄 PDF'den tablo çıkarılıyor:  Sayfa {Page}", pageNumber);

                var baseUrl = GetPaddleServiceUrl();

                // Multipart form data oluştur
                using var content = new MultipartFormDataContent();

                var fileBytes = await File.ReadAllBytesAsync(pdfPath);
                var fileContent = new ByteArrayContent(fileBytes);
                fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
                content.Add(fileContent, "file", Path.GetFileName(pdfPath));

                // Query parametreleri
                var queryParams = $"page_number={pageNumber}";

                if (tableRect != null)
                {
                    queryParams += $"&table_x={tableRect.X}&table_y={tableRect.Y}&table_w={tableRect. W}&table_h={tableRect.H}";
                }

                var response = await _httpClient.PostAsync(
                    $"{baseUrl}/api/table/extract-table? {queryParams}",
                    content
                );

                if (!response. IsSuccessStatusCode)
                {
                    var error = await response.Content.ReadAsStringAsync();
                    _logger.LogError("PaddleOCR API hatası: {Status} - {Error}", response.StatusCode, error);
                    return new List<Product>();
                }

                var json = await response.Content.ReadAsStringAsync();
                var result = JsonSerializer.Deserialize<TableExtractionResponse>(json, GetJsonOptions());

                if (result?. Success != true)
                {
                    _logger.LogWarning("PaddleOCR başarısız: {Message}", result?.Message);
                    return new List<Product>();
                }

                // Ürünleri dönüştür
                var products = new List<Product>();
                var seenRefs = new HashSet<int>();

                foreach (var table in result.Tables ??  new List<TableResultDto>())
                {
                    foreach (var product in table.Products ?? new List<ProductDto>())
                    {
                        // Duplicate kontrolü
                        if (product.RefNumber > 0 && seenRefs.Contains(product. RefNumber))
                            continue;

                        products.Add(new Product
                        {
                            Id = Guid.NewGuid(),
                            CatalogId = catalogId,
                            Code = product. PartCode ??  "",
                            Name = product. PartName ?? "",
                            Category = "Genel",
                            Price = 0,
                            StockQuantity = 10,
                            CreatedDate = DateTime.UtcNow,
                            PageNumber = pageNumber. ToString(),
                            RefNo = product.RefNumber,
                            Description = product.RefNumber > 0 ? $"Ref:  {product.RefNumber}" : ""
                        });

                        if (product.RefNumber > 0)
                            seenRefs.Add(product.RefNumber);
                    }
                }

                _logger.LogInformation("✅ {Count} ürün çıkarıldı (Sayfa {Page})", products.Count, pageNumber);
                return products;
            }
            catch (HttpRequestException ex)
            {
                _logger.LogError(ex, "PaddleOCR servise bağlanılamadı.  Servis çalışıyor mu?");
                throw new InvalidOperationException("PaddleOCR servisi yanıt vermiyor", ex);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Tablo çıkarma hatası");
                throw;
            }
        }

        /// <summary>
        /// Görüntüden hotspot tespiti yapar (OCR ile numara okuma)
        /// Hotspot entity'nizin yapısına uygun:  Left, Top, Width, Height, Label
        /// </summary>
        public async Task<List<Hotspot>> DetectHotspotsFromImageAsync(
            string imagePath,
            Guid pageId,
            RectObj imageRect,
            HashSet<int> expectedRefNumbers)
        {
            var hotspots = new List<Hotspot>();

            if (!File.Exists(imagePath))
            {
                _logger.LogWarning("Görüntü dosyası bulunamadı:  {Path}", imagePath);
                return hotspots;
            }

            try
            {
                _logger.LogInformation("🔍 Görüntüden metin okunuyor: {Path}", imagePath);

                var baseUrl = GetPaddleServiceUrl();

                using var content = new MultipartFormDataContent();
                var fileBytes = await File. ReadAllBytesAsync(imagePath);
                var fileContent = new ByteArrayContent(fileBytes);
                fileContent.Headers. ContentType = new MediaTypeHeaderValue("image/png");
                content.Add(fileContent, "file", Path.GetFileName(imagePath));

                var response = await _httpClient.PostAsync($"{baseUrl}/api/table/ocr-image", content);

                if (!response. IsSuccessStatusCode)
                {
                    var error = await response.Content.ReadAsStringAsync();
                    _logger.LogError("OCR API hatası: {Status} - {Error}", response.StatusCode, error);
                    return hotspots;
                }

                var json = await response.Content. ReadAsStringAsync();
                var result = JsonSerializer.Deserialize<OcrResponse>(json, GetJsonOptions());

                if (result?.Success != true)
                {
                    _logger.LogWarning("OCR başarısız: {Message}", result?.Message);
                    return hotspots;
                }

                // Görüntü boyutları
                int imageWidth = result.ImageWidth > 0 ? result.ImageWidth : 1000;
                int imageHeight = result.ImageHeight > 0 ?  result.ImageHeight : 1000;

                foreach (var text in result. Texts ??  new List<OcrTextDto>())
                {
                    // Sadece sayısal değerleri al
                    if (! int.TryParse(text. Text?. Trim(), out int refNumber))
                        continue;

                    // Beklenen ref numaralarında mı?
                    if (! expectedRefNumbers.Contains(refNumber))
                        continue;

                    // Bbox'tan koordinatları hesapla
                    // Bbox formatı: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                    double left = 0, top = 0, width = 0, height = 0;

                    if (text. Bbox != null && text.Bbox.Count >= 4)
                    {
                        double x1 = text.Bbox[0][0];
                        double y1 = text.Bbox[0][1];
                        double x2 = text.Bbox[2][0];
                        double y2 = text.Bbox[2][1];

                        // Yüzdeye çevir (imageRect içinde pozisyon)
                        left = imageRect.X + ((x1 / imageWidth) * imageRect.W);
                        top = imageRect.Y + ((y1 / imageHeight) * imageRect.H);
                        width = ((x2 - x1) / imageWidth) * imageRect.W;
                        height = ((y2 - y1) / imageHeight) * imageRect.H;
                    }
                    else
                    {
                        // Bbox yoksa center'dan hesapla
                        left = imageRect.X + ((text.CenterX / imageWidth) * imageRect.W) - 1;
                        top = imageRect.Y + ((text.CenterY / imageHeight) * imageRect.H) - 1;
                        width = 2;  // Varsayılan küçük kutu
                        height = 2;
                    }

                    // Sınırları kontrol et
                    left = Math. Clamp(left, 0, 100);
                    top = Math.Clamp(top, 0, 100);
                    width = Math.Clamp(width, 0.5, 100 - left);
                    height = Math.Clamp(height, 0.5, 100 - top);

                    hotspots.Add(new Hotspot
                    {
                        Id = Guid.NewGuid(),
                        PageId = pageId,
                        Left = left,
                        Top = top,
                        Width = width,
                        Height = height,
                        Label = refNumber.ToString(),  // Ref numarası string olarak
                        IsAiDetected = true,
                        AiConfidence = text.Confidence,
                        CreatedDate = DateTime.UtcNow
                    });
                }

                _logger.LogInformation("✅ {Count} hotspot oluşturuldu", hotspots.Count);
                return hotspots;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Hotspot tespit hatası");
                return hotspots;
            }
        }

        /// <summary>
        /// PaddleOCR servisinin sağlık durumunu kontrol eder
        /// </summary>
        public async Task<bool> IsHealthyAsync()
        {
            try
            {
                var baseUrl = GetPaddleServiceUrl();
                var response = await _httpClient.GetAsync($"{baseUrl}/health");

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    var health = JsonSerializer.Deserialize<HealthResponse>(json, GetJsonOptions());

                    return health?. Models?.TableReader ??  false;
                }

                return false;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "PaddleOCR sağlık kontrolü başarısız");
                return false;
            }
        }

        /// <summary>
        /// Servis bilgilerini döndürür
        /// </summary>
        public async Task<TableServiceInfo? > GetServiceInfoAsync()
        {
            try
            {
                var baseUrl = GetPaddleServiceUrl();
                var response = await _httpClient.GetAsync($"{baseUrl}/api/table/table-info");

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    return JsonSerializer.Deserialize<TableServiceInfo>(json, GetJsonOptions());
                }

                return null;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Servis bilgisi alınamadı");
                return null;
            }
        }

        #endregion

        #region Private Methods

        private string GetPaddleServiceUrl()
        {
            return _configuration["PaddleService:BaseUrl"] ?? "http://localhost:8000";
        }

        private string?  ResolvePdfPath(string webRoot, string pdfFileName)
        {
            var paths = new[]
            {
                Path.Combine(webRoot, "uploads", pdfFileName),
                Path.Combine(webRoot, "uploads", "pdfs", pdfFileName),
                Path.Combine(webRoot, "wwwroot", "uploads", pdfFileName),
                Path.Combine(Directory.GetCurrentDirectory(), "wwwroot", "uploads", pdfFileName)
            };

            foreach (var path in paths)
            {
                if (File.Exists(path))
                    return path;
            }

            return null;
        }

        private string?  ResolveImagePath(string webRoot, string imageFilePath)
        {
            var fileName = Path.GetFileName(imageFilePath);

            var paths = new[]
            {
                imageFilePath,
                Path. Combine(webRoot, "uploads", "pages", fileName),
                Path. Combine(webRoot, "wwwroot", "uploads", "pages", fileName),
                Path. Combine(Directory.GetCurrentDirectory(), "wwwroot", "uploads", "pages", fileName)
            };

            foreach (var path in paths)
            {
                if (File.Exists(path))
                    return path;
            }

            return null;
        }

        private static JsonSerializerOptions GetJsonOptions()
        {
            return new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true,
                PropertyNamingPolicy = JsonNamingPolicy. SnakeCaseLower
            };
        }

        #endregion

        #region Response Models

        private class TableExtractionResponse
        {
            public bool Success { get; set; }
            public string?  Message { get; set; }
            
            [JsonPropertyName("page_number")]
            public int PageNumber { get; set; }
            
            [JsonPropertyName("table_count")]
            public int TableCount { get; set; }
            
            [JsonPropertyName("total_products")]
            public int TotalProducts { get; set; }
            
            [JsonPropertyName("processing_time_ms")]
            public double ProcessingTimeMs { get; set; }
            
            public List<TableResultDto>? Tables { get; set; }
        }

        private class TableResultDto
        {
            [JsonPropertyName("table_index")]
            public int TableIndex { get; set; }
            
            [JsonPropertyName("row_count")]
            public int RowCount { get; set; }
            
            [JsonPropertyName("product_count")]
            public int ProductCount { get; set; }
            
            public List<ProductDto>? Products { get; set; }
            public List<double>? Bbox { get; set; }
        }

        private class ProductDto
        {
            [JsonPropertyName("ref_number")]
            public int RefNumber { get; set; }

            [JsonPropertyName("part_code")]
            public string?  PartCode { get; set; }

            [JsonPropertyName("part_name")]
            public string? PartName { get; set; }

            public double Confidence { get; set; }
        }

        private class OcrResponse
        {
            public bool Success { get; set; }
            public string? Message { get; set; }
            
            [JsonPropertyName("text_count")]
            public int TextCount { get; set; }
            
            [JsonPropertyName("processing_time_ms")]
            public double ProcessingTimeMs { get; set; }
            
            [JsonPropertyName("image_width")]
            public int ImageWidth { get; set; }
            
            [JsonPropertyName("image_height")]
            public int ImageHeight { get; set; }
            
            public List<OcrTextDto>?  Texts { get; set; }
        }

        private class OcrTextDto
        {
            public string? Text { get; set; }
            public double Confidence { get; set; }
            public List<List<double>>? Bbox { get; set; }

            [JsonPropertyName("center_x")]
            public double CenterX { get; set; }

            [JsonPropertyName("center_y")]
            public double CenterY { get; set; }
        }

        private class HealthResponse
        {
            public string? Status { get; set; }
            public ModelsStatus? Models { get; set; }
        }

        private class ModelsStatus
        {
            public bool Yolo { get; set; }
            public bool Ocr { get; set; }

            [JsonPropertyName("table_reader")]
            public bool TableReader { get; set; }
        }

        public class TableServiceInfo
        {
            public string? Service { get; set; }
            public string? Status { get; set; }
            public Dictionary<string, object>? Info { get; set; }
        }

        #endregion
    }

    /// <summary>
    /// Bölge koordinatları (yüzde olarak)
    /// </summary>
    public class RectObj
    {
        public double X { get; set; }
        public double Y { get; set; }
        public double W { get; set; }
        public double H { get; set; }
    }
}