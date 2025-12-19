

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

        public HotspotsController(AppDbContext context)
        {
            _context = context;
        }

        // 1. Yeni Hotspot Ekle (POST)
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

        // 2. Hotspot Sil (DELETE)
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