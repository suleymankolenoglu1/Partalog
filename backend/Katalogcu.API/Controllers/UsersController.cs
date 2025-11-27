using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class UsersController : ControllerBase
    {
        private readonly AppDbContext _context;

        public UsersController(AppDbContext context)
        {
            _context = context;
        }

        // GET: api/users
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            var users = await _context.Users.ToListAsync();
            return Ok(users);
        }

        // GET: api/users/{id}  <-- EKSİK OLAN METOD BUYDU
        [HttpGet("{id}")]
        public async Task<IActionResult> GetById(Guid id)
        {
            var user = await _context.Users.FindAsync(id);
            if (user == null) return NotFound();
            return Ok(user);
        }

        // POST: api/users
        [HttpPost]
        public async Task<IActionResult> Create(AppUser user)
        {
            user.CreatedDate = DateTime.UtcNow;
            
            _context.Users.Add(user);
            await _context.SaveChangesAsync();

            // Düzeltme: Artık 'GetById' metoduna yönlendiriyoruz
            return CreatedAtAction(nameof(GetById), new { id = user.Id }, user);
        }
    }
}