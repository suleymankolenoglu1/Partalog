using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class Catalog : BaseEntity
    {
        public string Name { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public string ImageUrl { get; set; } = string.Empty; // Kapak resmi
        public string PdfUrl { get; set; } = string.Empty;   // Azure'daki PDF yolu
        public string Status { get; set; } = "Processing";   // Processing, Published, Draft
        
        // --- İLİŞKİLER ---

        // 1. Kullanıcı İlişkisi
        public Guid UserId { get; set; } // Kataloğu kim yükledi?
        public AppUser? User { get; set; }
        
        // 2. Klasör İlişkisi
        public Guid? FolderId { get; set; }
        public Folder? Folder { get; set; }

        // 3. Sayfalar
        public ICollection<CatalogPage> Pages { get; set; } = new List<CatalogPage>();

        // 4. Bağlı Ürünler (Stoktaki gerçek ürünler)
        public ICollection<Product> Products { get; set; } = new List<Product>();

        // 5. 🔥 EKLENEN KISIM: Katalog Öğeleri (PDF'ten okunan ham satırlar)
        // ChatController'da arama yaparken kullandığımız 'CatalogItem' tablosunun buradaki karşılığı.
        public ICollection<CatalogItem> Items { get; set; } = new List<CatalogItem>();
    }
}