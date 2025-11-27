using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.API.Controllers
{
    [Authorize]
    [Route("api/[controller]")]
    [ApiController]
    public class CatalogsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly PdfService _pdfService;
        private readonly MockAiService _mockAiService;

        public CatalogsController(AppDbContext context, PdfService pdfService, MockAiService mockAiService)
        {
            _context = context;
            _pdfService = pdfService;
            _mockAiService = mockAiService;
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
                                        .FirstOrDefaultAsync(c => c.Id == id);

            if (catalog == null) return NotFound("Katalog bulunamadı.");
            return Ok(catalog);
        }

        // 3. Yeni Katalog Ekle (PDF İşleme ve Mock AI Dahil)
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
                    // A) PDF -> Resim
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

                    // B) Mock AI: Sahte Parça Üretimi
                    var fakeParts = _mockAiService.GenerateFakeParts(catalog.Id);
                    _context.Products.AddRange(fakeParts);

                    // Durum Güncelle
                    catalog.Status = "Draft"; // Önce taslak olsun, kullanıcı yayınlasın
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

        // 👇 EKSİK OLAN METOD BU (YENİDEN EKLENDİ) 👇
        // 4. Kataloğu Yayınla (POST: api/catalogs/{id}/publish)
        [HttpPost("{id}/publish")]
        public async Task<IActionResult> Publish(Guid id)
        {
            var catalog = await _context.Catalogs.FindAsync(id);
            if (catalog == null) return NotFound();

            // Durumu güncelle
            catalog.Status = "Published";
            catalog.UpdatedDate = DateTime.UtcNow;

            await _context.SaveChangesAsync();
            
            return Ok(new { message = "Katalog yayına alındı", status = catalog.Status });
        }
        // 👆 -------------------------------------- 👆

        // 5. Katalog Sil (Gelişmiş Silme)
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
}