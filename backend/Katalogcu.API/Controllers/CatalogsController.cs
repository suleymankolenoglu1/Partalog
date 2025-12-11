using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using System.Text.Json; // JSON loglama için gerekli

namespace Katalogcu.API.Controllers
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

        // 2. Tek Bir Katalog Getir (SIRALAMA GÜNCELLENDİ)
        [AllowAnonymous]
        [HttpGet("{id}")]
        public async Task<IActionResult> GetById(Guid id)
        {
            var catalog = await _context.Catalogs
                                        .Include(c => c.Pages.OrderBy(p => p.PageNumber))
                                        .ThenInclude(p => p.Hotspots)
                                        // --- KRİTİK GÜNCELLEME ---
                                        // Ürünleri çekerken sırasıyla:
                                        // 1. Sayfa Numarası (Önce 4. sayfa, sonra 5. sayfa...)
                                        // 2. Ref No (1, 2, 3...)
                                        // 3. Oluşturulma Tarihi (RefNo 0 ise okuma sırasına göre)
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
                    Console.WriteLine($"Hata: {ex.Message}");
                    catalog.Status = "Error";
                    await _context.SaveChangesAsync();
                }
            }

            return CreatedAtAction(nameof(GetById), new { id = catalog.Id }, catalog);
        }

        // 4. AI Analizi
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
                var tableRect = request.TableRect ?? defaultRect;
                var imageRect = request.ImageRect ?? defaultRect;

                string pdfFileName = Path.GetFileName(catalog.PdfUrl);

                var result = await _cloudService.AnalyzeCatalogPage(
                    pdfFileName,
                    page.PageNumber,
                    page.ImageUrl,
                    id,              
                    page.Id,         
                    tableRect,       
                    imageRect        
                );

                // --- LOGLAMA (Güncellendi) ---
                var logData = result.products.Select(p => new 
                {
                    page_number = p.PageNumber, // Artık nesnenin içinden geliyor
                    ref_no = p.RefNo,
                    part_code = p.Code,
                    part_name = p.Name,
                    quantity = p.StockQuantity
                }).ToList();

                var jsonLog = JsonSerializer.Serialize(logData, new JsonSerializerOptions { WriteIndented = true });
                
                Console.WriteLine("\n=== ☁️ CLOUD OCR RAW DATA (Saved to DB) ===");
                Console.WriteLine(jsonLog);
                Console.WriteLine("==========================================\n");
                // --------------------------------

                if (result.products.Any())
                {
                    _context.Products.AddRange(result.products);
                }

                if (result.hotspots.Any())
                {
                    _context.Hotspots.AddRange(result.hotspots);
                }
                
                await _context.SaveChangesAsync();
                
                return Ok(new { 
                    message = "AI Analizi Başarılı!", 
                    productCount = result.products.Count, 
                    hotspotCount = result.hotspots.Count 
                });
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"AI Hatası: {ex.Message}");
            }
        }

        // 5. Kataloğu Yayınla
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

        // 6. Katalog Sil
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
    }

    public class AnalyzeRequest
    {
        public required string PageId { get; set; }
        public Katalogcu.API.Services.RectObj? TableRect { get; set; } 
        public Katalogcu.API.Services.RectObj? ImageRect { get; set; }
    }
}