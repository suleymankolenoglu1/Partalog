using System.Text.Json.Serialization; 
using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class Product : BaseEntity
    {
        public string Name { get; set; } = string.Empty;
        public string Code { get; set; } = string.Empty;
        
        // 🔥 YENİ EKLENEN ALANLAR (Hata veren kısımlar)
        public string? OemNo { get; set; }      // OEM Numarası (Boş olabilir)
        public string? ImageUrl { get; set; }   // Parça Resmi (Boş olabilir)

        public string Description { get; set; } = string.Empty;
        public decimal Price { get; set; }
        public int StockQuantity { get; set; }
        
        // Kategori boş gelirse varsayılan atama yapılabilir
        public string Category { get; set; } = string.Empty;
        
        public string PageNumber { get; set; } = string.Empty;
        public int RefNo { get; set; } 

        // İlişkiler
        public Guid CatalogId { get; set; }

        public Guid? PageId { get; set; }

        [JsonIgnore] // Döngüsel referans hatasını önler
        public Catalog? Catalog { get; set; }
    }
}