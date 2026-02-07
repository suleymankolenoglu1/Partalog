using Katalogcu.Domain.Common;
using System.ComponentModel.DataAnnotations.Schema;
using Pgvector;
using System.Numerics;
namespace Katalogcu.Domain.Entities
{
    // 📚 KÜTÜPHANE TABLOSU
    public class CatalogItem : BaseEntity
    {
        // --- İLİŞKİLER (Navigation Properties) ---


        
        // Foreign Key
        public Guid CatalogId { get; set; }

        // 🔥 EKLENEN KISIM: ChatController'ın erişebilmesi için gerekli nesne referansı
        [ForeignKey("CatalogId")]
        public virtual Catalog Catalog { get; set; } = null!;

        // --- ÖZELLİKLER ---

        // Sayfa Numarası (Örn: "5", "10-11")
        public string PageNumber { get; set; } = string.Empty;

        // 🔥 GÜNCELLEME: ChatController'da 'RefNumber' olarak çağırdığımız için ismini düzelttik.
        // (Eski hali: RefNo -> Yeni hali: RefNumber)
        public string RefNumber { get; set; } = string.Empty;

        // Parça Kodu (Örn: "40057971")
        public string PartCode { get; set; } = string.Empty;

        // Parça Adı (Örn: "THROAT PLATE")
        public string PartName { get; set; } = string.Empty;

        // Ek Bilgiler
        public string Description { get; set; } = string.Empty;

        // Vektör Temsili (Embedding)
       
        [Column(TypeName = "vector(3072)")] 
        public Pgvector.Vector? Embedding { get; set; }

        public string? MachineModel { get; set; } 
        public string? MachineBrand { get; set; }

        public string? MachineGroup { get; set; }

        public string? Dimensions { get; set; }

        public string? Mechanism { get; set; }


        
        [NotMapped]
        public bool IsInStock { get; set; }
    }
}