using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Net.Http.Headers;
// using Pgvector; // Çakışma olmasın diye aşağıda tam isim kullanacağız (Pgvector.Vector)

namespace Katalogcu.API.Services;

public class CatalogProcessorService
{
    private readonly AppDbContext _context;
    private readonly IPartalogAiService _aiService; // Postacımız
    private readonly IWebHostEnvironment _env;
    private readonly ILogger<CatalogProcessorService> _logger;
    private readonly IHttpClientFactory _httpClientFactory;

    // Python API Adresi
    private const string PYTHON_API_URL = "http://localhost:8000";

    public CatalogProcessorService(
        AppDbContext context,
        IPartalogAiService aiService,
        IWebHostEnvironment env,
        ILogger<CatalogProcessorService> logger,
        IHttpClientFactory httpClientFactory)
    {
        _context = context;
        _aiService = aiService;
        _env = env;
        _logger = logger;
        _httpClientFactory = httpClientFactory;
    }

    public async Task ProcessCatalogAsync(Guid catalogId)
    {
        _logger.LogInformation($"🚀 Otonom İşlem Başladı: {catalogId}");

        var catalog = await _context.Catalogs.FindAsync(catalogId);
        if (catalog == null) return;

        var pages = await _context.CatalogPages
            .Where(p => p.CatalogId == catalogId)
            .OrderBy(p => p.PageNumber)
            .ToListAsync();

        if (!pages.Any())
        {
            _logger.LogWarning("⚠️ Hiç sayfa bulunamadı!");
            return;
        }

        var client = _httpClientFactory.CreateClient();
        client.Timeout = TimeSpan.FromMinutes(5); 

        foreach (var page in pages)
        {
            _logger.LogInformation($"🔄 Sayfa {page.PageNumber} işleniyor...");

            var fullPath = GetFullPath(page.ImageUrl);
            if (fullPath == null) continue;

            try
            {
                var fileBytes = await File.ReadAllBytesAsync(fullPath);

                // ADIM 0: KAPAK ANALİZİ
                if (page.PageNumber == 1)
                {
                    await AnalyzeCoverPage(client, catalog, fileBytes);
                }

                // ADIM 1: SAYFA ANALİZİ
                var analysis = await _aiService.AnalyzePageAsync(fileBytes);
                page.AiDescription = analysis.Title;
                
                // ADIM 2: TABLO VE VEKTÖR
                if (analysis.IsPartsList)
                {
                    var extractedItems = await _aiService.ExtractTableAsync(fileBytes, page.PageNumber);
                    
                    if (extractedItems != null && extractedItems.Any())
                    {
                        var oldItems = await _context.CatalogItems
                            .Where(ci => ci.CatalogId == catalogId && ci.PageNumber == page.PageNumber.ToString())
                            .ToListAsync();
                        _context.CatalogItems.RemoveRange(oldItems);

                        foreach (var item in extractedItems)
                        {
                            var catalogItem = new CatalogItem
                            {
                                CatalogId = catalogId,
                                PageNumber = page.PageNumber.ToString(),
                                RefNumber = item.RefNumber,
                                PartCode = item.PartCode ?? "",   
                                PartName = item.PartName ?? "",   
                                Description = item.Description ?? "" 
                            };

                            // --- 🧠 VEKTÖR KISMI ---
                            string textToEmbed = $"{item.PartName} {item.Description} {item.PartCode}".Trim();
                            if (!string.IsNullOrEmpty(textToEmbed))
                            {
                                var vectorData = await _aiService.GetEmbeddingAsync(textToEmbed);
                                if (vectorData != null && vectorData.Length > 0)
                                {
                                    catalogItem.Embedding = new Pgvector.Vector(vectorData);
                                }
                            }
                            // -----------------------

                            _context.CatalogItems.Add(catalogItem);
                        }
                        
                        await _context.SaveChangesAsync();
                        _logger.LogInformation($"📚 {extractedItems.Count} parça kaydedildi.");
                    }
                }

                // ADIM 3: HOTSPOT
                if (analysis.IsTechnicalDrawing)
                {
                    using (var stream = new MemoryStream(fileBytes))
                    {
                        var formFile = CreateFormFile(stream, fullPath);
                        var oldSpots = await _context.Hotspots.Where(h => h.PageId == page.Id).ToListAsync();
                        _context.Hotspots.RemoveRange(oldSpots);

                        var hotspots = await _aiService.DetectHotspotsAsync(formFile, page.Id);
                        if (hotspots.Any())
                        {
                            await _context.Hotspots.AddRangeAsync(hotspots);
                        }
                    }
                }
                await _context.SaveChangesAsync();
            }
            catch (Exception ex)
            {
                var msg = ex.InnerException != null ? ex.InnerException.Message : ex.Message;
                _logger.LogError(ex, $"❌ Sayfa {page.PageNumber} hata: {msg}");
            }
        }

        _logger.LogInformation($"🏁 Katalog İşlemi Tamamlandı: {catalog.Name}");

        // 👇👇👇 YENİ EKLENEN KISIM: EĞİTİMİ TETİKLE 👇👇👇
        try
        {
            _logger.LogInformation("🚂 Python'a eğitim emri gönderiliyor...");
            // Python'daki /api/admin/train endpoint'ine boş bir POST atıyoruz.
            // Fire-and-forget (cevap beklememize gerek yok, arka planda yapsın).
            await client.PostAsync($"{PYTHON_API_URL}/api/admin/train", null);
            _logger.LogInformation("✅ Eğitim isteği gönderildi.");
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"⚠️ Eğitim tetiklenemedi (Sorun değil, sonraki katalogda öğrenir): {ex.Message}");
        }
        // 👆👆👆 --------------------------------------- 👆👆👆
    }

    // --- YARDIMCI METODLAR (Aynı) ---
    private async Task AnalyzeCoverPage(HttpClient client, Catalog catalog, byte[] fileBytes)
    {
        try
        {
            using var content = new MultipartFormDataContent();
            content.Add(new ByteArrayContent(fileBytes), "file", "cover.jpg");
            var response = await client.PostAsync($"{PYTHON_API_URL}/api/table/extract-metadata", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                var metadata = JsonSerializer.Deserialize<MetadataResponse>(json, new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                if (metadata != null && !string.IsNullOrEmpty(metadata.MachineModel))
                    catalog.Name = $"{metadata.MachineModel} ({metadata.CatalogTitle})";
            }
        }
        catch (Exception ex) { _logger.LogError($"Kapak hatası: {ex.Message}"); }
    }

    private IFormFile CreateFormFile(Stream stream, string fullPath)
    {
        return new FormFile(stream, 0, stream.Length, "file", Path.GetFileName(fullPath))
        {
            Headers = new HeaderDictionary(), ContentType = "image/jpeg"
        };
    }

    private string? GetFullPath(string? url)
    {
        if (string.IsNullOrEmpty(url)) return null;
        string cleanPath = WebUtility.UrlDecode(url);
        if (Uri.TryCreate(cleanPath, UriKind.Absolute, out var uri)) cleanPath = uri.LocalPath;
        cleanPath = cleanPath.TrimStart('/', '\\').Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
        var fullPath = Path.Combine(_env.WebRootPath, cleanPath);
        return File.Exists(fullPath) ? fullPath : null;
    }
}

public class MetadataResponse
{
    [JsonPropertyName("machine_model")] public string MachineModel { get; set; }
    [JsonPropertyName("catalog_title")] public string CatalogTitle { get; set; }
}