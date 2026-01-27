using Katalogcu.Domain.Entities;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Katalogcu.API.Services;

// --- GÜNCELLENMİŞ DTO MODELLERİ ---
public class AiAnalysisResult
{
    [JsonPropertyName("is_technical_drawing")]
    public bool IsTechnicalDrawing { get; set; }

    [JsonPropertyName("is_parts_list")] // ✨ KRİTİK EKLEME: Artık tabloları tanıyoruz
    public bool IsPartsList { get; set; }

    [JsonPropertyName("title")]
    public string? Title { get; set; }
}

public interface IPartalogAiService
{
    Task<List<Hotspot>> DetectHotspotsAsync(IFormFile file, Guid pageId);
    Task<List<Product>> ExtractTableAsync(IFormFile file, int pageNumber, Guid catalogId);
    Task<AiAnalysisResult?> AnalyzePageTitleAsync(IFormFile file);
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
        // Tier 1 hızında olsak da büyük dosyalar için güvenlik payı bırakıyoruz
        _httpClient.Timeout = TimeSpan.FromMinutes(5); 
    }

    // --- 1. YOLO (HOTSPOT TESPİTİ) ---
    public async Task<List<Hotspot>> DetectHotspotsAsync(IFormFile file, Guid pageId)
    {
        try
        {
            var endpoint = "/api/hotspot/detect"; 
            var responseJson = await SendFileAsync(file, endpoint);
            
            var result = JsonSerializer.Deserialize<YoloResponseDto>(responseJson, GetJsonOptions());
            if (result == null || !result.Success || result.Hotspots == null) return new List<Hotspot>();

            return result.Hotspots.Select(d => new Hotspot
            {
                Id = Guid.NewGuid(),
                PageId = pageId,
                Left = d.LeftPercent,
                Top = d.TopPercent,
                Width = d.WidthPercent,
                Height = d.HeightPercent,
                Label = d.Label,
                IsAiDetected = true,
                AiConfidence = d.Confidence,
                CreatedDate = DateTime.UtcNow
            }).ToList();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Hotspot servisi hatası.");
            return new List<Hotspot>(); // Hata durumunda boş liste dön, akışı kesme
        }
    }

    // --- 2. GEMINI (TABLO OKUMA) ---
    public async Task<List<Product>> ExtractTableAsync(IFormFile file, int pageNumber, Guid catalogId)
    {
        try
        {
            var endpoint = $"/api/table/extract?page_number={pageNumber}"; 
            var responseJson = await SendFileAsync(file, endpoint);
            
            var result = JsonSerializer.Deserialize<TableResponseDto>(responseJson, GetJsonOptions());
            if (result == null || !result.Success) return new List<Product>();

            var products = new List<Product>();
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
                            RefNo = item.RefNumber,
                            Code = item.PartCode,
                            Name = item.PartName,
                            StockQuantity = item.Quantity,
                            PageNumber = pageNumber.ToString(),
                            CreatedDate = DateTime.UtcNow
                        });
                    }
                }
            }
            return products;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Tablo okuma servisi hatası.");
            return new List<Product>();
        }
    }

    // --- 3. SAYFA ANALİZİ (BAŞLIK ve TÜR BULMA) ---
    public async Task<AiAnalysisResult?> AnalyzePageTitleAsync(IFormFile file)
    {
        try
        {
            var endpoint = "/api/analysis/analyze-page-title";
            var responseJson = await SendFileAsync(file, endpoint);
            
            // Python'dan dönen "is_parts_list" alanını artık karşılıyoruz
            return JsonSerializer.Deserialize<AiAnalysisResult>(responseJson, GetJsonOptions());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Sayfa analiz servisi hatası.");
            return null;
        }
    }

    // --- YARDIMCI METODLAR ---
    private async Task<string> SendFileAsync(IFormFile file, string relativeUrl)
    {
        using var content = new MultipartFormDataContent();
        using var stream = file.OpenReadStream();
        var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue(file.ContentType);
        content.Add(fileContent, "file", file.FileName);

        var response = await _httpClient.PostAsync(relativeUrl, content);
        if (!response.IsSuccessStatusCode)
        {
            var error = await response.Content.ReadAsStringAsync();
            _logger.LogError($"AI API Hatası ({relativeUrl}): {error}");
            throw new HttpRequestException($"AI Error: {response.StatusCode} - {error}");
        }
        return await response.Content.ReadAsStringAsync();
    }

    private JsonSerializerOptions GetJsonOptions() => new() 
    { 
        PropertyNameCaseInsensitive = true, 
        NumberHandling = JsonNumberHandling.AllowReadingFromString 
    };

    // --- İÇ DTO SINIFLARI ---
    private class YoloResponseDto
    {
        public bool Success { get; set; }
        public List<YoloHotspotDto>? Hotspots { get; set; }
    }
    private class YoloHotspotDto
    {
        public string? Label { get; set; }
        public double Confidence { get; set; }
        [JsonPropertyName("left_percent")] public double LeftPercent { get; set; }
        [JsonPropertyName("top_percent")] public double TopPercent { get; set; }
        [JsonPropertyName("width_percent")] public double WidthPercent { get; set; }
        [JsonPropertyName("height_percent")] public double HeightPercent { get; set; }
    }
    private class TableResponseDto
    {
        public bool Success { get; set; }
        public List<TableResultDto>? Tables { get; set; }
    }
    private class TableResultDto { public List<ProductItemDto>? Products { get; set; } }
    private class ProductItemDto
    {
        [JsonPropertyName("ref_number")] public int RefNumber { get; set; }
        [JsonPropertyName("part_code")] public string? PartCode { get; set; }
        [JsonPropertyName("part_name")] public string? PartName { get; set; }
        [JsonPropertyName("quantity")] public int Quantity { get; set; }
    }
}