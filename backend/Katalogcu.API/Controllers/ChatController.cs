using Katalogcu.API.Services; // DTO'lar buradan gelecek
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Newtonsoft.Json; 

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class ChatController : ControllerBase
    {
        private readonly IPartalogAiService _aiService;
        private readonly AppDbContext _context;
        private readonly ILogger<ChatController> _logger;

        public ChatController(
            IPartalogAiService aiService, 
            AppDbContext context,
            ILogger<ChatController> logger)
        {
            _aiService = aiService;
            _context = context;
            _logger = logger;
        }

        [HttpPost("ask")]
        public async Task<IActionResult> Ask([FromForm] AiChatRequestWithHistoryDto request)
        {
            try
            {
                // 1. History JSON string olarak gelir, listeye çevirelim
                // ChatMessageDto artık Services namespace'inden geliyor.
                List<ChatMessageDto> chatHistory = new();
                if (!string.IsNullOrEmpty(request.History))
                {
                    try {
                        chatHistory = JsonConvert.DeserializeObject<List<ChatMessageDto>>(request.History) ?? new();
                    } catch { _logger.LogWarning("History parse edilemedi"); }
                }

                // 2. Python Servisine İletmek İçin DTO Hazırla
                // Bu AiChatRequestDto artık Services namespace'inden geliyor (Doğru olan)
                var aiRequest = new AiChatRequestDto 
                { 
                    Text = request.Text,
                    Image = request.Image,
                    History = chatHistory 
                };

                var aiAnalysis = await _aiService.GetExpertChatResponseAsync(aiRequest);

                if (string.IsNullOrEmpty(aiAnalysis.SearchTerm))
                {
                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = aiAnalysis.ReplySuggestion ?? "Anlaşıldı.",
                        Products = [],
                        DebugInfo = "Chat Mode (No Search)"
                    });
                }

                // 3. STRATEJİK ARAMA MOTORU 🕵️‍♂️
                (List<CatalogItem> results, string debugInfo) = await ExecuteSearchStrategyAsync(aiAnalysis);

                // 4. SONUÇLARI ZENGİNLEŞTİR
                var enrichedResults = await EnrichResultsAsync(results);

                // 5. RESPONSE HAZIRLA
                string finalReply = !string.IsNullOrEmpty(aiAnalysis.ReplySuggestion)
                    ? aiAnalysis.ReplySuggestion 
                    : (results.Count > 0 ? $"İşte bulduğum sonuçlar ({results.Count} adet):" : "Üzgünüm, veritabanında eşleşen parça bulamadım.");

                return Ok(new ChatResponseDto
                {
                    ReplySuggestion = finalReply,
                    Products = enrichedResults,
                    DebugInfo = debugInfo
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Chat Ask endpoint'inde hata oluştu");
                return StatusCode(500, new { error = "Bir hata oluştu, lütfen tekrar deneyin." });
            }
        }

        // --- ARAMA STRATEJİLERİ ---
        private async Task<(List<CatalogItem> Results, string DebugInfo)> ExecuteSearchStrategyAsync(AiChatResponseDto aiData) 
        {
            List<CatalogItem> results;
            string debugInfo;
            var mainTerm = aiData.SearchTerm ?? string.Empty;

            // PLAN A
            results = await SearchDatabaseAsync(mainTerm, aiData);
            debugInfo = $"Plan A ({mainTerm} | Filters: {aiData.StrictFilter ?? "None"})";
            if (results.Count > 0) return (results, debugInfo);

            // PLAN B
            if (!string.IsNullOrEmpty(aiData.StrictFilter) || !string.IsNullOrEmpty(aiData.Gauge))
            {
                // Service DTO'sunu kullanıyoruz
                var relaxedData = new AiChatResponseDto 
                { 
                    SearchTerm = mainTerm,
                    NegativeFilter = aiData.NegativeFilter, 
                    Gauge = null, StrictFilter = null,
                    ReplySuggestion = aiData.ReplySuggestion,
                    Alternatives = aiData.Alternatives
                };
                results = await SearchDatabaseAsync(mainTerm, relaxedData);
                debugInfo = $"Plan B ({mainTerm} - Relaxed)";
                if (results.Count > 0) return (results, debugInfo);
            }

            // PLAN C
            if (aiData.Alternatives is { Count: > 0 })
            {
                foreach (var altTerm in aiData.Alternatives)
                {
                    results = await SearchDatabaseAsync(altTerm, aiData);
                    if (results.Count > 0)
                    {
                        debugInfo = $"Plan C ({altTerm} + Filters)";
                        return (results, debugInfo);
                    }
                }
            }

            return (new List<CatalogItem>(), debugInfo);
        }

        private async Task<List<CatalogItem>> SearchDatabaseAsync(string term, AiChatResponseDto filters)
        {
            if (string.IsNullOrWhiteSpace(term)) return new List<CatalogItem>();
            var normalizedTerm = term.ToUpperInvariant();

            var query = _context.CatalogItems.AsNoTracking()
                .Where(ci => EF.Functions.ILike(ci.PartName, $"%{normalizedTerm}%") || EF.Functions.ILike(ci.PartCode, $"%{normalizedTerm}%"));

            if (!string.IsNullOrEmpty(filters.Gauge))
            {
                var gauge = filters.Gauge.ToUpperInvariant();
                query = query.Where(ci => EF.Functions.ILike(ci.Description, $"%{gauge}%"));
            }

            if (!string.IsNullOrEmpty(filters.StrictFilter))
            {
                var strict = filters.StrictFilter.ToUpperInvariant();
                query = query.Where(ci => EF.Functions.ILike(ci.Description, $"%{strict}%") || EF.Functions.ILike(ci.PartName, $"%{strict}%"));
            }

            if (!string.IsNullOrEmpty(filters.NegativeFilter))
            {
                var negative = filters.NegativeFilter.ToUpperInvariant();
                query = query.Where(ci => !EF.Functions.ILike(ci.Description, $"%{negative}%") && !EF.Functions.ILike(ci.PartName, $"%{negative}%"));
            }

            var rawResults = await query.Take(50).ToListAsync();

            return rawResults
                .GroupBy(x => x.PartCode).Select(g => g.First())
                .OrderByDescending(x => x.PartName.Equals(normalizedTerm, StringComparison.OrdinalIgnoreCase))
                .ThenBy(x => x.PartName.Length)
                .Take(10).ToList();
        }

        private async Task<List<EnrichedPartResult>> EnrichResultsAsync(List<CatalogItem> items)
        {
            if (items.Count == 0) return [];
            var codes = items.Select(i => i.PartCode).Distinct().ToList();
            var products = await _context.Products.AsNoTracking().Where(p => codes.Contains(p.Code)).ToListAsync();
            var productDict = products.GroupBy(p => p.Code).ToDictionary(g => g.Key, g => g.First());

            return items.Select(item =>
            {
                productDict.TryGetValue(item.PartCode, out var product);
                return new EnrichedPartResult
                {
                    Id = item.Id, Code = item.PartCode, Name = item.PartName, Description = item.Description,
                    CatalogId = item.CatalogId, PageNumber = item.PageNumber.ToString(),
                    StockStatus = product != null ? "Stokta Var" : "Stokta Yok",
                    Price = product?.Price, ImageUrl = product?.ImageUrl
                };
            }).ToList();
        }
    }

    #region Controller-Specific DTOs

    // ⚠️ DİKKAT: Burada 'AiChatRequestDto', 'ChatMessageDto' ve 'AiChatResponseDto' SINIFLARINI SİLDİK.
    // Çünkü onlar zaten 'Katalogcu.API.Services' içinde var ve biz 'using' ile onları kullanıyoruz.
    // Tekrar tanımlarsak çakışma (ambiguity) olur.

    // 1. Controller'a gelen DTO (Frontend'den gelen - Özel DTO)
    public class AiChatRequestWithHistoryDto
    {
        public string? Text { get; set; }
        public IFormFile? Image { get; set; }
        public string? History { get; set; } // JSON String olarak gelir
    }

    // 2. Frontend'e dönen cevap (UI için - Özel DTO)
    public record ChatResponseDto
    {
        public string ReplySuggestion { get; init; } = string.Empty;
        public List<EnrichedPartResult> Products { get; init; } = [];
        public string? DebugInfo { get; init; }
    }

    // 3. Zenginleştirilmiş Sonuç (UI için - Özel DTO)
    public record EnrichedPartResult
    {
        public Guid Id { get; init; } 
        public string Code { get; init; } = string.Empty;
        public string Name { get; init; } = string.Empty;
        public string? Description { get; init; }
        public Guid CatalogId { get; init; }
        public string? PageNumber { get; init; } 
        public string StockStatus { get; init; } = "Stokta Yok";
        public decimal? Price { get; init; }
        public string? ImageUrl { get; init; }
    }

    #endregion
}