using System.Text.Json.Serialization; // 👈 BU SATIRI EN ÜSTE EKLE
using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class CatalogPage : BaseEntity
    {
        public int PageNumber { get; set; }
        public string ImageUrl { get; set; } = string.Empty;
        
        public Guid CatalogId { get; set; }
        
        // 👇 BU SATIRA [JsonIgnore] EKLE
        // Bu sayede Swagger/API bizden "Katalog nerede?" diye sormayacak.
        [JsonIgnore] 
        public Catalog? Catalog { get; set; }
        
        public ICollection<Hotspot> Hotspots { get; set; } = new List<Hotspot>();
    }
}