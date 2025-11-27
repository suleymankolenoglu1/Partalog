

using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class ProductsController : ControllerBase
    {
        private readonly AppDbContext _context;

        public ProductsController(AppDbContext context)
        {
            _context = context;
        }

        // GET: api/products
        [AllowAnonymous]
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            return Ok(await _context.Products.ToListAsync());
        }

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

            _context.Products.Remove(product);
            await _context.SaveChangesAsync();
            return NoContent();
        }
    }
}