using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using System.Security.Claims;

namespace Katalogcu.API.Controllers
{
    [Authorize] // 🔒 Sadece giriş yapmış kullanıcılar erişebilir
    [Route("api/[controller]")]
    [ApiController]
    public class FoldersController : ControllerBase
    {
        private readonly AppDbContext _context;
        private readonly ILogger<FoldersController> _logger;

        public FoldersController(AppDbContext context, ILogger<FoldersController> logger)
        {
            _context = context;
            _logger = logger;
        }

        // Kullanıcı ID'sini token'dan alma yardımcısı
        private Guid GetCurrentUserId()
        {
            var idString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (Guid.TryParse(idString, out var guid))
            {
                return guid;
            }
            return Guid.Empty;
        }

        // ==========================================
        // 1. SORUN ÇÖZÜMÜ: SADECE KENDİ KLASÖRLERİNİ GÖR
        // ==========================================
        [HttpGet]
        public async Task<IActionResult> GetMyFolders()
        {
            var userId = GetCurrentUserId();

            var folders = await _context.Folders
                .Where(f => f.UserId == userId) // 👈 İŞTE BU SATIR EKSİKTİ!
                .OrderByDescending(f => f.CreatedDate)
                .Select(f => new 
                {
                    f.Id,
                    f.Name,
                    // Klasörün içindeki katalog sayısını da dönelim (Opsiyonel)
                    CatalogCount = _context.Catalogs.Count(c => c.FolderId == f.Id)
                })
                .ToListAsync();

            return Ok(folders);
        }

        // Klasör Oluşturma
        [HttpPost]
        public async Task<IActionResult> CreateFolder([FromBody] CreateFolderDto request)
        {
            var userId = GetCurrentUserId();

            // Aynı isimde klasör var mı kontrolü (Kendi klasörleri içinde)
            var exists = await _context.Folders
                .AnyAsync(f => f.UserId == userId && f.Name == request.Name);

            if (exists)
                return BadRequest("Bu isimde bir klasörünüz zaten var.");

            var folder = new Folder
            {
                Id = Guid.NewGuid(),
                Name = request.Name,
                UserId = userId,
                CreatedDate = DateTime.UtcNow
            };

            _context.Folders.Add(folder);
            await _context.SaveChangesAsync();

            return Ok(folder);
        }

        // ==========================================
        // 2. İSTEK: KLASÖR SİLME ÖZELLİĞİ
        // ==========================================
        [HttpDelete("{id}")]
        public async Task<IActionResult> DeleteFolder(Guid id)
        {
            var userId = GetCurrentUserId();

            // 1. Klasörü bul (Sadece bu kullanıcıya aitse!)
            var folder = await _context.Folders
                .FirstOrDefaultAsync(f => f.Id == id && f.UserId == userId);

            if (folder == null)
                return NotFound("Klasör bulunamadı veya silme yetkiniz yok.");

            try
            {
                // 2. Senaryo A: Klasörün içindeki katalogları ne yapacağız?
                // Seçenek 1: Klasör silinince içindeki katalogların FolderId'sini null yap (Ana dizine düşer)
                var catalogsInFolder = await _context.Catalogs.Where(c => c.FolderId == id).ToListAsync();
                foreach (var catalog in catalogsInFolder)
                {
                    catalog.FolderId = null; // Katalog silinmez, klasörden çıkar.
                }

                // Seçenek 2: Eğer klasörle birlikte içindekileri de silmek istersen:
                // _context.Catalogs.RemoveRange(catalogsInFolder); (DİKKATLİ KULLAN)

                // 3. Klasörü Sil
                _context.Folders.Remove(folder);
                await _context.SaveChangesAsync();

                return Ok(new { message = "Klasör başarıyla silindi." });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Klasör silme hatası");
                return StatusCode(500, "Klasör silinirken hata oluştu.");
            }
        }
    }

    // Basit DTO
    public class CreateFolderDto
    {
        public string Name { get; set; }
    }
}