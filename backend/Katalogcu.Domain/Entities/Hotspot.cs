using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class Hotspot : BaseEntity
    {
        // Koordinatlar (% olarak, örn: 50.5)
        public double X { get; set; } 
        public double Y { get; set; }
        public int Number { get; set; } // Yuvarlak içindeki numara (1, 2, 3)

        // Hangi sayfada?
        public Guid PageId { get; set; }
        public CatalogPage? Page { get; set; }

        // Hangi ürünü işaret ediyor?
        public Guid? ProductId { get; set; } 
        public Product? Product { get; set; }
    }
}