using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.API.Services;

namespace Katalogcu.API.Controllers
{
    // 👇 GÜVENLİK: Varsayılan olarak kilitli olsun (Sadece giriş yapanlar)
    [Authorize] 
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

        // GET: api/products
        [AllowAnonymous] // Herkes görebilir
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            return Ok(await _context.Products.ToListAsync());
        }

        // 👇 EKSİK OLAN METOD BU (LÜTFEN EKLE) 👇
        // GET: api/products/catalog/{catalogId}
        [AllowAnonymous] // Müşteri ekranında (PublicView) lazım olduğu için herkese açık
        [HttpGet("catalog/{catalogId}")]
        public async Task<IActionResult> GetByCatalog(Guid catalogId)
        {
            var products = await _context.Products
                                         .Where(p => p.CatalogId == catalogId)
                                         .ToListAsync();
            return Ok(products);
        }
        // -----------------------------------------

        // POST: api/products
        [HttpPost]
        public async Task<IActionResult> Create(Product product)
        {
            product.CreatedDate = DateTime.UtcNow;
            _context.Products.Add(product);
            await _context.SaveChangesAsync();
            return Ok(product);
        }
        
        // DELETE: api/products/{id}
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var product = await _context.Products.FindAsync(id);
            if (product == null) return NotFound();

            // Eğer bu ürüne bağlı Hotspotlar varsa hata verir, önce onları temizlemek gerekebilir.
            // Şimdilik basit silme yapıyoruz.
            _context.Products.Remove(product);
            await _context.SaveChangesAsync();
            return NoContent();
        }

        [HttpPost("import")]
        public async Task<IActionResult> Import([FromForm] IFormFile file, [FromForm] Guid catalogId)
        {
            if (file == null || file.Length == 0)
                return BadRequest("Lütfen bir Excel dosyası yükleyin.");

            try 
            {
                var products = _excelService.ParseProducts(file, catalogId);

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