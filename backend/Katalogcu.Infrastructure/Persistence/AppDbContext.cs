using Katalogcu.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace Katalogcu.Infrastructure.Persistence
{
    public class AppDbContext : DbContext
    {
        public AppDbContext(DbContextOptions<AppDbContext> options) : base(options)
        {
        }

        // Mevcut Tablolar
        public DbSet<AppUser> Users { get; set; }
        public DbSet<Catalog> Catalogs { get; set; }
        public DbSet<Product> Products { get; set; }
        public DbSet<CatalogPage> CatalogPages { get; set; }
        public DbSet<Hotspot> Hotspots { get; set; }
        public DbSet<Order> Orders { get; set; }
        public DbSet<OrderItem> OrderItems { get; set; }
        public DbSet<CatalogItem> CatalogItems { get; set; }
        public DbSet<Folder> Folders { get; set; }

        // İlişki ve Davranış Ayarları
        protected override void OnModelCreating(ModelBuilder modelBuilder)
        {
            // 🔥 KRİTİK ADIM: PostgreSQL Vektör Eklentisini Aktif Et
            // Bu satır, veritabanına "vector" tipini tanıtır.
            modelBuilder.HasPostgresExtension("vector");

            base.OnModelCreating(modelBuilder);

            // 1. Sipariş (Order) ile Kalemleri (OrderItems) arasındaki ilişki
            modelBuilder.Entity<Order>()
                .HasMany(o => o.Items)
                .WithOne(i => i.Order)
                .HasForeignKey(i => i.OrderId)
                .OnDelete(DeleteBehavior.Cascade); 
                // ÖNEMLİ: Sipariş silinirse içindeki kalemler de silinsin.

            // 2. Sipariş Kalemi ile Ürün arasındaki ilişki
            modelBuilder.Entity<OrderItem>()
                .HasOne(i => i.Product)
                .WithMany()
                .HasForeignKey(i => i.ProductId)
                .OnDelete(DeleteBehavior.Restrict); 
                // GÜVENLİK: Eğer bir ürün satılmışsa, Products tablosundan silinemesin.
                
            // Fiyat alanları için hassasiyet ayarı
            modelBuilder.Entity<Order>()
                .Property(o => o.TotalAmount)
                .HasPrecision(18, 2);

            modelBuilder.Entity<OrderItem>()
                .Property(i => i.UnitPrice)
                .HasPrecision(18, 2);
        }
    }
}