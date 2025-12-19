using Katalogcu.API. Services;
using Katalogcu.Domain. Entities;
using Katalogcu. Infrastructure. Persistence;
using Microsoft. AspNetCore.Authorization;
using Microsoft. AspNetCore. Mvc;
using Microsoft.EntityFrameworkCore;
using System.Text.Json;

namespace Katalogcu. API.Controllers
{
    [Authorize]
    [Route("api/[controller]")]
    [ApiController]
    public class CatalogsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly PdfService _pdfService;
        private readonly CloudOcrService _cloudService;

        public CatalogsController(AppDbContext context, PdfService pdfService, CloudOcrService cloudService)
        {
            _context = context;
            _pdfService = pdfService;
            _cloudService = cloudService;
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
                                        .Include(c => c.Pages. OrderBy(p => p. PageNumber))
                                        .ThenInclude(p => p. Hotspots)
                                        .Include(c => c. Products
                                            .OrderBy(pr => pr.PageNumber)
                                            .ThenBy(pr => pr. RefNo)
                                            . ThenBy(pr => pr.CreatedDate)
                                        )
                                        .FirstOrDefaultAsync(c => c. Id == id);

            if (catalog == null) return NotFound("Katalog bulunamadı.");
            return Ok(catalog);
        }

        // 3. Yeni Katalog Ekle
        [HttpPost]
        public async Task<IActionResult> Create(Catalog catalog)
        {
            catalog.CreatedDate = DateTime. UtcNow;
            catalog. Status = "Processing";

            _context. Catalogs.Add(catalog);
            await _context.SaveChangesAsync();

            if (! string.IsNullOrEmpty(catalog.PdfUrl))
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
                    _context. Catalogs.Update(catalog);
                    await _context.SaveChangesAsync();
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Hata: {ex. Message}");
                    catalog.Status = "Error";
                    await _context.SaveChangesAsync();
                }
            }

            return CreatedAtAction(nameof(GetById), new { id = catalog.Id }, catalog);
        }

        // 4. AI Analizi (Eski - Geriye Dönük Uyumluluk)
        [HttpPost("{id}/analyze")]
        public async Task<IActionResult> Analyze(Guid id, [FromBody] AnalyzeRequest request)
        {
            var catalog = await _context.Catalogs.FirstOrDefaultAsync(c => c.Id == id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");
            if (string.IsNullOrEmpty(catalog.PdfUrl)) return BadRequest("Kataloğun PDF dosyası yok.");

            var page = await _context.CatalogPages.FindAsync(Guid.Parse(request.PageId));
            if (page == null) return NotFound("Sayfa bulunamadı");

            try
            {
                var defaultRect = new RectObj { X = 0, Y = 0, W = 100, H = 100 };
                var tableRect = request. TableRect ?? defaultRect;
                var imageRect = request.ImageRect ?? defaultRect;

                string pdfFileName = Path.GetFileName(catalog.PdfUrl);

                // Eski metod - Tablo ve resim aynı sayfada
                var result = await _cloudService.AnalyzeCatalogPage(
                    pdfFileName,
                    page.PageNumber,
                    page.ImageUrl,
                    id,
                    page.Id,
                    tableRect,
                    imageRect
                );

                LogAnalysisResult(result. products);

                if (result.products.Any())
                {
                    _context.Products.AddRange(result.products);
                }

                if (result.hotspots. Any())
                {
                    _context.Hotspots.AddRange(result.hotspots);
                }

                await _context.SaveChangesAsync();

                return Ok(new
                {
                    message = "AI Analizi Başarılı!",
                    productCount = result.products.Count,
                    hotspotCount = result.hotspots. Count
                });
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"AI Hatası: {ex. Message}");
            }
        }

        // 5. AI Analizi (Yeni - Çoklu Sayfa Desteği)
        [HttpPost("{id}/analyze-multi")]
        public async Task<IActionResult> AnalyzeMultiPage(Guid id, [FromBody] MultiPageAnalyzeRequest request)
        {
            // Katalog kontrolü
            var catalog = await _context. Catalogs
                . Include(c => c.Pages)
                .FirstOrDefaultAsync(c => c.Id == id);
                
            if (catalog == null) 
                return NotFound("Katalog bulunamadı.");
            if (string.IsNullOrEmpty(catalog.PdfUrl)) 
                return BadRequest("Kataloğun PDF dosyası yok.");

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
                var imageRect = request.ImageRect ??  defaultRect;

                string pdfFileName = Path.GetFileName(catalog.PdfUrl);

                Console.WriteLine("\n" + new string('=', 80));
                Console.ForegroundColor = ConsoleColor. Cyan;
                Console.WriteLine("🚀 MULTI-PAGE ANALİZ BAŞLADI");
                Console.ResetColor();
                Console.WriteLine($"   📋 Tablo Sayfası: {tablePage. PageNumber} (ID: {tablePage. Id})");
                Console. WriteLine($"   🎨 Teknik Resim Sayfası: {imagePage.PageNumber} (ID: {imagePage.Id})");
                Console.WriteLine(new string('=', 80));

                // Yeni metod - Tablo ve resim farklı sayfalarda olabilir
                var result = await _cloudService.AnalyzeCatalogPage(
                    pdfFileName,
                    tablePage.PageNumber,      // Tablo sayfası numarası
                    imagePage.PageNumber,      // Teknik resim sayfası numarası
                    imagePage.ImageUrl,        // Teknik resim görüntüsü
                    id,                        // Katalog ID
                    imagePage.Id,              // Hotspot'lar teknik resim sayfasına bağlanacak
                    tableRect,
                    imageRect
                );

                LogAnalysisResult(result.products);

                // Ürünleri kaydet
                if (result.products. Any())
                {
                    _context.Products.AddRange(result.products);
                }

                // Hotspot'ları kaydet
                if (result.hotspots.Any())
                {
                    _context.Hotspots.AddRange(result.hotspots);
                }

                await _context.SaveChangesAsync();

                return Ok(new
                {
                    message = "Çoklu Sayfa AI Analizi Başarılı!",
                    tablePageNumber = tablePage.PageNumber,
                    imagePageNumber = imagePage.PageNumber,
                    productCount = result.products. Count,
                    hotspotCount = result.hotspots.Count
                });
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"❌ Multi-Page Analiz Hatası: {ex. Message}");
                Console.ResetColor();
                return StatusCode(500, $"AI Hatası: {ex.Message}");
            }
        }

        // 6. Kataloğu Yayınla
        [HttpPost("{id}/publish")]
        public async Task<IActionResult> Publish(Guid id)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound();

            catalog.Status = "Published";
            catalog.UpdatedDate = DateTime. UtcNow;

            await _context.SaveChangesAsync();

            return Ok(new { message = "Katalog yayına alındı", status = catalog.Status });
        }

        // 7. Katalog Sil
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var catalog = await _context.Catalogs. FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var pageIds = await _context.CatalogPages
                .Where(p => p.CatalogId == id)
                .Select(p => p.Id)
                .ToListAsync();
                
            var productIds = await _context. Products
                .Where(p => p. CatalogId == id)
                .Select(p => p.Id)
                .ToListAsync();

            if (pageIds.Any() || productIds.Any())
            {
                await _context. Hotspots
                    .Where(h => pageIds.Contains(h.PageId) || 
                           (h.ProductId != null && productIds.Contains(h.ProductId.Value)))
                    .ExecuteDeleteAsync();
            }

            if (pageIds.Any())
                await _context.CatalogPages.Where(p => pageIds.Contains(p.Id)).ExecuteDeleteAsync();
                
            if (productIds.Any())
                await _context. Products.Where(p => productIds.Contains(p.Id)).ExecuteDeleteAsync();

            _context. Catalogs.Remove(catalog);
            await _context.SaveChangesAsync();

            return NoContent();
        }

        // 8. Sayfa Ürünlerini ve Hotspot'larını Temizle
        [HttpDelete("{id}/pages/{pageId}/clear")]
        public async Task<IActionResult> ClearPageData(Guid id, Guid pageId)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound("Katalog bulunamadı.");

            var page = await _context. CatalogPages. FindAsync(pageId);
            if (page == null) return NotFound("Sayfa bulunamadı.");

            // Bu sayfadaki hotspot'ları sil
            var deletedHotspots = await _context. Hotspots
                .Where(h => h.PageId == pageId)
                .ExecuteDeleteAsync();

            // Bu sayfaya ait ürünleri sil (PageNumber'a göre)
            var deletedProducts = await _context.Products
                .Where(p => p.CatalogId == id && p.PageNumber == page.PageNumber. ToString())
                .ExecuteDeleteAsync();

            return Ok(new
            {
                message = "Sayfa verileri temizlendi",
                deletedProducts = deletedProducts,
                deletedHotspots = deletedHotspots
            });
        }

        #region Private Methods

        private void LogAnalysisResult(List<Product> products)
        {
            var logData = products.Select(p => new
            {
                page_number = p.PageNumber,
                ref_no = p. RefNo,
                part_code = p.Code,
                part_name = p.Name,
                quantity = p.StockQuantity
            }).ToList();

            var jsonLog = JsonSerializer. Serialize(logData, new JsonSerializerOptions { WriteIndented = true });

            Console.WriteLine("\n=== ☁️ CLOUD OCR RAW DATA (Saved to DB) ===");
            Console. WriteLine(jsonLog);
            Console.WriteLine("==========================================\n");
        }

        #endregion
    }

    #region Request Models

    /// <summary>
    /// Eski analiz isteği - Tablo ve resim aynı sayfada
    /// </summary>
    public class AnalyzeRequest
    {
        public required string PageId { get; set; }
        public RectObj?  TableRect { get; set; }
        public RectObj?  ImageRect { get; set; }
    }

    /// <summary>
    /// Yeni analiz isteği - Tablo ve resim farklı sayfalarda olabilir
    /// </summary>
    public class MultiPageAnalyzeRequest
    {
        /// <summary>
        /// Tablo sayfasının ID'si (parça listesi tablosunun bulunduğu sayfa)
        /// </summary>
        public required string TablePageId { get; set; }

        /// <summary>
        /// Tablo alanı koordinatları (yüzde olarak)
        /// </summary>
        public RectObj?  TableRect { get; set; }

        /// <summary>
        /// Teknik resim sayfasının ID'si (numaralı parça resminin bulunduğu sayfa)
        /// </summary>
        public required string ImagePageId { get; set; }

        /// <summary>
        /// Teknik resim alanı koordinatları (yüzde olarak)
        /// </summary>
        public RectObj? ImageRect { get; set; }
    }

    #endregion
}