using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Newtonsoft.Json;
using System.Text.Json;
using System.Security.Claims;

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

        private Guid GetCurrentUserId()
        {
            var idString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (Guid.TryParse(idString, out var guid)) return guid;
            return Guid.Empty;
        }

        [HttpPost("ask")]
        public async Task<IActionResult> Ask([FromForm] AiChatRequestWithHistoryDto request)
        {
            try
            {
                // ✅ Kullanıcı ayrımı: önce JWT, yoksa request.UserId
                var userId = GetCurrentUserId();
                if (userId == Guid.Empty && !string.IsNullOrWhiteSpace(request.UserId))
                {
                    Guid.TryParse(request.UserId, out userId);
                }

                if (userId == Guid.Empty)
                {
                    return BadRequest("Kullanıcı bilgisi bulunamadı.");
                }

                _logger.LogInformation("Chat request userId: {UserId}", userId);

                // ✅ Katalog yoksa direkt boş dön
                var hasCatalogs = await _context.Catalogs.AsNoTracking().AnyAsync(c => c.UserId == userId);
                if (!hasCatalogs)
                {
                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = "Bu mağazada henüz katalog yok.",
                        Products = new List<EnrichedPartResult>(),
                        DebugInfo = "No catalogs for user"
                    });
                }

                // 1. History Parse
                var chatHistory = new List<ChatMessageDto>();
                if (!string.IsNullOrEmpty(request.History))
                {
                    try
                    {
                        chatHistory = JsonConvert.DeserializeObject<List<ChatMessageDto>>(request.History) ?? new();
                    }
                    catch { _logger.LogWarning("History parse edilemedi, sohbet sıfırdan başlıyor."); }
                }

                // 2. Servis İsteği Hazırlığı
                var aiRequest = new AiChatRequestDto
                {
                    Text = request.Text,
                    Image = request.Image,
                    History = chatHistory
                };

                // 3. AI Analizi (Python)
                var aiResponse = await _aiService.GetExpertChatResponseAsync(aiRequest);

                // --- NİYET ANALİZİ ---
                string? searchTerm = null;
                if (aiResponse.DebugIntent is JsonElement intentElement)
                {
                    if (intentElement.TryGetProperty("search_term", out var st)) searchTerm = st.GetString();
                }

                // 4. PARÇA LİSTESİ HAZIRLIĞI
                List<EnrichedPartResult> finalProducts = new();

                // SENARYO A: Python kaynak bulduysa
                if (aiResponse.Sources != null && aiResponse.Sources.Any())
                {
                    finalProducts = await EnrichPythonSourcesAsync(aiResponse.Sources, userId);
                }
                // SENARYO B: Python bulamadıysa ama Kod yakaladıysa
                else if (!string.IsNullOrWhiteSpace(searchTerm) && IsPartNumber(searchTerm))
                {
                    var fallbackResults = await SearchByCodeAsync(searchTerm, userId);
                    finalProducts = await EnrichResultsAsync(fallbackResults, userId);
                }

                // 5. ACİL MÜDAHALE (Kod araması)
                if (IsPartNumber(request.Text) && finalProducts.Count == 0)
                {
                    var directResults = await SearchByCodeAsync(request.Text, userId);
                    if (directResults.Any())
                    {
                        finalProducts = await EnrichResultsAsync(directResults, userId);
                        aiResponse.Answer = $"Aradığınız {request.Text} kodlu ürün için veritabanında {finalProducts.Count} sonuç buldum.";
                    }
                }

                // 🔥 6. AI CEVABINI DÜZELTME (OVERRIDE - V2: ESTETİK AMELİYAT) 🔥
                if (!string.IsNullOrEmpty(aiResponse.Answer) && finalProducts.Any())
                {
                    var bestMatch = finalProducts.First();
                    var bestName = bestMatch.Name;

                    var badPhrases = new[] { "Unknown Part", "Belirtilmemiş Parça", "İsimsiz Parça", "Bilinmeyen Parça", "İsimsiz" };
                    bool correctionMade = false;

                    foreach (var phrase in badPhrases)
                    {
                        if (aiResponse.Answer.Contains(phrase, StringComparison.OrdinalIgnoreCase))
                        {
                            aiResponse.Answer = aiResponse.Answer.Replace(phrase, bestName, StringComparison.OrdinalIgnoreCase);
                            correctionMade = true;
                        }
                    }

                    if (correctionMade && !aiResponse.Answer.Contains(bestMatch.Code))
                    {
                        aiResponse.Answer = $"{bestMatch.Code} - {aiResponse.Answer}";
                    }

                    if (!correctionMade && (aiResponse.Answer.Contains("Unknown Part") || aiResponse.Answer.Contains("Belirtilmemiş")))
                    {
                        aiResponse.Answer = $"Aradığınız parça {bestMatch.Code} - {bestMatch.Name}, {bestMatch.Model ?? "ilgili"} makinesi içindir.";
                    }
                }

                // 7. CEVAP DÖN
                return Ok(new ChatResponseDto
                {
                    ReplySuggestion = aiResponse.Answer ?? "Üzgünüm, sonuç bulunamadı.",
                    Products = finalProducts,
                    DebugInfo = $"Search: {searchTerm ?? "Yok"}"
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Chat Controller Hatası");
                return StatusCode(500, new { error = "Sistem hatası: " + ex.Message });
            }
        }

        // --- YARDIMCI METODLAR ---

        private async Task<List<EnrichedPartResult>> EnrichPythonSourcesAsync(List<ChatSourceDto> sources, Guid userId)
        {
            var codes = sources.Where(s => !string.IsNullOrEmpty(s.Code)).Select(s => s.Code).Distinct().ToList();
            if (!codes.Any()) return new();

            var products = await _context.Products
                .Include(p => p.Catalog)
                .AsNoTracking()
                .Where(p => codes.Contains(p.Code) && p.Catalog.UserId == userId)
                .ToListAsync();

            var productDict = products.GroupBy(p => p.Code).ToDictionary(g => g.Key, g => g.First());

            var catalogItems = await _context.CatalogItems
                .Include(ci => ci.Catalog)
                .AsNoTracking()
                .Where(ci => codes.Contains(ci.PartCode) && ci.Catalog.UserId == userId)
                .ToListAsync();

            var itemDict = catalogItems
                .GroupBy(ci => ci.PartCode)
                .ToDictionary(g => g.Key, g => g
                    .OrderByDescending(x => !string.IsNullOrWhiteSpace(x.PartName) && x.PartName != "Unknown Part")
                    .ThenByDescending(x => !string.IsNullOrWhiteSpace(x.Description))
                    .First());

            var enrichedList = new List<EnrichedPartResult>();

            foreach (var source in sources)
            {
                if (string.IsNullOrEmpty(source.Code)) continue;

                productDict.TryGetValue(source.Code, out var product);
                itemDict.TryGetValue(source.Code, out var catItem);

                string finalName = catItem?.PartName;
                if (string.IsNullOrWhiteSpace(finalName) || finalName == "Unknown Part") finalName = source.Name;
                if ((string.IsNullOrWhiteSpace(finalName) || finalName == "Unknown Part") && !string.IsNullOrWhiteSpace(catItem?.Description)) finalName = catItem.Description;
                if (string.IsNullOrWhiteSpace(finalName) || finalName == "Unknown Part") finalName = $"Parça {source.Code}";

                enrichedList.Add(new EnrichedPartResult
                {
                    Id = catItem?.Id ?? Guid.Empty,
                    Code = source.Code,
                    Name = finalName,
                    Description = catItem?.Description ?? source.Description,
                    Model = source.Model,
                    CatalogId = catItem?.CatalogId ?? Guid.Empty,
                    PageNumber = catItem?.PageNumber,
                    StockStatus = product != null ? "Stokta Var" : "Stokta Yok",
                    Price = product?.Price,
                    ImageUrl = product?.ImageUrl
                });
            }
            return enrichedList;
        }

        private async Task<List<CatalogItem>> SearchByCodeAsync(string? term, Guid userId)
        {
            if (string.IsNullOrWhiteSpace(term)) return new List<CatalogItem>();
            var code = term.Trim().ToUpperInvariant();

            return await _context.CatalogItems
                .Include(ci => ci.Catalog)
                .AsNoTracking()
                .Where(ci =>
                    ci.Catalog.UserId == userId &&
                    (ci.RefNumber == code || ci.PartCode == code || ci.PartCode.StartsWith(code)))
                .OrderBy(ci => ci.PartCode.Length)
                .Take(5)
                .ToListAsync();
        }

        private async Task<List<EnrichedPartResult>> EnrichResultsAsync(List<CatalogItem> items, Guid userId)
        {
            if (items.Count == 0) return new();

            var codes = items.Select(i => i.PartCode).Distinct().ToList();

            var products = await _context.Products
                .Include(p => p.Catalog)
                .AsNoTracking()
                .Where(p => codes.Contains(p.Code) && p.Catalog.UserId == userId)
                .ToListAsync();

            var productDict = products.GroupBy(p => p.Code).ToDictionary(g => g.Key, g => g.First());

            var cleanCatalogItems = await _context.CatalogItems
                .Include(ci => ci.Catalog)
                .AsNoTracking()
                .Where(ci => codes.Contains(ci.PartCode) && ci.Catalog.UserId == userId)
                .ToListAsync();

            var bestItemsDict = cleanCatalogItems
                .GroupBy(ci => ci.PartCode)
                .ToDictionary(g => g.Key, g => g
                    .OrderByDescending(x => !string.IsNullOrWhiteSpace(x.PartName) && x.PartName != "Unknown Part")
                    .ThenByDescending(x => !string.IsNullOrWhiteSpace(x.Description))
                    .First());

            return items.Select(item =>
            {
                productDict.TryGetValue(item.PartCode ?? "", out var product);
                bestItemsDict.TryGetValue(item.PartCode ?? "", out var bestItem);
                var targetItem = bestItem ?? item;

                string displayName = targetItem.PartName;
                if (string.IsNullOrWhiteSpace(displayName) || displayName == "Unknown Part")
                {
                    displayName = !string.IsNullOrWhiteSpace(targetItem.Description) ? targetItem.Description : $"Parça {targetItem.PartCode}";
                }

                return new EnrichedPartResult
                {
                    Id = targetItem.Id,
                    Code = targetItem.PartCode ?? "",
                    Name = displayName,
                    Description = targetItem.Description,
                    CatalogId = targetItem.CatalogId,
                    PageNumber = targetItem.PageNumber,
                    StockStatus = product != null ? "Stokta Var" : "Stokta Yok",
                    Price = product?.Price,
                    ImageUrl = product?.ImageUrl
                };
            }).ToList();
        }

        private bool IsPartNumber(string? term)
        {
            if (string.IsNullOrWhiteSpace(term)) return false;
            return term.Length > 2 && term.Any(char.IsDigit);
        }
    }

    #region DTOs
    public class AiChatRequestWithHistoryDto
    {
        public string? Text { get; set; }
        public IFormFile? Image { get; set; }
        public string? History { get; set; }

        // ✅ Public-view için userId alıyoruz (JWT yoksa buradan gelir)
        public string? UserId { get; set; }
    }

    public record ChatResponseDto
    {
        public string ReplySuggestion { get; init; } = string.Empty;
        public List<EnrichedPartResult> Products { get; init; } = new();
        public string? DebugInfo { get; init; }
    }

    public record EnrichedPartResult
    {
        public Guid Id { get; init; }
        public string Code { get; init; } = string.Empty;
        public string Name { get; init; } = string.Empty;
        public string? Description { get; init; }
        public string? Model { get; init; }
        public Guid CatalogId { get; init; }
        public string? PageNumber { get; init; }
        public string StockStatus { get; init; } = "Bilinmiyor";
        public decimal? Price { get; init; }
        public string? ImageUrl { get; init; }
    }
    #endregion
}