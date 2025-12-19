using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class Hotspot : BaseEntity
    {
        // --- 1. Konum ve Boyut (CSS Dostu & Responsive) ---
        // Veritabanında % olarak saklayacağız (0.0 ile 100.0 arası)
        
        public double Left { get; set; }   // X konumu (%)
        public double Top { get; set; }    // Y konumu (%)
        public double Width { get; set; }  // Kutunun genişliği (%)
        public double Height { get; set; } // Kutunun yüksekliği (%)

        // --- 2. İçerik Bilgisi ---
        
        // YOLO bunu okuyamaz! (OCR gerekir veya elle girilir)
        public string? Label { get; set; } // "12", "12-B" olabilir diye string yaptım.
        
        // Bu kutu yapay zeka tarafından mı bulundu, insan mı ekledi?
        public bool IsAiDetected { get; set; } = true; 
        
        // AI ne kadar emindi? (%98 eminse belki direkt onaylarız)
        public double AiConfidence { get; set; } 

        // --- 3. İlişkiler ---
        public Guid PageId { get; set; }
        public CatalogPage? Page { get; set; }

        public Guid? ProductId { get; set; } 
        public Product? Product { get; set; }
    }
}