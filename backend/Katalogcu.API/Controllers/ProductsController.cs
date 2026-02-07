using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.API.Services;
using System.Security.Claims; // ✨ User ID okumak için

namespace Katalogcu.API.Controllers
{
    [Authorize] // 🔒 Sadece giriş yapanlar
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

        // 🛠️ Yardımcı Metod: Token'dan UserID'yi (Guid) okur
        private Guid GetCurrentUserId()
        {
            var idString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (Guid.TryParse(idString, out var guid)) return guid;
            return Guid.Empty;
        }

        private Guid ResolveUserId(Guid? userId)
        {
            var tokenUserId = GetCurrentUserId();
            if (tokenUserId != Guid.Empty) return tokenUserId;
            if (userId.HasValue && userId.Value != Guid.Empty) return userId.Value;
            return Guid.Empty;
        }

        // 1. TÜM ÜRÜNLERİ GETİR (SADECE BENİM OLANLAR)
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            var userId = GetCurrentUserId();

            // 🔥 DÜZELTME: Sadece giriş yapan kullanıcının kataloglarına bağlı ürünleri getir.
            var products = await _context.Products
                .Include(p => p.Catalog)
                .Where(p => p.Catalog.UserId == userId) // 🔒 Veri İzolasyonu
                .OrderByDescending(p => p.CreatedDate)
                .Select(p => new 
                {
                    p.Id,
                    p.Code,
                    p.Name,
                    p.OemNo,
                    p.Price,
                    p.StockQuantity,
                    p.ImageUrl,
                    p.Category,
                    CatalogName = p.Catalog != null ? p.Catalog.Name : "Genel Stok",
                    CatalogId = p.CatalogId
                })
                .ToListAsync();

            return Ok(products);
        }

        // 2. KATALOĞA GÖRE GETİR (Vitrin için açık bırakıldı)
        [AllowAnonymous]
        [HttpGet("catalog/{catalogId}")]
        public async Task<IActionResult> GetByCatalog(Guid catalogId, [FromQuery] Guid? userId)
        {
            var resolvedUserId = ResolveUserId(userId);
            if (resolvedUserId == Guid.Empty) return BadRequest("Kullanıcı bilgisi bulunamadı.");

            var products = await _context.Products
                                         .Include(p => p.Catalog)
                                         .Where(p => p.CatalogId == catalogId && p.Catalog.UserId == resolvedUserId)
                                         .OrderBy(p => p.Code)
                                         .ToListAsync();
            return Ok(products);
        }

        // 3. YENİ ÜRÜN EKLE
        [HttpPost]
        public async Task<IActionResult> Create(Product product)
        {
            var userId = GetCurrentUserId();

            // Güvenlik Kontrolü: Eklenmek istenen katalog bu kullanıcıya mı ait?
            if (product.CatalogId != null && product.CatalogId != Guid.Empty)
            {
                var ownsCatalog = await _context.Catalogs.AnyAsync(c => c.Id == product.CatalogId && c.UserId == userId);
                if (!ownsCatalog) return BadRequest("Seçilen katalog size ait değil veya bulunamadı.");
            }

            if (string.IsNullOrEmpty(product.Category)) product.Category = "Genel";

            product.CreatedDate = DateTime.UtcNow;
            _context.Products.Add(product);
            await _context.SaveChangesAsync();
            return Ok(product);
        }
        
        // 4. ÜRÜN SİL (GÜÇLENDİRİLMİŞ)
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var userId = GetCurrentUserId();

            // Ürünü ve Kataloğunu bul
            var product = await _context.Products
                .Include(p => p.Catalog)
                .FirstOrDefaultAsync(p => p.Id == id);

            if (product == null) return NotFound("Ürün bulunamadı.");

            // 🔒 YETKİ KONTROLÜ: Ürün bir kataloğa bağlıysa, o katalog benim mi?
            if (product.Catalog != null && product.Catalog.UserId != userId)
            {
                return Unauthorized("Bu ürünü silme yetkiniz yok.");
            }

            try 
            {
                // A. Hotspotları Temizle
                var linkedHotspots = await _context.Hotspots.Where(h => h.ProductId == id).ToListAsync();
                if (linkedHotspots.Any())
                {
                    _context.Hotspots.RemoveRange(linkedHotspots);
                }

                // B. 🔥 SİPARİŞ KALEMLERİNİ TEMİZLE (FK Hatasını Önler)
                var orderItems = await _context.OrderItems.Where(oi => oi.ProductId == id).ToListAsync();
                if (orderItems.Any())
                {
                    _context.OrderItems.RemoveRange(orderItems);
                }

                // C. Ürünü Sil
                _context.Products.Remove(product);
                await _context.SaveChangesAsync();
                return NoContent();
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"Silme hatası: {ex.Message}");
            }
        }

        // 5. EXCEL İLE TOPLU YÜKLEME
        [HttpPost("import")]
        public async Task<IActionResult> Import(IFormFile file, [FromForm] Guid? catalogId)
        {
            var userId = GetCurrentUserId();

            if (file == null || file.Length == 0)
                return BadRequest("Lütfen bir Excel dosyası yükleyin.");

            // 🔒 Güvenlik: Eğer bir kataloğa yükleme yapılıyorsa, katalog kullanıcının mı?
            if (catalogId.HasValue && catalogId != Guid.Empty)
            {
                var ownsCatalog = await _context.Catalogs.AnyAsync(c => c.Id == catalogId && c.UserId == userId);
                if (!ownsCatalog) return BadRequest("Seçilen katalog size ait değil.");
            }

            try 
            {
                var targetCatalogId = catalogId ?? Guid.Empty; 

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