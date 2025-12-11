

using Katalogcu.Domain.Entities;
using NPOI.SS.UserModel;
using NPOI.XSSF.UserModel; // .xlsx formatı için

namespace Katalogcu.API.Services
{
    public class ExcelService
    {
        public List<Product> ParseProducts(IFormFile file, Guid catalogId)
        {
            var products = new List<Product>();

            // Dosya akışını aç
            using (var stream = file.OpenReadStream())
            {
                stream.Position = 0;
                
                // Excel dosyasını oluştur
                ISheet sheet;
                var xssWorkbook = new XSSFWorkbook(stream); 
                sheet = xssWorkbook.GetSheetAt(0); // İlk sayfayı oku

                // Satırları dön (İlk satır başlık olduğu için 1'den başlıyoruz)
                for (int i = (sheet.FirstRowNum + 1); i <= sheet.LastRowNum; i++)
                {
                    var row = sheet.GetRow(i);
                    if (row == null) continue;

                    // Hücreleri oku (Sıralama: Ad, Kod, Kategori, Fiyat, Stok, Açıklama)
                    // Not: Excel'deki sütun sırasını buna göre ayarlamalarını isteyeceğiz.
                    
                    try 
                    {
                        var product = new Product
                        {
                            Id = Guid.NewGuid(),
                            CatalogId = catalogId,
                            CreatedDate = DateTime.UtcNow,
                            
                            Name = GetCellValue(row, 0), // A Sütunu
                            Code = GetCellValue(row, 1), // B Sütunu
                            Category = GetCellValue(row, 2), // C Sütunu
                            
                            // Fiyat ve Stok sayısal olduğu için dönüşüm yapıyoruz
                            Price = decimal.TryParse(GetCellValue(row, 3), out var p) ? p : 0,
                            StockQuantity = int.TryParse(GetCellValue(row, 4), out var s) ? s : 0,
                            
                            Description = GetCellValue(row, 5) // F Sütunu
                        };

                        // Boş satırları atla
                        if(!string.IsNullOrEmpty(product.Name) && !string.IsNullOrEmpty(product.Code))
                        {
                            products.Add(product);
                        }
                    }
                    catch
                    {
                        // Hatalı satırı atla, logla (Basit tutuyoruz)
                        continue;
                    }
                }
            }

            return products;
        }

        // Hücre verisini string olarak alma yardımcısı
        private string GetCellValue(IRow row, int cellIndex)
        {
            var cell = row.GetCell(cellIndex);
            return cell?.ToString() ?? string.Empty;
        }
    }
}