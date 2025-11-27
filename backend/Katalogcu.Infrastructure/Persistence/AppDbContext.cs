using Katalogcu.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.Infrastructure.Persistence
{
    public class AppDbContext: DbContext
    {
        public AppDbContext(DbContextOptions<AppDbContext> options) : base(options)
        {
            
        }
        public DbSet<AppUser> Users {get;set;}
        public DbSet<Catalog> Catalogs { get; set; }
        public DbSet<Product> Products { get; set; }
        public DbSet<CatalogPage> CatalogPages { get; set; }
        public DbSet<Hotspot> Hotspots { get; set; }
        
        
        
    }
}