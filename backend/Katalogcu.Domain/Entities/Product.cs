using System.Text.Json.Serialization; // 👈 EKLE
using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class Product : BaseEntity
    {
        // ... Diğer alanlar aynı kalsın ...
        public string Name { get; set; } = string.Empty;
        public string Code { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public decimal Price { get; set; }
        public int StockQuantity { get; set; }
        public string Category { get; set; } = string.Empty;
        public string PageNumber {get;set;} = string.Empty;
        public int RefNo {get;set;} 
        
        public Guid CatalogId { get; set; }

        // 👇 BURAYA DA EKLE
        [JsonIgnore]
        public Catalog? Catalog { get; set; }
    }
}