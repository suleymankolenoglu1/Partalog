using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text; // Encoding için gerekli
using Katalogcu.Domain.Entities; 

namespace Katalogcu.API.Services;

// --- ARAYÜZ (INTERFACE) ---
public interface IPartalogAiService
{
    // 1. YOLO
    Task<List<Hotspot>> DetectHotspotsAsync(IFormFile file, Guid pageId);
    
    // 2. GEMINI Tablo
    Task<List<ProductItemDto>> ExtractTableAsync(byte[] fileBytes, int pageNumber);
    
    // 3. Sayfa Analizi
    Task<PageAnalysisResult> AnalyzePageAsync(byte[] fileBytes);
    
    // 4. CHAT (Geçmiş Destekli)
    Task<AiChatResponseDto> GetExpertChatResponseAsync(AiChatRequestDto request);

    // 5. EĞİTİM TETİKLEYİCİ
    Task TriggerTrainingAsync();

    // 6. 🔥 YENİ: METİN VEKTÖRLEŞTİRME (SEMANTIC SEARCH)
    // Metni alır, 768 boyutlu float dizisi döner.
    Task<float[]?> GetEmbeddingAsync(string text);
}

// --- SERVİS (IMPLEMENTATION) ---
public class PartalogAiService : IPartalogAiService
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<PartalogAiService> _logger;
    private readonly JsonSerializerOptions _jsonOptions;

    public PartalogAiService(HttpClient httpClient, ILogger<PartalogAiService> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
        
        // Timeout ayarı (Uzun süren AI işlemleri için)
        _httpClient.Timeout = TimeSpan.FromMinutes(5);

        _jsonOptions = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            NumberHandling = JsonNumberHandling.AllowReadingFromString,
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower 
        };
    }

    // --- 1. YOLO (HOTSPOT TESPİTİ) ---
    public async Task<List<Hotspot>> DetectHotspotsAsync(IFormFile file, Guid pageId)
    {
        try
        {
            var responseJson = await SendFileStreamAsync(file, "/api/hotspot/detect");
            var result = JsonSerializer.Deserialize<YoloResponseDto>(responseJson, _jsonOptions);
            
            if (result == null || !result.Success || result.Hotspots == null) 
                return new List<Hotspot>();

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
            _logger.LogError(ex, "YOLO servisi hatası.");
            return new List<Hotspot>();
        }
    }

    // --- 2. GEMINI (TABLO OKUMA) ---
    public async Task<List<ProductItemDto>> ExtractTableAsync(byte[] fileBytes, int pageNumber)
    {
        try
        {
            using var content = new MultipartFormDataContent();
            var fileContent = new ByteArrayContent(fileBytes);
            fileContent.Headers.ContentType = new MediaTypeHeaderValue("image/jpeg");
            content.Add(fileContent, "file", "page.jpg");
            
            var response = await _httpClient.PostAsync($"/api/table/extract?page_number={pageNumber}", content);
            if (!response.IsSuccessStatusCode) return new List<ProductItemDto>();

            var responseJson = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<TableResponseDto>(responseJson, _jsonOptions);
            
            if (result == null || !result.Success || result.Tables == null) 
                return new List<ProductItemDto>();

            return result.Tables.SelectMany(t => t.Products ?? new List<ProductItemDto>()).ToList();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Tablo okuma servisi hatası.");
            return new List<ProductItemDto>();
        }
    }

    // --- 3. SAYFA ANALİZİ ---
    public async Task<PageAnalysisResult> AnalyzePageAsync(byte[] fileBytes)
    {
        try
        {
            using var content = new MultipartFormDataContent();
            var fileContent = new ByteArrayContent(fileBytes);
            fileContent.Headers.ContentType = new MediaTypeHeaderValue("image/jpeg");
            content.Add(fileContent, "file", "page.jpg");

            var response = await _httpClient.PostAsync("/api/analysis/analyze-page-title", content); 
            if (response.IsSuccessStatusCode)
            {
                var responseJson = await response.Content.ReadAsStringAsync();
                var result = JsonSerializer.Deserialize<PageAnalysisResult>(responseJson, _jsonOptions);
                return result ?? new PageAnalysisResult();
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Sayfa analiz servisi hatası.");
        }
        return new PageAnalysisResult { IsTechnicalDrawing = false, IsPartsList = false, Title = "Analiz Edilemedi" };
    }

    // --- 4. EXPERT AI CHAT ---
    public async Task<AiChatResponseDto> GetExpertChatResponseAsync(AiChatRequestDto request)
    {
        try
        {
            using var content = new MultipartFormDataContent();

            content.Add(new StringContent(request.Text ?? ""), "text");
            var historyJson = JsonSerializer.Serialize(request.History ?? new List<ChatMessageDto>(), _jsonOptions);
            content.Add(new StringContent(historyJson), "history");

            if (request.Image != null)
            {
                var fileStream = request.Image.OpenReadStream();
                var fileContent = new StreamContent(fileStream);
                fileContent.Headers.ContentType = new MediaTypeHeaderValue(request.Image.ContentType);
                content.Add(fileContent, "file", request.Image.FileName);
            }

            var response = await _httpClient.PostAsync("/api/chat/expert-chat", content);

            if (!response.IsSuccessStatusCode)
            {
                var errorMsg = await response.Content.ReadAsStringAsync();
                _logger.LogError($"Chat API Hatası ({response.StatusCode}): {errorMsg}");
                return new AiChatResponseDto { ReplySuggestion = "AI servisine ulaşılamıyor." };
            }

            var jsonResponse = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<AiChatResponseDto>(jsonResponse, _jsonOptions);
            
            return result ?? new AiChatResponseDto { ReplySuggestion = "Anlaşılamadı." };
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Chat servisi hatası.");
            return new AiChatResponseDto { ReplySuggestion = "Sistem hatası oluştu." };
        }
    }

    // --- 5. EĞİTİM TETİKLEYİCİ ---
    public async Task TriggerTrainingAsync()
    {
        try
        {
            var response = await _httpClient.PostAsync("/api/admin/train", null);
            if (response.IsSuccessStatusCode)
                _logger.LogInformation("✅ AI Sözlük Eğitimi başarıyla tetiklendi.");
            else
                _logger.LogWarning($"⚠️ AI Eğitimi tetiklenemedi. Status: {response.StatusCode}");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ AI Trigger hatası.");
        }
    }

    // --- 6. 🔥 YENİ: EMBEDDING (VEKTÖR) ALMA ---
    public async Task<float[]?> GetEmbeddingAsync(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return null;

        try
        {
            // Python'a gidecek JSON: { "text": "civata" }
            var payload = new { text = text };
            var jsonContent = new StringContent(
                JsonSerializer.Serialize(payload), 
                Encoding.UTF8, 
                "application/json");

            var response = await _httpClient.PostAsync("/api/embed", jsonContent);

            if (!response.IsSuccessStatusCode)
            {
                var err = await response.Content.ReadAsStringAsync();
                _logger.LogError($"Embedding API Hatası ({response.StatusCode}): {err}");
                return null;
            }

            var resJson = await response.Content.ReadAsStringAsync();
            var result = JsonSerializer.Deserialize<EmbeddingResponseDto>(resJson, _jsonOptions);

            return result?.Embedding;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Embedding servisi hatası.");
            return null;
        }
    }

    // --- YARDIMCI METODLAR ---
    private async Task<string> SendFileStreamAsync(IFormFile file, string relativeUrl)
    {
        using var content = new MultipartFormDataContent();
        using var stream = file.OpenReadStream();
        var fileContent = new StreamContent(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue(file.ContentType);
        content.Add(fileContent, "file", file.FileName);

        var response = await _httpClient.PostAsync(relativeUrl, content);
        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException($"API Hatası: {response.StatusCode}");
        }
        return await response.Content.ReadAsStringAsync();
    }

    // --- DAHİLİ DTO SINIFLARI (Internal) ---
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

    // 🔥 Yeni: Embedding Cevabı için DTO
    private class EmbeddingResponseDto
    {
        [JsonPropertyName("embedding")]
        public float[]? Embedding { get; set; }
    }
}

// --- PUBLIC DTO'LAR ---

public class AiChatRequestDto
{
    public string? Text { get; set; }
    public List<ChatMessageDto> History { get; set; } = new(); 
    public IFormFile? Image { get; set; } 
}

public class ChatMessageDto
{
    public string Role { get; set; } = "user";
    public string Text { get; set; } = string.Empty;
}

public class AiChatResponseDto
{
    [JsonPropertyName("search_term")]
    public string? SearchTerm { get; set; }

    [JsonPropertyName("alternatives")]
    public List<string>? Alternatives { get; set; }

    [JsonPropertyName("gauge")]
    public string? Gauge { get; set; }

    [JsonPropertyName("strict_filter")]
    public string? StrictFilter { get; set; }

    [JsonPropertyName("negative_filter")]
    public string? NegativeFilter { get; set; }

    [JsonPropertyName("reply_suggestion")]
    public string? ReplySuggestion { get; set; }
}

public class PageAnalysisResult
{
    [JsonPropertyName("is_technical_drawing")]
    public bool IsTechnicalDrawing { get; set; }

    [JsonPropertyName("is_parts_list")]
    public bool IsPartsList { get; set; }

    [JsonPropertyName("title")]
    public string Title { get; set; } = "Başlıksız";
}

public class ProductItemDto
{
    [JsonPropertyName("ref_number")] public string RefNumber { get; set; } = "0";
    [JsonPropertyName("part_code")] public string? PartCode { get; set; }
    [JsonPropertyName("part_name")] public string? PartName { get; set; }
    [JsonPropertyName("description")] public string? Description { get; set; }
    [JsonPropertyName("quantity")] public int Quantity { get; set; }
}