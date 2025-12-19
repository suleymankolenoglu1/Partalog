

using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.API.Controllers
{
    [Authorize] // Sadece giriş yapanlar
    [Route("api/[controller]")]
    [ApiController]
    public class HotspotsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly Services.YoloService _yoloService;
        private readonly ILogger<HotspotsController> _logger;

        public HotspotsController(AppDbContext context, Services.YoloService yoloService, ILogger<HotspotsController> logger)
        {
            _context = context;
            _yoloService = yoloService;
            _logger = logger;
        }

        // 1. Otomatik Hotspot Tespiti (YOLO ile)
        [HttpPost("detect/{pageId}")]
        public async Task<IActionResult> DetectHotspots(Guid pageId, [FromQuery] double minConfidence = 0.5)
        {
            // Input validation
            if (minConfidence < 0.0 || minConfidence > 1.0)
            {
                return BadRequest(new { error = "minConfidence parametresi 0.0 ile 1.0 arasında olmalıdır" });
            }

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

                // YOLO servis sağlığını kontrol et
                var isHealthy = await _yoloService.IsHealthyAsync();
                if (!isHealthy)
                {
                    return StatusCode(503, new { error = "YOLO servisi çalışmıyor veya model yüklenmemiş" });
                }

                _logger.LogInformation("🔍 Sayfa {PageId} için YOLO ile hotspot tespiti başlıyor", pageId);

                // YOLO ile hotspot'ları tespit et
                var detectedHotspots = await _yoloService.DetectHotspotsAsync(page.ImageUrl, pageId, minConfidence);

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

                // Veritabanına kaydet
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
            catch (HttpRequestException ex)
            {
                _logger.LogError(ex, "YOLO servisi ile iletişim hatası");
                return StatusCode(503, new { error = "YOLO servisi ile iletişim kurulamadı", details = ex.Message });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Hotspot tespit hatası");
                return StatusCode(500, new { error = "Hotspot tespiti sırasında hata oluştu", details = ex.Message });
            }
        }

        // 2. Yeni Hotspot Ekle (POST) - Manuel ekleme
        [HttpPost]
        public async Task<IActionResult> Create(Hotspot hotspot)
        {
            // Hangi sayfa?
            var page = await _context.CatalogPages
                                     .Include(p => p.Hotspots)
                                     .FirstOrDefaultAsync(p => p.Id == hotspot.PageId);
            
            if (page == null) return NotFound("Sayfa bulunamadı.");

            // Otomatik numara ver (Mevcutların en büyüğü + 1)
            //int nextNumber = page.Hotspots.Any() ? page.Hotspots.Max(h => h.Number.ToString) + 1 : 1;
            //hotspot.Number = nextNumber;
            hotspot.CreatedDate = DateTime.UtcNow;

            _context.Hotspots.Add(hotspot);
            await _context.SaveChangesAsync();

            return Ok(hotspot);
        }

        // 3. Hotspot Sil (DELETE)
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var hotspot = await _context.Hotspots.FindAsync(id);
            if (hotspot == null) return NotFound();

            _context.Hotspots.Remove(hotspot);
            await _context.SaveChangesAsync();
            return NoContent();
        }
    }
}