

using Katalogcu.Domain.Entities;

namespace Katalogcu.API.Services
{
    public class MockAiService
    {
        private readonly Random _random = new Random();

        // Rastgele parça üretici
        public List<Product> GenerateFakeParts(Guid catalogId)
        {
            var parts = new List<Product>();
            
            // Havuzdan rastgele seçmek için veriler
            var partNames = new[] { 
                "Ön Fren Balatası", "Yağ Filtresi", "Hava Filtresi", "Buji Takımı", 
                "Arka Amortisör", "Debriyaj Seti", "Triger Kayışı", "Su Pompası", 
                "Alternatör", "Marş Motoru", "Silecek Süpürgesi", "Polen Filtresi" 
            };
            
            var categories = new[] { 
                "Fren Sistemi", "Filtreler", "Motor", "Ateşleme", 
                "Süspansiyon", "Şanzıman", "Soğutma", "Elektrik" 
            };

            // Her katalog için 8-12 arası rastgele parça üretelim
            int count = _random.Next(8, 12);

            for (int i = 0; i < count; i++)
            {
                var nameIndex = _random.Next(partNames.Length);
                
                parts.Add(new Product
                {
                    Id = Guid.NewGuid(),
                    CatalogId = catalogId,
                    Name = partNames[nameIndex],
                    // Rastgele OEM Kodu: AB-12345
                    Code = $"OEM-{_random.Next(10000, 99999)}", 
                    Category = categories[_random.Next(categories.Length)],
                    // Rastgele Fiyat: 100 ile 5000 arası
                    Price = _random.Next(10, 500) * 10, 
                    // Rastgele Stok: 0 ile 100 arası
                    StockQuantity = _random.Next(0, 100), 
                    Description = "Yapay zeka tarafından otomatik tespit edildi (AI Scan).",
                    CreatedDate = DateTime.UtcNow
                });
            }

            return parts;
        }
    }
}