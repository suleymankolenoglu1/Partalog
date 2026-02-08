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

                // --- NİYET ANALİZİ (Yeni yapı) ---
                string? searchTerm = null;
                string? intent = null;
                string? partCode = null;
                double? confidence = null;
                List<string> multiTerms = new();

                if (aiResponse.DebugIntent is JsonElement intentElement)
                {
                    if (intentElement.TryGetProperty("intent", out var it)) intent = it.GetString();
                    if (intentElement.TryGetProperty("part_name", out var pn)) searchTerm = pn.GetString();
                    if (intentElement.TryGetProperty("part_code", out var pc)) partCode = pc.GetString();

                    if (intentElement.TryGetProperty("confidence", out var cf) && cf.ValueKind == JsonValueKind.Number)
                        confidence = cf.GetDouble();

                    // ✅ Multi-part yakalama (parts[])
                    multiTerms = ExtractPartsFromDebugIntent(intentElement);
                }

                if (confidence.HasValue && confidence.Value < 0.60)
                {
                    _logger.LogWarning("Low intent confidence: {Confidence} | Intent: {Intent} | Text: {Text}",
                        confidence.Value, intent ?? "n/a", request.Text);
                }

                // CHAT intent’te arama yapma
                if (string.Equals(intent, "CHAT", StringComparison.OrdinalIgnoreCase))
                {
                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = aiResponse.Answer ?? "Buyur ustam?",
                        Products = new List<EnrichedPartResult>(),
                        DebugInfo = $"Intent: {intent} | Confidence: {confidence?.ToString("0.00") ?? "n/a"}"
                    });
                }

                // ✅ HELP intent
                if (string.Equals(intent, "HELP", StringComparison.OrdinalIgnoreCase))
                {
                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = "Ustam, hangi bilgiyi istersin? (fiyat, stok, uyumluluk, parça kodu) diye sor.",
                        Products = new List<EnrichedPartResult>(),
                        DebugInfo = $"Intent: HELP | Confidence: {confidence?.ToString("0.00") ?? "n/a"}"
                    });
                }

                // ✅ SEARCH intent + multi-part -> yan yana listele
                if (string.Equals(intent, "SEARCH", StringComparison.OrdinalIgnoreCase) && multiTerms.Count > 1)
                {
                    List<CompareGroupDto> compareGroups;

                    // ✅ Prefer Python semantic sources when available
                    if (aiResponse.Sources != null && aiResponse.Sources.Any())
                    {
                        // Group Python sources by query field
                        var groupedSources = aiResponse.Sources
                            .Where(s => !string.IsNullOrWhiteSpace(s.Query))
                            .GroupBy(s => s.Query)
                            .ToList();

                        if (groupedSources.Any())
                        {
                            // Process grouped Python sources
                            compareGroups = new List<CompareGroupDto>();
                            foreach (var group in groupedSources)
                            {
                                var products = await EnrichPythonSourcesAsync(group.ToList(), userId);
                                
                                compareGroups.Add(new CompareGroupDto
                                {
                                    Query = group.Key!,
                                    Results = products
                                });
                            }
                        }
                        else
                        {
                            // Python sources exist but no query field, fallback to term-based search
                            compareGroups = await BuildCompareGroupsFromTermsAsync(multiTerms, userId);
                        }
                    }
                    else
                    {
                        // No Python sources, fallback to existing SearchByCodeAsync logic
                        compareGroups = await BuildCompareGroupsFromTermsAsync(multiTerms, userId);
                    }

                    var anyResults = compareGroups.Any(g => g.Results.Any());

                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = anyResults
                            ? "Birden fazla parça için sonuçları ayrı ayrı listeledim."
                            : "Birden fazla parça istedin ama uygun sonuç bulamadım.",
                        Products = new List<EnrichedPartResult>(),
                        CompareGroups = compareGroups,
                        DebugInfo = $"Intent: SEARCH | Terms: {string.Join(", ", multiTerms)}"
                    });
                }

                // ✅ Intent bazlı özel akışlar
                var intentQuery = partCode ?? searchTerm ?? request.Text;

                if (string.Equals(intent, "PRICE", StringComparison.OrdinalIgnoreCase))
                {
                    var priceResults = await SearchByCodeAsync(intentQuery, userId);
                    var priceProducts = await EnrichResultsAsync(priceResults, userId);

                    if (!priceProducts.Any())
                    {
                        return Ok(new ChatResponseDto
                        {
                            ReplySuggestion = "Fiyat için uygun parça bulamadım. Kod veya isim net mi?",
                            Products = new List<EnrichedPartResult>(),
                            DebugInfo = $"Intent: PRICE | Code: {intentQuery}"
                        });
                    }

                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = $"Fiyat bilgisi bulunan {priceProducts.Count} parça buldum.",
                        Products = priceProducts,
                        DebugInfo = $"Intent: PRICE | Code: {intentQuery}"
                    });
                }

                if (string.Equals(intent, "STOCK", StringComparison.OrdinalIgnoreCase))
                {
                    var stockResults = await SearchByCodeAsync(intentQuery, userId);
                    var stockProducts = await EnrichResultsAsync(stockResults, userId);

                    if (!stockProducts.Any())
                    {
                        return Ok(new ChatResponseDto
                        {
                            ReplySuggestion = "Stok için uygun parça bulamadım.",
                            Products = new List<EnrichedPartResult>(),
                            DebugInfo = $"Intent: STOCK | Code: {intentQuery}"
                        });
                    }

                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = "Stok durumlarını listeledim.",
                        Products = stockProducts,
                        DebugInfo = $"Intent: STOCK | Code: {intentQuery}"
                    });
                }

                if (string.Equals(intent, "COMPATIBILITY", StringComparison.OrdinalIgnoreCase))
                {
                    var compResults = await SearchByCodeAsync(intentQuery, userId);
                    var compProducts = await EnrichResultsAsync(compResults, userId);

                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = compProducts.Any()
                            ? "Uyumlu model bilgilerini listeledim."
                            : "Uyumluluk için parça bulunamadı.",
                        Products = compProducts,
                        DebugInfo = $"Intent: COMPATIBILITY | Code: {intentQuery}"
                    });
                }

                if (string.Equals(intent, "COMPARE", StringComparison.OrdinalIgnoreCase))
                {
                    var compareQuery = partCode ?? searchTerm ?? request.Text;
                    var terms = ExtractCompareTerms(compareQuery);

                    var compareGroups = new List<CompareGroupDto>();

                    foreach (var term in terms)
                    {
                        var compareResults = await SearchByCodeAsync(term, userId);
                        var compareProducts = await EnrichResultsAsync(compareResults, userId);

                        compareGroups.Add(new CompareGroupDto
                        {
                            Query = term,
                            Results = compareProducts
                        });
                    }

                    return Ok(new ChatResponseDto
                    {
                        ReplySuggestion = compareGroups.Any()
                            ? "Karşılaştırma için parçaları yan yana listeledim."
                            : "Karşılaştırma için uygun parça bulamadım.",
                        Products = new List<EnrichedPartResult>(),
                        CompareGroups = compareGroups,
                        DebugInfo = $"Intent: COMPARE | Terms: {string.Join(", ", terms)}"
                    });
                }

                // 4. PARÇA LİSTESİ HAZIRLIĞI
                List<EnrichedPartResult> finalProducts = new();

                // SENARYO A: Python kaynak bulduysa
                if (aiResponse.Sources != null && aiResponse.Sources.Any())
                {
                    finalProducts = await EnrichPythonSourcesAsync(aiResponse.Sources, userId);
                }
                // SENARYO B: Python bulamadıysa ama Kod yakaladıysa
                else if (!string.IsNullOrWhiteSpace(partCode) && IsPartNumber(partCode))
                {
                    var fallbackResults = await SearchByCodeAsync(partCode, userId);
                    finalProducts = await EnrichResultsAsync(fallbackResults, userId);
                }
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
                    DebugInfo = $"Intent: {intent ?? "Yok"} | Search: {searchTerm ?? "Yok"} | Code: {partCode ?? "Yok"} | Confidence: {confidence?.ToString("0.00") ?? "n/a"}"
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Chat Controller Hatası");
                return StatusCode(500, new { error = "Sistem hatası: " + ex.Message });
            }
        }

        // --- YARDIMCI METODLAR ---

        private static List<string> ExtractPartsFromDebugIntent(JsonElement intentElement)
        {
            var terms = new List<string>();

            if (intentElement.TryGetProperty("parts", out var parts) && parts.ValueKind == JsonValueKind.Array)
            {
                foreach (var part in parts.EnumerateArray())
                {
                    if (part.TryGetProperty("part_code", out var pc) && pc.ValueKind == JsonValueKind.String)
                    {
                        var value = pc.GetString();
                        if (!string.IsNullOrWhiteSpace(value))
                        {
                            terms.Add(value);
                            continue;
                        }
                    }

                    if (part.TryGetProperty("part_name", out var pn) && pn.ValueKind == JsonValueKind.String)
                    {
                        var value = pn.GetString();
                        if (!string.IsNullOrWhiteSpace(value))
                        {
                            terms.Add(value);
                        }
                    }
                }
            }

            return terms.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        }

        private static List<string> ExtractCompareTerms(string? text)
        {
            if (string.IsNullOrWhiteSpace(text)) return new List<string>();

            var separators = new[] { " ve ", " & ", ",", ";", "/" };
            var parts = separators.Aggregate(new List<string> { text }, (list, sep) =>
                list.SelectMany(x => x.Split(sep, StringSplitOptions.RemoveEmptyEntries)).ToList()
            );

            return parts
                .Select(p => p.Trim())
                .Where(p => !string.IsNullOrWhiteSpace(p))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
        }

        private async Task<List<CompareGroupDto>> BuildCompareGroupsFromTermsAsync(List<string> terms, Guid userId)
        {
            var compareGroups = new List<CompareGroupDto>();

            foreach (var term in terms)
            {
                var results = await SearchByCodeAsync(term, userId);
                var products = await EnrichResultsAsync(results, userId);

                compareGroups.Add(new CompareGroupDto
                {
                    Query = term,
                    Results = products
                });
            }

            return compareGroups;
        }

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

                // ✅ Use new Python fields with fallback to legacy fields
                string? sourceDescription = source.Description ?? source.LegacyDescription;
                string? sourceModel = source.MachineModel ?? source.LegacyModel;

                enrichedList.Add(new EnrichedPartResult
                {
                    Id = catItem?.Id ?? Guid.Empty,
                    Code = source.Code,
                    Name = finalName,
                    Description = catItem?.Description ?? sourceDescription,
                    Model = sourceModel,
                    CatalogId = catItem?.CatalogId ?? Guid.Empty,
                    PageNumber = catItem?.PageNumber,
                    StockStatus = product != null ? "Stokta Var" : "Stokta Yok",
                    Price = product?.Price,
                    ImageUrl = !string.IsNullOrWhiteSpace(catItem?.VisualImageUrl)
                        ? catItem.VisualImageUrl
                        : product?.ImageUrl
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
                    ImageUrl = !string.IsNullOrWhiteSpace(targetItem.VisualImageUrl)
                        ? targetItem.VisualImageUrl
                        : product?.ImageUrl
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

        // ✅ Yan yana karşılaştırma için
        public List<CompareGroupDto>? CompareGroups { get; init; }
    }

    public record CompareGroupDto
    {
        public string Query { get; init; } = string.Empty;
        public List<EnrichedPartResult> Results { get; init; } = new();
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