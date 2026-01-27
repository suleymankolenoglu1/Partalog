using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.API.Services;

namespace Katalogcu.API.Controllers
{
    [Authorize] // Varsayılan: Sadece giriş yapanlar
    [Route("api/[controller]")]
    [ApiController]
    public class ProductsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly ExcelService _excelService;

        public ProductsController(AppDbContext context, ExcelService excelService)
        {
            _context = context;
            _excelService = excelService;
        }

        // 1. TÜM ÜRÜNLERİ GETİR (Admin Paneli - Envanter Listesi İçin)
        // 🔥 GÜNCELLENDİ: Katalog ismini de (Join) getiriyor.
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            var products = await _context.Products
                .Include(p => p.Catalog) // Katalog tablosunu bağla
                .OrderByDescending(p => p.CreatedDate)
                .Select(p => new 
                {
                    p.Id,
                    p.Code,
                    p.Name,
                    p.OemNo,          // Yeni UI için lazım
                    p.Price,
                    p.StockQuantity,
                    p.ImageUrl,
                    p.Category,       // "Fren", "Motor" vb.
                    
                    // Frontend'de "Bağlı Olduğu Katalog" sütunu için:
                    CatalogName = p.Catalog != null ? p.Catalog.Name : "Genel Stok",
                    CatalogId = p.CatalogId
                })
                .ToListAsync();

            return Ok(products);
        }

        // 2. KATALOĞA GÖRE ÜRÜNLERİ GETİR (Vitrin / PublicView İçin)
        [AllowAnonymous] // Müşteriler görebilsin
        [HttpGet("catalog/{catalogId}")]
        public async Task<IActionResult> GetByCatalog(Guid catalogId)
        {
            var products = await _context.Products
                                         .Where(p => p.CatalogId == catalogId)
                                         .OrderBy(p => p.Code) // Kod sırasına göre gelsin
                                         .ToListAsync();
            return Ok(products);
        }

        // 3. YENİ ÜRÜN EKLE
        [HttpPost]
        public async Task<IActionResult> Create(Product product)
        {
            // Eğer kategori boşsa varsayılan ata
            if (string.IsNullOrEmpty(product.Category)) product.Category = "Genel";

            product.CreatedDate = DateTime.UtcNow;
            _context.Products.Add(product);
            await _context.SaveChangesAsync();
            return Ok(product);
        }
        
        // 4. ÜRÜN SİL
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var product = await _context.Products.FindAsync(id);
            if (product == null) return NotFound("Ürün bulunamadı.");

            // İlişkili Hotspot'ları (resim üzerindeki noktalar) temizle
            var linkedHotspots = await _context.Hotspots.Where(h => h.ProductId == id).ToListAsync();
            if (linkedHotspots.Any())
            {
                _context.Hotspots.RemoveRange(linkedHotspots);
            }

            _context.Products.Remove(product);
            await _context.SaveChangesAsync();
            return NoContent();
        }

        // 5. EXCEL İLE TOPLU YÜKLEME
        [HttpPost("import")]
        public async Task<IActionResult> Import([FromForm] IFormFile file, [FromForm] Guid? catalogId)
        {
            if (file == null || file.Length == 0)
                return BadRequest("Lütfen bir Excel dosyası yükleyin.");

            try 
            {
                // catalogId null gelebilir (Genel stok yüklemesi için)
                var targetCatalogId = catalogId ?? Guid.Empty; 

                // Excel servisinin Guid? desteklediğinden emin olalım, değilse servisi güncellemek gerekebilir
                // Şimdilik varsayım: ParseProducts(file, Guid catalogId) şeklinde.
                var products = _excelService.ParseProducts(file, targetCatalogId);

                if (products.Count == 0)
                    return BadRequest("Dosyada okunabilir ürün bulunamadı.");

                _context.Products.AddRange(products);
                await _context.SaveChangesAsync();

                return Ok(new { message = $"{products.Count} adet ürün başarıyla yüklendi!", count = products.Count });
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"Yükleme hatası: {ex.Message}");
            }
        }
    }
}