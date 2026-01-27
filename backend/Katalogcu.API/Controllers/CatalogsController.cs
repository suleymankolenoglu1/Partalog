using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.API.Dtos;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection; // ✨ Background Scope için gerekli

namespace Katalogcu.API.Controllers
{
    [Authorize]
    [Route("api/[controller]")]
    [ApiController]
    public class CatalogsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly PdfService _pdfService;
        private readonly IPartalogAiService _aiService;
        private readonly ILogger<CatalogsController> _logger;
        private readonly IWebHostEnvironment _env;
        
        // ✨ YENİ: Arka plan işlemleri için Scope Factory (Processor'ı buradan üreteceğiz)
        private readonly IServiceScopeFactory _scopeFactory;

        public CatalogsController(
            AppDbContext context,
            PdfService pdfService,
            IPartalogAiService aiService,
            ILogger<CatalogsController> logger,
            IWebHostEnvironment env,
            IServiceScopeFactory scopeFactory) // ✨ Inject ettik
        {
            _context = context;
            _pdfService = pdfService;
            _aiService = aiService;
            _logger = logger;
            _env = env;
            _scopeFactory = scopeFactory;
        }

        // ==========================================
        // 🔥 1. DASHBOARD ISTATISTIKLERI
        // ==========================================
        [HttpGet("stats")]
        public async Task<IActionResult> GetStats()
        {
            var totalCatalogs = await _context.Catalogs.CountAsync();
            var totalParts = await _context.Products.CountAsync();
            var totalViews = 15240; // Temsili veri

            var pendingCount = await _context.Catalogs
                .CountAsync(c => c.Status == "Processing" || c.Status == "Pending" || c.Status == "Uploading");

            var recentCatalogs = await _context.Catalogs
                .OrderByDescending(c => c.CreatedDate)
                .Take(5)
                .Select(c => new 
                {
                    c.Id,
                    c.Name,
                    c.Status,
                    PartCount = _context.Products.Count(p => p.CatalogId == c.Id),
                    c.CreatedDate
                })
                .ToListAsync();

            return Ok(new
            {
                TotalCatalogs = totalCatalogs,
                TotalParts = totalParts,
                TotalViews = totalViews,
                PendingCount = pendingCount,
                RecentCatalogs = recentCatalogs
            });
        }

        // ==========================================
        // 2. LISTELEME & DETAY
        // ==========================================
        
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            var catalogs = await _context.Catalogs
                                         .Include(c => c.Pages)
                                         .OrderByDescending(c => c.CreatedDate)
                                         .ToListAsync();
            return Ok(catalogs);
        }

        // 🛑 PERFORMANCE FIX: Ürünleri (Products) buradan kaldırdık. Ayrı çekeceğiz.
        // 🛑 ROUTING FIX: {id:guid} ile stats çakışmasını önledik.
        [AllowAnonymous]
        [HttpGet("{id:guid}")]
        public async Task<IActionResult> GetById(Guid id)
        {
            var catalog = await _context.Catalogs
                                        .Include(c => c.Pages.OrderBy(p => p.PageNumber))
                                        .ThenInclude(p => p.Hotspots)
                                        // .Include(c => c.Products...) <-- BURAYI SİLDİK (Hız için)
                                        .FirstOrDefaultAsync(c => c.Id == id);

            if (catalog == null) return NotFound("Katalog bulunamadı.");
            return Ok(catalog);
        }

        // ==========================================
        // 3. EKLEME & ARKA PLAN İŞLEME (CORE)
        // ==========================================

        [HttpPost]
        public async Task<IActionResult> Create(Catalog catalog)
        {
            catalog.CreatedDate = DateTime.UtcNow;
            catalog.Status = "Uploading"; 

            _context.Catalogs.Add(catalog);
            await _context.SaveChangesAsync();

            if (!string.IsNullOrEmpty(catalog.PdfUrl))
            {
                try
                {
                    var fileName = Path.GetFileName(catalog.PdfUrl);
                    var pageUrls = await _pdfService.ConvertPdfToImages(fileName);

                    int pageNum = 1;
                    var newPages = new List<CatalogPage>();

                    foreach (var imgPath in pageUrls)
                    {
                        var fullUrl = $"{Request.Scheme}://{Request.Host}/{imgPath}";
                        newPages.Add(new CatalogPage
                        {
                            CatalogId = catalog.Id,
                            PageNumber = pageNum++,
                            ImageUrl = fullUrl
                        });
                    }
                    _context.CatalogPages.AddRange(newPages);

                    catalog.Status = "ReadyToProcess"; 
                    _context.Catalogs.Update(catalog);
                    await _context.SaveChangesAsync();
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "PDF işleme hatası");
                    catalog.Status = "Error";
                    await _context.SaveChangesAsync();
                    return StatusCode(500, "PDF işlenirken hata oluştu.");
                }
            }

            return CreatedAtAction(nameof(GetById), new { id = catalog.Id }, catalog);
        }

        // 🔥 GÜNCELLENMİŞ OTONOM START METODU (FIRE-AND-FORGET) 🚀
        [HttpPost("{id}/start-ai-process")]
        public async Task<IActionResult> StartAutonomousProcess(Guid id)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            if (catalog.Status == "Processing") 
                return BadRequest("Bu katalog zaten işleniyor.");

            // Durumu hemen güncelle
            catalog.Status = "Processing"; 
            await _context.SaveChangesAsync();

            // 🔥 İşlemi ARKA PLANA at (Task.Run)
            _ = Task.Run(async () => 
            {
                // Yeni scope açıyoruz (Controller kapansa bile bu yaşar)
                using (var scope = _scopeFactory.CreateScope())
                {
                    try
                    {
                        var scopedProcessor = scope.ServiceProvider.GetRequiredService<CatalogProcessorService>();
                        
                        // Uzun süren işlemi başlat
                        await scopedProcessor.ProcessCatalogAsync(id);

                        // Başarılı olursa durumu güncelle
                        var scopedContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();
                        var cat = await scopedContext.Catalogs.FindAsync(id);
                        if(cat != null) {
                            cat.Status = "AI_Completed";
                            cat.UpdatedDate = DateTime.UtcNow;
                            await scopedContext.SaveChangesAsync();
                        }
                    }
                    catch (Exception ex)
                    {
                        _logger.LogError(ex, $"Arka plan işlem hatası: {id}");
                        
                        // Hata durumunu veritabanına yaz
                        using (var errorScope = _scopeFactory.CreateScope())
                        {
                            var errorDb = errorScope.ServiceProvider.GetRequiredService<AppDbContext>();
                            var cat = await errorDb.Catalogs.FindAsync(id);
                            if (cat != null)
                            {
                                cat.Status = "Error";
                                await errorDb.SaveChangesAsync();
                            }
                        }
                    }
                }
            });

            // Frontend'e HEMEN cevap ver (202 Accepted)
            return Accepted(new 
            { 
                message = "AI Analizi arka planda başlatıldı.", 
                catalogId = id,
                status = "Processing"
            });
        }

        // ==========================================
        // 4. MANUEL ANALİZ METOTLARI (OPSİYONEL)
        // ==========================================

        [HttpPost("{id}/analyze")]
        public async Task<IActionResult> Analyze(Guid id, [FromBody] AnalyzePageRequestDto request)
        {
            // Eski manuel analiz kodu (Aynen kalabilir veya silinebilir)
             var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var page = await _context.CatalogPages.FirstOrDefaultAsync(p => p.Id == request.PageId);
            if (page == null) return NotFound("Sayfa bulunamadı");

            try
            {
                var filePath = GetPhysicalPath(page.ImageUrl);
                if (!System.IO.File.Exists(filePath))
                    return BadRequest($"Resim dosyası sunucuda bulunamadı: {filePath}");

                using var streamTable = System.IO.File.OpenRead(filePath);
                var formFileTable = new FormFile(streamTable, 0, streamTable.Length, "file", Path.GetFileName(filePath))
                {
                    Headers = new HeaderDictionary(),
                    ContentType = "image/jpeg"
                };

                var products = await _aiService.ExtractTableAsync(formFileTable, page.PageNumber, id);

                using var streamHotspot = System.IO.File.OpenRead(filePath);
                var formFileHotspot = new FormFile(streamHotspot, 0, streamHotspot.Length, "file", Path.GetFileName(filePath))
                {
                    Headers = new HeaderDictionary(),
                    ContentType = "image/jpeg"
                };

                var hotspots = await _aiService.DetectHotspotsAsync(formFileHotspot, page.Id);

                if (products.Any()) _context.Products.AddRange(products);
                if (hotspots.Any()) _context.Hotspots.AddRange(hotspots);

                await _context.SaveChangesAsync();

                return Ok(new
                {
                    message = "Manuel Analiz Başarılı",
                    productCount = products.Count,
                    hotspotCount = hotspots.Count
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "AI Analiz Hatası");
                return StatusCode(500, $"AI Hatası: {ex.Message}");
            }
        }

        [HttpPost("{id}/analyze-multi")]
        public async Task<IActionResult> AnalyzeMultiPage(Guid id, [FromBody] AnalyzeMultiPageRequestDto request)
        {
            return Ok(new { message = "Bu endpoint artık otonom sistem tarafından kapsanıyor." });
        }

        // ==========================================
        // 5. YÖNETİM (YAYINLA / SİL / TEMİZLE)
        // ==========================================

        [HttpPost("{id}/publish")]
        public async Task<IActionResult> Publish(Guid id)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound();

            catalog.Status = "Published";
            catalog.UpdatedDate = DateTime.UtcNow;

            await _context.SaveChangesAsync();

            return Ok(new { message = "Katalog yayına alındı", status = catalog.Status });
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var pageIds = await _context.CatalogPages.Where(p => p.CatalogId == id).Select(p => p.Id).ToListAsync();
            var productIds = await _context.Products.Where(p => p.CatalogId == id).Select(p => p.Id).ToListAsync();

            if (pageIds.Any() || productIds.Any())
            {
                await _context.Hotspots
                    .Where(h => pageIds.Contains(h.PageId) || (h.ProductId != null && productIds.Contains(h.ProductId.Value)))
                    .ExecuteDeleteAsync();
            }

            if (pageIds.Any()) await _context.CatalogPages.Where(p => pageIds.Contains(p.Id)).ExecuteDeleteAsync();
            if (productIds.Any()) await _context.Products.Where(p => productIds.Contains(p.Id)).ExecuteDeleteAsync();

            _context.Catalogs.Remove(catalog);
            await _context.SaveChangesAsync();

            return NoContent();
        }

        [HttpDelete("{id}/pages/{pageId}/clear")]
        public async Task<IActionResult> ClearPageData(Guid id, Guid pageId)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var page = await _context.CatalogPages.FindAsync(pageId);
            if (page == null) return NotFound("Sayfa bulunamadı.");

            var deletedHotspots = await _context.Hotspots.Where(h => h.PageId == pageId).ExecuteDeleteAsync();
            var deletedProducts = await _context.Products.Where(p => p.CatalogId == id && p.PageNumber == page.PageNumber.ToString()).ExecuteDeleteAsync();

            return Ok(new
            {
                message = "Sayfa verileri temizlendi",
                deletedProducts = deletedProducts,
                deletedHotspots = deletedHotspots
            });
        }

        private string GetPhysicalPath(string url)
        {
            var fileName = Path.GetFileName(url);
            var pathPages = Path.Combine(_env.WebRootPath, "uploads", "pages", fileName);
            if (System.IO.File.Exists(pathPages)) return pathPages;

            var pathRoot = Path.Combine(_env.WebRootPath, "uploads", fileName);
            if (System.IO.File.Exists(pathRoot)) return pathRoot;

            return pathPages;
        }
    }
}