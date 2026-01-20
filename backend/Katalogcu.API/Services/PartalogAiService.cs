using Katalogcu.Domain.Entities;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Katalogcu.API.Services;

public interface IPartalogAiService
{
    // YOLO: Görseldeki hotspotları bulur ve Hotspot entity listesi döner
    Task<List<Hotspot>> DetectHotspotsAsync(IFormFile file, Guid pageId);

    // GEMINI: Görseldeki tabloyu okur ve Product entity listesi döner
    Task<List<Product>> ExtractTableAsync(IFormFile file, int pageNumber, Guid catalogId);
}

public class PartalogAiService : IPartalogAiService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _config;
    private readonly ILogger<PartalogAiService> _logger;

    public PartalogAiService(HttpClient httpClient, IConfiguration configuration, ILogger<PartalogAiService> logger)
    {
        _httpClient = httpClient;
        _config = configuration;
        _logger = logger;
    }

    // --- 1. YOLO (HOTSPOT TESPİTİ) ---
    public async Task<List<Hotspot>> DetectHotspotsAsync(IFormFile file, Guid pageId)
    {
        _logger.LogInformation("🔍 YOLO Hotspot Tespiti Başlıyor: {FileName}", file.FileName);

        // Python Endpoint: /api/detect
        var endpoint = _config["AiService:Endpoints:DetectHotspots"] ?? "/api/detect";

        // İsteği Gönder
        var responseJson = await SendFileAsync(file, endpoint);

        // JSON Parse Et
        var result = JsonSerializer.Deserialize<YoloResponseDto>(responseJson, GetJsonOptions());

        if (result is null || !result.Success)
        {
            _logger.LogError("❌ YOLO Hatası: {Message}", result?.Error ?? "Bilinmeyen hata");
            return new List<Hotspot>();
        }

        // DTO -> Domain Entity Dönüşümü
        var hotspots = result.Detections.Select(d => new Hotspot
        {
            Id = Guid.NewGuid(),
            PageId = pageId,
            // YOLO'dan gelen değerler (x, y, w, h)
            Left = d.Box != null && d.Box.Count >= 4 ? d.Box[0] : 0, // x
            Top = d.Box != null && d.Box.Count >= 4 ? d.Box[1] : 0,  // y
            Width = d.Box != null && d.Box.Count >= 4 ? d.Box[2] : 0, // w
            Height = d.Box != null && d.Box.Count >= 4 ? d.Box[3] : 0,// h
            Label = d.Label, // "1", "2" gibi numaralar
            IsAiDetected = true,
            AiConfidence = d.Confidence,
            CreatedDate = DateTime.UtcNow
        }).ToList();

        _logger.LogInformation("✅ {Count} hotspot tespit edildi.", hotspots.Count);
        return hotspots;
    }

    // --- 2. GEMINI (TABLO OKUMA) ---
    public async Task<List<Product>> ExtractTableAsync(IFormFile file, int pageNumber, Guid catalogId)
    {
        _logger.LogInformation("🤖 Gemini Tablo Okuma Başlıyor: Sayfa {Page}", pageNumber);

        // Python Endpoint: /api/table/extract-table
        var endpoint = _config["AiService:Endpoints:ExtractTable"] ?? "/api/table/extract-table";
        var url = $"{endpoint}?page_number={pageNumber}";

        // İsteği Gönder
        var responseJson = await SendFileAsync(file, url);

        // JSON Parse Et
        var result = JsonSerializer.Deserialize<TableResponseDto>(responseJson, GetJsonOptions());

        if (result is null || !result.Success)
        {
            _logger.LogError("❌ Gemini Hatası: {Message}", result?.Message ?? "Bilinmeyen hata");
            return new List<Product>();
        }

        var products = new List<Product>();
        
        // Gemini'den gelen tabloları gez
        if (result.Tables != null)
        {
            foreach (var table in result.Tables)
            {
                if (table.Products == null) continue;

                foreach (var item in table.Products)
                {
                    products.Add(new Product
                    {
                        Id = Guid.NewGuid(),
                        CatalogId = catalogId,
                        RefNo = item.RefNumber, // int
                        Code = item.PartCode,   // string
                        Name = item.PartName,   // string
                        StockQuantity = item.Quantity, // int (Adet)
                        PageNumber = pageNumber.ToString(),
                        Description = $"AI tarafından okundu (Ref: {item.RefNumber})",
                        CreatedDate = DateTime.UtcNow,
                        Category = "Yedek Parça",
                        Price = 0 // Fiyat bilgisi tablodan gelmiyor
                    });
                }
            }
        }

        _logger.LogInformation("✅ {Count} parça başarıyla okundu.", products.Count);
        return products;
    }

    // --- YARDIMCI METODLAR ---

    private async Task<string> SendFileAsync(IFormFile file, string relativeUrl)
    {
        using var content = new MultipartFormDataContent();
        using var stream = file.OpenReadStream();
        var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue(file.ContentType);
        
        // Python tarafı parametre adını "file" olarak bekliyor
        content.Add(fileContent, "file", file.FileName);

        var response = await _httpClient.PostAsync(relativeUrl, content);

        if (!response.IsSuccessStatusCode)
        {
            var error = await response.Content.ReadAsStringAsync();
            throw new Exception($"AI Servis Hatası ({response.StatusCode}): {error}");
        }

        return await response.Content.ReadAsStringAsync();
    }

    private JsonSerializerOptions GetJsonOptions()
    {
        return new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            NumberHandling = JsonNumberHandling.AllowReadingFromString
        };
    }

    // --- DTO CLASSES (Python JSON Karşılıkları) ---

    // YOLO Response Yapısı
    private class YoloResponseDto
    {
        public bool Success { get; set; }
        public string? Error { get; set; }
        public List<YoloDetectionDto> Detections { get; set; } = new();
    }

    private class YoloDetectionDto
    {
        public string? Label { get; set; }
        public double Confidence { get; set; }
        // YOLO genelde [x, y, w, h] döner
        public List<double>? Box { get; set; } 
    }

    // GEMINI Response Yapısı
    private class TableResponseDto
    {
        public bool Success { get; set; }
        public string? Message { get; set; }
        public List<TableResultDto>? Tables { get; set; }
    }

    private class TableResultDto
    {
        public List<ProductItemDto>? Products { get; set; }
    }

    private class ProductItemDto
    {
        [JsonPropertyName("ref_number")]
        public int RefNumber { get; set; }

        [JsonPropertyName("part_code")]
        public string? PartCode { get; set; }

        [JsonPropertyName("part_name")]
        public string? PartName { get; set; }

        [JsonPropertyName("quantity")]
        public int Quantity { get; set; }
    }
}