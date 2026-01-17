using Katalogcu.API.Services;
using Katalogcu. Domain.Entities;
using Katalogcu.Infrastructure. Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft. EntityFrameworkCore;
using System. Text.Json;

namespace Katalogcu.API.Controllers
{
    [Authorize]
    [Route("api/[controller]")]
    [ApiController]
    public class CatalogsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly PdfService _pdfService;
        private readonly PaddleTableService _paddleService;
        private readonly ILogger<CatalogsController> _logger;

        public CatalogsController(
            AppDbContext context, 
            PdfService pdfService, 
            PaddleTableService paddleService,
            ILogger<CatalogsController> logger)
        {
            _context = context;
            _pdfService = pdfService;
            _paddleService = paddleService;
            _logger = logger;
        }

        // 1. Tüm Katalogları Listele
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            var catalogs = await _context. Catalogs
                                         .Include(c => c.Pages)
                                         .OrderByDescending(c => c.CreatedDate)
                                         . ToListAsync();
            return Ok(catalogs);
        }

        // 2. Tek Bir Katalog Getir
        [AllowAnonymous]
        [HttpGet("{id}")]
        public async Task<IActionResult> GetById(Guid id)
        {
            var catalog = await _context.Catalogs
                                        .Include(c => c.Pages. OrderBy(p => p.PageNumber))
                                        .ThenInclude(p => p. Hotspots)
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
            catalog.CreatedDate = DateTime. UtcNow;
            catalog.Status = "Processing";

            _context.Catalogs.Add(catalog);
            await _context. SaveChangesAsync();

            if (! string.IsNullOrEmpty(catalog.PdfUrl))
            {
                try
                {
                    var fileName = Path.GetFileName(catalog. PdfUrl);
                    var pageUrls = await _pdfService. ConvertPdfToImages(fileName);

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
                    _context. Catalogs.Update(catalog);
                    await _context.SaveChangesAsync();
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "PDF işleme hatası");
                    catalog. Status = "Error";
                    await _context.SaveChangesAsync();
                }
            }

            return CreatedAtAction(nameof(GetById), new { id = catalog.Id }, catalog);
        }

        // 4. AI Analizi - PaddleOCR ile
        [HttpPost("{id}/analyze")]
        public async Task<IActionResult> Analyze(Guid id, [FromBody] AnalyzeRequest request)
        {
            var catalog = await _context.Catalogs
                . Include(c => c.Pages)
                .FirstOrDefaultAsync(c => c. Id == id);
                
            if (catalog == null) 
                return NotFound("Katalog bulunamadı.");
            if (string.IsNullOrEmpty(catalog.PdfUrl)) 
                return BadRequest("Kataloğun PDF dosyası yok.");

            var page = await _context.CatalogPages.FindAsync(Guid.Parse(request.PageId));
            if (page == null) 
                return NotFound("Sayfa bulunamadı");

            // Servis sağlık kontrolü
            var isHealthy = await _paddleService.IsHealthyAsync();
            if (!isHealthy)
            {
                return StatusCode(503, new
                {
                    error = "PaddleOCR servisi kullanılamıyor",
                    message = "Python servisi çalışıyor mu kontrol edin:  http://localhost:8000/health"
                });
            }

            try
            {
                var defaultRect = new RectObj { X = 0, Y = 0, W = 100, H = 100 };
                var tableRect = request.TableRect ?? defaultRect;
                var imageRect = request.ImageRect ?? defaultRect;

                string pdfFileName = Path.GetFileName(catalog.PdfUrl);

                _logger.LogInformation("🐼 PaddleOCR Analizi Başlıyor - Sayfa {PageNumber}", page.PageNumber);

                var result = await _paddleService.AnalyzeCatalogPageAsync(
                    pdfFileName,
                    page.PageNumber,
                    page.PageNumber,
                    page.ImageUrl,
                    id,
                    page.Id,
                    tableRect,
                    imageRect
                );

                LogAnalysisResult(result.products);

                if (result.products.Any())
                {
                    _context.Products.AddRange(result.products);
                }

                if (result.hotspots. Any())
                {
                    _context.Hotspots. AddRange(result.hotspots);
                }

                await _context.SaveChangesAsync();

                return Ok(new
                {
                    message = "AI Analizi Başarılı! ",
                    engine = "PaddleOCR",
                    productCount = result.products.Count,
                    hotspotCount = result.hotspots.Count
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "PaddleOCR Analiz Hatası");
                return StatusCode(500, $"AI Hatası: {ex.Message}");
            }
        }

        // 5. AI Analizi (Çoklu Sayfa Desteği) - PaddleOCR ile
        [HttpPost("{id}/analyze-multi")]
        public async Task<IActionResult> AnalyzeMultiPage(Guid id, [FromBody] MultiPageAnalyzeRequest request)
        {
            var catalog = await _context. Catalogs
                .Include(c => c.Pages)
                .FirstOrDefaultAsync(c => c.Id == id);
                
            if (catalog == null) 
                return NotFound("Katalog bulunamadı.");
            if (string.IsNullOrEmpty(catalog.PdfUrl)) 
                return BadRequest("Kataloğun PDF dosyası yok.");

            // Servis sağlık kontrolü
            var isHealthy = await _paddleService.IsHealthyAsync();
            if (!isHealthy)
            {
                return StatusCode(503, new
                {
                    error = "PaddleOCR servisi kullanılamıyor",
                    message = "Python servisi çalışıyor mu kontrol edin: http://localhost:8000/health"
                });
            }

            // Tablo sayfası kontrolü
            if (! Guid.TryParse(request.TablePageId, out Guid tablePageGuid))
                return BadRequest("Geçersiz TablePageId formatı.");

            var tablePage = catalog.Pages.FirstOrDefault(p => p.Id == tablePageGuid);
            if (tablePage == null) 
                return NotFound("Tablo sayfası bulunamadı.");

            // Teknik resim sayfası kontrolü
            if (!Guid.TryParse(request.ImagePageId, out Guid imagePageGuid))
                return BadRequest("Geçersiz ImagePageId formatı.");

            var imagePage = catalog.Pages.FirstOrDefault(p => p.Id == imagePageGuid);
            if (imagePage == null) 
                return NotFound("Teknik resim sayfası bulunamadı.");

            try
            {
                var defaultRect = new RectObj { X = 0, Y = 0, W = 100, H = 100 };
                var tableRect = request.TableRect ?? defaultRect;
                var imageRect = request.ImageRect ?? defaultRect;

                string pdfFileName = Path. GetFileName(catalog.PdfUrl);

                _logger.LogInformation("🐼 PaddleOCR Multi-Page Analizi Başlıyor");
                _logger.LogInformation("   📋 Tablo Sayfası: {TablePage}", tablePage.PageNumber);
                _logger.LogInformation("   🎨 Teknik Resim Sayfası: {ImagePage}", imagePage. PageNumber);

                var result = await _paddleService.AnalyzeCatalogPageAsync(
                    pdfFileName,
                    tablePage.PageNumber,
                    imagePage.PageNumber,
                    imagePage.ImageUrl,
                    id,
                    imagePage.Id,
                    tableRect,
                    imageRect
                );

                LogAnalysisResult(result.products);

                if (result.products.Any())
                {
                    _context.Products.AddRange(result. products);
                }

                if (result.hotspots.Any())
                {
                    _context.Hotspots.AddRange(result.hotspots);
                }

                await _context.SaveChangesAsync();

                return Ok(new
                {
                    message = "Çoklu Sayfa AI Analizi Başarılı!",
                    engine = "PaddleOCR",
                    tablePageNumber = tablePage.PageNumber,
                    imagePageNumber = imagePage.PageNumber,
                    productCount = result.products.Count,
                    hotspotCount = result.hotspots.Count
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "PaddleOCR Multi-Page Analiz Hatası");
                return StatusCode(500, $"AI Hatası: {ex.Message}");
            }
        }

        // 6. Kataloğu Yayınla
        [HttpPost("{id}/publish")]
        public async Task<IActionResult> Publish(Guid id)
        {
            var catalog = await _context.Catalogs. FindAsync(id);
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

            var pageIds = await _context.CatalogPages
                .Where(p => p.CatalogId == id)
                .Select(p => p.Id)
                .ToListAsync();
                
            var productIds = await _context.Products
                .Where(p => p.CatalogId == id)
                .Select(p => p.Id)
                .ToListAsync();

            if (pageIds.Any() || productIds.Any())
            {
                await _context. Hotspots
                    .Where(h => pageIds.Contains(h.PageId) || 
                           (h.ProductId != null && productIds.Contains(h.ProductId. Value)))
                    .ExecuteDeleteAsync();
            }

            if (pageIds.Any())
                await _context.CatalogPages. Where(p => pageIds.Contains(p.Id)).ExecuteDeleteAsync();
                
            if (productIds.Any())
                await _context.Products.Where(p => productIds.Contains(p.Id)).ExecuteDeleteAsync();

            _context.Catalogs.Remove(catalog);
            await _context.SaveChangesAsync();

            return NoContent();
        }

        // 8. Sayfa Ürünlerini ve Hotspot'larını Temizle
        [HttpDelete("{id}/pages/{pageId}/clear")]
        public async Task<IActionResult> ClearPageData(Guid id, Guid pageId)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var page = await _context.CatalogPages.FindAsync(pageId);
            if (page == null) return NotFound("Sayfa bulunamadı.");

            var deletedHotspots = await _context. Hotspots
                .Where(h => h.PageId == pageId)
                .ExecuteDeleteAsync();

            var deletedProducts = await _context. Products
                .Where(p => p.CatalogId == id && p.PageNumber == page.PageNumber. ToString())
                .ExecuteDeleteAsync();

            return Ok(new
            {
                message = "Sayfa verileri temizlendi",
                deletedProducts = deletedProducts,
                deletedHotspots = deletedHotspots
            });
        }

        // 9. PaddleOCR Servis Durumu
        [AllowAnonymous]
        [HttpGet("ai-status")]
        public async Task<IActionResult> GetAiStatus()
        {
            try
            {
                var isHealthy = await _paddleService.IsHealthyAsync();
                var info = await _paddleService.GetServiceInfoAsync();

                return Ok(new
                {
                    healthy = isHealthy,
                    service = "PaddleOCR",
                    url = "http://localhost:8000",
                    info = info
                });
            }
            catch (Exception ex)
            {
                return Ok(new
                {
                    healthy = false,
                    service = "PaddleOCR",
                    error = ex.Message
                });
            }
        }

        #region Private Methods

        private void LogAnalysisResult(List<Product> products)
        {
            var logData = products.Select(p => new
            {
                page_number = p.PageNumber,
                ref_no = p.RefNo,
                part_code = p.Code,
                part_name = p.Name,
                quantity = p.StockQuantity
            }).ToList();

            var jsonLog = JsonSerializer.Serialize(logData, new JsonSerializerOptions { WriteIndented = true });

            _logger.LogInformation("=== 🐼 PaddleOCR DATA (Saved to DB) ===");
            _logger.LogInformation(jsonLog);
        }

        #endregion
    }

    #region Request Models

    public class AnalyzeRequest
    {
        public required string PageId { get; set; }
        public RectObj? TableRect { get; set; }
        public RectObj? ImageRect { get; set; }
    }

    public class MultiPageAnalyzeRequest
    {
        public required string TablePageId { get; set; }
        public RectObj? TableRect { get; set; }
        public required string ImagePageId { get; set; }
        public RectObj? ImageRect { get; set; }
    }

    #endregion
}