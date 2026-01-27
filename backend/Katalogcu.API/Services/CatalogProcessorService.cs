using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using System.Net; 

namespace Katalogcu.API.Services;

public class CatalogProcessorService
{
    private readonly AppDbContext _context;
    private readonly IPartalogAiService _aiService;
    private readonly IWebHostEnvironment _env;
    private readonly ILogger<CatalogProcessorService> _logger;

    public CatalogProcessorService(
        AppDbContext context, 
        IPartalogAiService aiService, 
        IWebHostEnvironment env,
        ILogger<CatalogProcessorService> logger)
    {
        _context = context;
        _aiService = aiService;
        _env = env;
        _logger = logger;
    }

    public async Task ProcessCatalogAsync(Guid catalogId)
    {
        _logger.LogInformation($"🚀 Otonom İşlem Başladı: {catalogId}");

        var pages = await _context.CatalogPages
            .Where(p => p.CatalogId == catalogId)
            .OrderBy(p => p.PageNumber)
            .ToListAsync();

        if (!pages.Any()) 
        {
            _logger.LogWarning("⚠️ Hiç sayfa bulunamadı!");
            return;
        }

        // --- AKILLI HAFIZA ---
        Guid? activeDrawingPageId = null; 
        int activeDrawingPageNumber = -999; // Mesafeyi ölçmek için sayfa numarasını tutuyoruz

        foreach (var page in pages)
        {
            _logger.LogInformation($"🔄 Sayfa {page.PageNumber} işleniyor...");

            var fullPath = GetFullPath(page.ImageUrl);
            if (fullPath == null) 
            {
                _logger.LogError($"❌ DOSYA BULUNAMADI! Sayfa: {page.PageNumber}");
                continue; 
            }

            try 
            {
                using (var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read))
                {
                    var formFile = CreateFormFile(stream, fullPath);

                    // 1. ANALİZ
                    var analysis = await _aiService.AnalyzePageTitleAsync(formFile);
                    
                    // Null ve Başlık Güvenliği
                    if (analysis == null) analysis = new AiAnalysisResult();
                    var safeTitle = !string.IsNullOrEmpty(analysis.Title) ? analysis.Title : $"Sayfa {page.PageNumber}";

                    // 🛡️ ÖNCELİK KİLİDİ: Resimse, tablo özelliğini zorla kapat.
                    if (analysis.IsTechnicalDrawing)
                    {
                        analysis.IsPartsList = false; 
                    }

                    if (analysis.IsTechnicalDrawing)
                    {
                        // ---------------------------------------------------------
                        // DURUM A: YENİ TEKNİK RESİM (ZİNCİR BAŞLANGICI)
                        // ---------------------------------------------------------
                        _logger.LogInformation($"✅ Teknik Resim Saptandı: '{safeTitle}'");
                        
                        // Hafızayı Güncelle (Yeni Patron Bu Sayfa)
                        activeDrawingPageId = page.Id;
                        activeDrawingPageNumber = page.PageNumber; // Sayfa numarasını kaydet
                        
                        page.AiDescription = safeTitle;

                        // 🧹 TEMİZLİK: Eski verileri sil
                        var oldProducts = await _context.Products.Where(p => p.PageId == page.Id).ToListAsync();
                        if (oldProducts.Any())
                        {
                            _context.Products.RemoveRange(oldProducts);
                            _logger.LogInformation($"🧹 TEMİZLİK: {oldProducts.Count} eski ürün silindi.");
                        }

                        var oldSpots = await _context.Hotspots.Where(h => h.PageId == page.Id).ToListAsync();
                        _context.Hotspots.RemoveRange(oldSpots);
                        
                        // SADECE YOLO Çalıştır
                        stream.Position = 0; 
                        var hotspots = await _aiService.DetectHotspotsAsync(formFile, page.Id);
                        
                        if (hotspots.Any())
                        {
                            await _context.Hotspots.AddRangeAsync(hotspots);
                            _logger.LogInformation($"🎯 {hotspots.Count} adet koordinat bulundu.");
                        }
                    }
                    else if (analysis.IsPartsList)
                    {
                        // ---------------------------------------------------------
                        // DURUM B: PARÇA LİSTESİ (TABLO)
                        // ---------------------------------------------------------
                        
                        // 📏 MESAFE KURALI (DISTANCE RULE)
                        // Tablo, son teknik resimden en fazla 2 sayfa sonra gelebilir.
                        // Eğer fark > 2 ise, bu tablo o resme ait değildir. Zinciri kır.
                        int pageGap = page.PageNumber - activeDrawingPageNumber;

                        if (activeDrawingPageId != null && pageGap > 0 && pageGap <= 2)
                        {
                            _logger.LogInformation($"📦 Tablo Okunuyor... (Fark: {pageGap} sayfa) -> Hedef Resim: {activeDrawingPageNumber}");

                            stream.Position = 0;
                            var products = await _aiService.ExtractTableAsync(formFile, page.PageNumber, catalogId);

                            if (products.Any())
                            {
                                // İspiyoncu Log (Sarı)
                                _logger.LogWarning($"🧐 TABLO İÇERİĞİ ({products.Count} satır): {products.FirstOrDefault()?.Code} vb...");

                                foreach (var p in products)
                                {
                                    // Parçayı TABLOYA DEĞİL, önceki RESME (activeDrawingPageId) ekle
                                    p.PageId = activeDrawingPageId.Value; 
                                    _context.Products.Add(p);
                                }
                                _logger.LogInformation($"💾 {products.Count} parça başarıyla önceki resme eklendi.");
                            }
                        }
                        else
                        {
                            // Mesafe çok fazlaysa veya resim yoksa veriyi çöpe atma, ama bağlama da.
                            if (activeDrawingPageId == null)
                                _logger.LogWarning("⚠️ Tablo bulundu ama öncesinde Teknik Resim yoktu. Veri atlandı.");
                            else
                                _logger.LogWarning($"⛔ GÜVENLİK DURUŞU: Tablo bulundu ama son resim {pageGap} sayfa geride kaldı. Bağlantı kurulmadı.");
                            
                            // Zinciri kopar
                            activeDrawingPageId = null;
                            activeDrawingPageNumber = -999;
                        }
                    }
                    else
                    {
                        // ---------------------------------------------------------
                        // DURUM C: ALAKASIZ SAYFA (Zinciri Kır)
                        // ---------------------------------------------------------
                        _logger.LogInformation("ℹ️ Standart Sayfa. Akış sıfırlandı.");
                        
                        // Araya başka tür sayfa girdiyse, sonraki tabloların önceki resme yapışmasını engelle
                        activeDrawingPageId = null; 
                        activeDrawingPageNumber = -999;

                        if (string.IsNullOrEmpty(page.AiDescription))
                        {
                            page.AiDescription = safeTitle;
                        }
                    }
                } 
                
                await _context.SaveChangesAsync();
            }
            catch (Exception ex)
            {
                var msg = ex.InnerException != null ? ex.InnerException.Message : ex.Message;
                _logger.LogError(ex, $"❌ Sayfa {page.PageNumber} hatası: {msg}");
            }
        }
        
        // --- EŞLEŞTİRME ---
        await MatchHotspotsToProducts(catalogId);
        _logger.LogInformation($"🏁 İşlem Tamamlandı: {catalogId}");
    }

    private async Task MatchHotspotsToProducts(Guid catalogId)
    {
        var pages = await _context.CatalogPages
            .Include(p => p.Hotspots)
            .Where(p => p.CatalogId == catalogId)
            .ToListAsync();

        foreach (var page in pages)
        {
            var pageProducts = await _context.Products
                .Where(p => p.PageId == page.Id)
                .ToListAsync();

            if (!page.Hotspots.Any() || !pageProducts.Any()) continue;

            foreach (var spot in page.Hotspots)
            {
                if (string.IsNullOrEmpty(spot.Label)) continue;

                var matched = pageProducts.FirstOrDefault(p => 
                    (p.RefNo != 0 && p.RefNo.ToString() == spot.Label) || 
                    (p.RefNo != 0 && spot.Label.TrimStart('0') == p.RefNo.ToString())
                );

                if (matched != null)
                {
                    spot.ProductId = matched.Id;
                }
            }
        }
        await _context.SaveChangesAsync();
    }

    private IFormFile CreateFormFile(Stream stream, string fullPath)
    {
        return new FormFile(stream, 0, stream.Length, "file", Path.GetFileName(fullPath))
        {
            Headers = new HeaderDictionary(), ContentType = "image/png"
        };
    }

    private string? GetFullPath(string? url)
    {
        if (string.IsNullOrEmpty(url)) return null;
        string cleanPath = WebUtility.UrlDecode(url).Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar).TrimStart(Path.DirectorySeparatorChar);
        var fullPath = Path.Combine(_env.WebRootPath, cleanPath);
        if (!File.Exists(fullPath) && cleanPath.Contains("uploads"))
        {
             var uploadIndex = cleanPath.LastIndexOf("uploads");
             if (uploadIndex > -1) {
                 var subPath = cleanPath.Substring(uploadIndex);
                 var altPath = Path.Combine(_env.WebRootPath, subPath);
                 if (File.Exists(altPath)) return altPath;
             }
        }
        return File.Exists(fullPath) ? fullPath : null;
    }
}