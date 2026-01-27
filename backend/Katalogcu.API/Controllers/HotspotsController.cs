using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.API.Controllers
{
    // [Authorize] // Geliştirme aşamasında kapalı kalabilir, canlıda açılmalı
    [Route("api/[controller]")]
    [ApiController]
    public class HotspotsController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly IPartalogAiService _aiService;
        private readonly ILogger<HotspotsController> _logger;
        private readonly IWebHostEnvironment _env;

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

                // Dosya yolunu bul
                var filePath = GetPhysicalPath(page.ImageUrl);
                if (!System.IO.File.Exists(filePath))
                {
                    return BadRequest($"Görüntü dosyası sunucuda bulunamadı: {filePath}");
                }

                _logger.LogInformation("🔍 Sayfa {PageNumber} için YOLO ile hotspot tespiti başlıyor...", page.PageNumber);

                // Dosyayı Stream Olarak Aç
                using var stream = System.IO.File.OpenRead(filePath);
                var formFile = new FormFile(stream, 0, stream.Length, "file", Path.GetFileName(filePath))
                {
                    Headers = new HeaderDictionary(),
                    ContentType = "image/jpeg"
                };

                // AI Servisine Gönder (Artık LeftPercent, WidthPercent gibi değerler dönmeli)
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

                // ✨ İsteğe Bağlı: Bu sayfa için eski hotspotları temizle (Çakışmayı önlemek için)
                // var existingHotspots = _context.Hotspots.Where(h => h.PageId == pageId);
                // _context.Hotspots.RemoveRange(existingHotspots);

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
            catch (Exception ex)
            {
                _logger.LogError(ex, "Hotspot tespit hatası");
                return StatusCode(500, new { error = "Hotspot tespiti sırasında hata oluştu", details = ex.Message });
            }
        }

        // 2. Yeni Hotspot Ekle (Manuel & Frontend Uyumlu)
        [HttpPost]
        public async Task<IActionResult> Create([FromBody] Hotspot hotspot)
        {
            if (hotspot == null || hotspot.PageId == Guid.Empty)
            {
                return BadRequest("Geçersiz veri.");
            }

            // Sayfa kontrolü
            var page = await _context.CatalogPages.FindAsync(hotspot.PageId);
            if (page == null) return NotFound("Sayfa bulunamadı.");

            // ID ve Tarih ataması
            hotspot.Id = Guid.NewGuid();
            hotspot.CreatedDate = DateTime.UtcNow;
            
            // Label boşsa varsayılan ata
            if (string.IsNullOrEmpty(hotspot.Label))
            {
                hotspot.Label = "?";
            }

            // ✨ GÜVENLİK ÖNLEMİ: Frontend Width/Height göndermediyse varsayılan ata
            // Frontend'de %3 ve %2 göndermiştik ama garanti olsun.
            if (hotspot.Width <= 0) hotspot.Width = 3.0;  // %3
            if (hotspot.Height <= 0) hotspot.Height = 2.0; // %2

            _context.Hotspots.Add(hotspot);
            await _context.SaveChangesAsync();

            return Ok(hotspot);
        }

        // 3. Hotspot Sil
        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(Guid id)
        {
            var hotspot = await _context.Hotspots.FindAsync(id);
            if (hotspot == null) return NotFound(new { message = "Hotspot bulunamadı" });

            _context.Hotspots.Remove(hotspot);
            await _context.SaveChangesAsync();
            return NoContent(); // Başarılı silme (204 No Content)
        }

        // --- YARDIMCI METODLAR ---

        private string GetPhysicalPath(string url)
        {
            // URL'den sadece dosya adını al (örn: image123.jpg)
            var fileName = Path.GetFileName(url);
            
            // 1. Önce "uploads/pages" klasörüne bak (Standart yer)
            var pathPages = Path.Combine(_env.WebRootPath, "uploads", "pages", fileName);
            if (System.IO.File.Exists(pathPages)) return pathPages;

            // 2. Yoksa "uploads" köküne bak (Alternatif)
            var pathRoot = Path.Combine(_env.WebRootPath, "uploads", fileName);
            if (System.IO.File.Exists(pathRoot)) return pathRoot;

            // Hiçbiri yoksa varsayılan pages yolunu dön (Hata fırlatması için)
            return pathPages; 
        }
    }
}