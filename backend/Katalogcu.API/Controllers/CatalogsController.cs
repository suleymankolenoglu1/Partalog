using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.API.Dtos; // DTO'ları buradan çekiyoruz
using System.Text.Json;

namespace Katalogcu.API.Controllers
{
    [Authorize]
    [Route("api/[controller]")]
    [ApiController]
    public class CatalogsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly PdfService _pdfService;
        private readonly IPartalogAiService _aiService; // ✅ YENİ AI SERVİSİ
        private readonly ILogger<CatalogsController> _logger;
        private readonly IWebHostEnvironment _env; // 📂 Dosya yolu bulucu

        public CatalogsController(
            AppDbContext context,
            PdfService pdfService,
            IPartalogAiService aiService,
            ILogger<CatalogsController> logger,
            IWebHostEnvironment env)
        {
            _context = context;
            _pdfService = pdfService;
            _aiService = aiService;
            _logger = logger;
            _env = env;
        }

        // 1. Tüm Katalogları Listele
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            var catalogs = await _context.Catalogs
                                         .Include(c => c.Pages)
                                         .OrderByDescending(c => c.CreatedDate)
                                         .ToListAsync();
            return Ok(catalogs);
        }

        // 2. Tek Bir Katalog Getir
        [AllowAnonymous]
        [HttpGet("{id}")]
        public async Task<IActionResult> GetById(Guid id)
        {
            var catalog = await _context.Catalogs
                                        .Include(c => c.Pages.OrderBy(p => p.PageNumber))
                                        .ThenInclude(p => p.Hotspots)
                                        .Include(c => c.Products
                                            .OrderBy(pr => pr.PageNumber)
                                            .ThenBy(pr => pr.RefNo)
                                            .ThenBy(pr => pr.CreatedDate)
                                        )
                                        .FirstOrDefaultAsync(c => c.Id == id);

            if (catalog == null) return NotFound("Katalog bulunamadı.");
            return Ok(catalog);
        }

        // 3. Yeni Katalog Ekle
        [HttpPost]
        public async Task<IActionResult> Create(Catalog catalog)
        {
            catalog.CreatedDate = DateTime.UtcNow;
            catalog.Status = "Processing";

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

                    catalog.Status = "Draft";
                    _context.Catalogs.Update(catalog);
                    await _context.SaveChangesAsync();
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "PDF işleme hatası");
                    catalog.Status = "Error";
                    await _context.SaveChangesAsync();
                }
            }

            return CreatedAtAction(nameof(GetById), new { id = catalog.Id }, catalog);
        }

        // 4. AI Analizi - TEK SAYFA (Hem Tablo Hem Hotspot)
        [HttpPost("{id}/analyze")]
        public async Task<IActionResult> Analyze(Guid id, [FromBody] AnalyzePageRequestDto request)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var page = await _context.CatalogPages.FirstOrDefaultAsync(p => p.Id == request.PageId);
            if (page == null) return NotFound("Sayfa bulunamadı");

            try
            {
                var filePath = GetPhysicalPath(page.ImageUrl);
                if (!System.IO.File.Exists(filePath))
                    return BadRequest($"Resim dosyası sunucuda bulunamadı: {filePath}");

                // --- A. GEMINI İLE TABLO OKUMA ---
                // Dosya stream'i açıyoruz
                using var streamTable = System.IO.File.OpenRead(filePath);
                var formFileTable = new FormFile(streamTable, 0, streamTable.Length, "file", Path.GetFileName(filePath))
                {
                    Headers = new HeaderDictionary(),
                    ContentType = "image/jpeg"
                };

                var products = await _aiService.ExtractTableAsync(formFileTable, page.PageNumber, id);

                // --- B. YOLO İLE HOTSPOT TESPİTİ ---
                // Stream kapandığı için yeni bir stream açıyoruz (veya Position=0 yapılabilir ama bu daha güvenli)
                using var streamHotspot = System.IO.File.OpenRead(filePath);
                var formFileHotspot = new FormFile(streamHotspot, 0, streamHotspot.Length, "file", Path.GetFileName(filePath))
                {
                    Headers = new HeaderDictionary(),
                    ContentType = "image/jpeg"
                };

                var hotspots = await _aiService.DetectHotspotsAsync(formFileHotspot, page.Id);

                // --- C. KAYDETME ---
                if (products.Any())
                {
                    // Eski ürünleri sil (Opsiyonel: İstersen üstüne ekle)
                    // _context.Products.RemoveRange(_context.Products.Where(p => p.CatalogId == id && p.PageNumber == page.PageNumber.ToString()));
                    _context.Products.AddRange(products);
                }

                if (hotspots.Any())
                {
                    _context.Hotspots.AddRange(hotspots);
                }

                await _context.SaveChangesAsync();

                return Ok(new
                {
                    message = "AI Analizi Başarılı (Gemini + YOLO)",
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

        // 5. AI Analizi - ÇOKLU SAYFA (Tablo Sayfası Ayrı, Resim Sayfası Ayrı)
        [HttpPost("{id}/analyze-multi")]
        public async Task<IActionResult> AnalyzeMultiPage(Guid id, [FromBody] AnalyzeMultiPageRequestDto request)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            // --- 1. TABLO SAYFASI İŞLEMLERİ (GEMINI) ---
            var tablePage = await _context.CatalogPages.FindAsync(request.TablePageId);
            int productCount = 0;

            if (tablePage != null)
            {
                var tablePath = GetPhysicalPath(tablePage.ImageUrl);
                if (System.IO.File.Exists(tablePath))
                {
                    using var stream = System.IO.File.OpenRead(tablePath);
                    var formFile = new FormFile(stream, 0, stream.Length, "file", Path.GetFileName(tablePath))
                    {
                        Headers = new HeaderDictionary(),
                        ContentType = "image/jpeg"
                    };

                    var products = await _aiService.ExtractTableAsync(formFile, tablePage.PageNumber, id);
                    if (products.Any())
                    {
                        _context.Products.AddRange(products);
                        productCount = products.Count;
                    }
                }
            }

            // --- 2. TEKNİK RESİM SAYFASI İŞLEMLERİ (YOLO) ---
            var imagePage = await _context.CatalogPages.FindAsync(request.ImagePageId);
            int hotspotCount = 0;

            if (imagePage != null)
            {
                var imagePath = GetPhysicalPath(imagePage.ImageUrl);
                if (System.IO.File.Exists(imagePath))
                {
                    using var stream = System.IO.File.OpenRead(imagePath);
                    var formFile = new FormFile(stream, 0, stream.Length, "file", Path.GetFileName(imagePath))
                    {
                        Headers = new HeaderDictionary(),
                        ContentType = "image/jpeg"
                    };

                    var hotspots = await _aiService.DetectHotspotsAsync(formFile, imagePage.Id);
                    if (hotspots.Any())
                    {
                        _context.Hotspots.AddRange(hotspots);
                        hotspotCount = hotspots.Count;
                    }
                }
            }

            await _context.SaveChangesAsync();

            return Ok(new
            {
                success = true,
                message = "Çoklu Sayfa AI Analizi Başarılı!",
                productCount = productCount,
                hotspotCount = hotspotCount,
                tablePageNumber = tablePage?.PageNumber,
                imagePageNumber = imagePage?.PageNumber
            });
        }

        // 6. Kataloğu Yayınla
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

        // 7. Katalog Sil
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            // İlişkili verileri temizle
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

        // 8. Sayfa Verilerini Temizle
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

        // --- YARDIMCI METODLAR ---

        /// <summary>
        /// URL'den (http://localhost/uploads/...) fiziksel dosya yolunu (C:\wwwroot\uploads\...) bulur
        /// </summary>
        private string GetPhysicalPath(string url)
        {
            var fileName = Path.GetFileName(url);
            
            // 1. Önce "uploads/pages" klasörüne bak
            var pathPages = Path.Combine(_env.WebRootPath, "uploads", "pages", fileName);
            if (System.IO.File.Exists(pathPages)) return pathPages;

            // 2. Yoksa "uploads" köküne bak
            var pathRoot = Path.Combine(_env.WebRootPath, "uploads", fileName);
            if (System.IO.File.Exists(pathRoot)) return pathRoot;

            return pathPages; // Varsayılan olarak ilk yolu dön
        }
    }
}