

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
        
        // İlişkiler
        public Guid UserId { get; set; } // Kataloğu kim yükledi?
        public AppUser? User { get; set; }
        
        public ICollection<CatalogPage> Pages { get; set; } = new List<CatalogPage>();
        public ICollection<Product> Products { get; set; } = new List<Product>();
    }
}