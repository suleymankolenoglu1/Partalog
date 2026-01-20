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
    public class HotspotsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly IPartalogAiService _aiService; // ✅ YENİ AI SERVİSİ
        private readonly ILogger<HotspotsController> _logger;
        private readonly IWebHostEnvironment _env; // 📂 Dosya yolu bulucu

        public HotspotsController(
            AppDbContext context, 
            IPartalogAiService aiService, 
            ILogger<HotspotsController> logger,
            IWebHostEnvironment env)
        {
            _context = context;
            _aiService = aiService;
            _logger = logger;
            _env = env;
        }

        // 1. Otomatik Hotspot Tespiti (YOLO ile)
        [HttpPost("detect/{pageId}")]
        public async Task<IActionResult> DetectHotspots(Guid pageId)
        {
            try
            {
                // Sayfayı bul
                var page = await _context.CatalogPages.FindAsync(pageId);
                if (page == null)
                {
                    return NotFound(new { error = "Sayfa bulunamadı" });
                }

                if (string.IsNullOrEmpty(page.ImageUrl))
                {
                    return BadRequest(new { error = "Sayfanın görüntüsü yok" });
                }

                // 1. Dosya yolunu bul
                var filePath = GetPhysicalPath(page.ImageUrl);
                if (!System.IO.File.Exists(filePath))
                {
                    return BadRequest($"Görüntü dosyası sunucuda bulunamadı: {filePath}");
                }

                _logger.LogInformation("🔍 Sayfa {PageNumber} için YOLO ile hotspot tespiti başlıyor...", page.PageNumber);

                // 2. Dosyayı Stream Olarak Aç
                using var stream = System.IO.File.OpenRead(filePath);
                var formFile = new FormFile(stream, 0, stream.Length, "file", Path.GetFileName(filePath))
                {
                    Headers = new HeaderDictionary(),
                    ContentType = "image/jpeg"
                };

                // 3. AI Servisine Gönder
                var detectedHotspots = await _aiService.DetectHotspotsAsync(formFile, pageId);

                if (!detectedHotspots.Any())
                {
                    return Ok(new
                    {
                        message = "Hiç hotspot tespit edilemedi",
                        pageId = pageId,
                        detectedCount = 0,
                        hotspots = new List<Hotspot>()
                    });
                }

                // 4. Veritabanına kaydet
                // (İsteğe bağlı: Önce eski otomatik tespit edilenleri silebilirsin)
                _context.Hotspots.AddRange(detectedHotspots);
                await _context.SaveChangesAsync();

                _logger.LogInformation("✅ {Count} hotspot başarıyla kaydedildi", detectedHotspots.Count);

                return Ok(new
                {
                    message = $"{detectedHotspots.Count} hotspot tespit edildi ve kaydedildi",
                    pageId = pageId,
                    detectedCount = detectedHotspots.Count,
                    hotspots = detectedHotspots
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Hotspot tespit hatası");
                return StatusCode(500, new { error = "Hotspot tespiti sırasında hata oluştu", details = ex.Message });
            }
        }

        // 2. Yeni Hotspot Ekle (Manuel)
        [HttpPost]
        public async Task<IActionResult> Create(Hotspot hotspot)
        {
            // Sayfa kontrolü
            var page = await _context.CatalogPages.FindAsync(hotspot.PageId);
            if (page == null) return NotFound("Sayfa bulunamadı.");

            // Gerekli alanları doldur
            hotspot.Id = Guid.NewGuid();
            hotspot.CreatedDate = DateTime.UtcNow;
            
            // Eğer Label boş geldiyse varsayılan bir değer ata
            if (string.IsNullOrEmpty(hotspot.Label))
            {
                hotspot.Label = "?";
            }

            _context.Hotspots.Add(hotspot);
            await _context.SaveChangesAsync();

            return Ok(hotspot);
        }

        // 3. Hotspot Sil
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var hotspot = await _context.Hotspots.FindAsync(id);
            if (hotspot == null) return NotFound();

            _context.Hotspots.Remove(hotspot);
            await _context.SaveChangesAsync();
            return NoContent();
        }

        // --- YARDIMCI METODLAR ---

        private string GetPhysicalPath(string url)
        {
            var fileName = Path.GetFileName(url);
            
            // 1. Önce "uploads/pages" klasörüne bak
            var pathPages = Path.Combine(_env.WebRootPath, "uploads", "pages", fileName);
            if (System.IO.File.Exists(pathPages)) return pathPages;

            // 2. Yoksa "uploads" köküne bak
            var pathRoot = Path.Combine(_env.WebRootPath, "uploads", fileName);
            if (System.IO.File.Exists(pathRoot)) return pathRoot;

            return pathPages;
        }
    }
}