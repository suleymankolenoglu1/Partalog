using Docnet.Core;
using Docnet.Core.Models;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using SixLabors.ImageSharp.Processing;

namespace Katalogcu.API.Services
{
    public class PdfService
    {
        private readonly IWebHostEnvironment _env;

        public PdfService(IWebHostEnvironment env)
        {
            _env = env;
        }

        public async Task<List<string>> ConvertPdfToImages(string pdfFileName)
        {
            var imagePaths = new List<string>();
            
            // 1. Kök dizini garantiye al (Mac/Windows uyumlu)
            var webRoot = _env.WebRootPath ?? Path.Combine(Directory.GetCurrentDirectory(), "wwwroot");
            
            // 2. Dosya yollarını oluştur
            var pdfPath = Path.Combine(webRoot, "uploads", pdfFileName);
            var outputFolder = Path.Combine(webRoot, "uploads", "pages");

            // 3. Dosya var mı kontrol et
            if (!File.Exists(pdfPath))
            {
                throw new FileNotFoundException($"PDF dosyası sunucuda bulunamadı! Yol: {pdfPath}");
            }

            // 4. Çıktı klasörü yoksa oluştur
            if (!Directory.Exists(outputFolder))
                Directory.CreateDirectory(outputFolder);

            // 5. PDF İşleme (Kilitleme olmasın diye using bloğu)
            lock (DocLib.Instance) 
            {
                using (var docReader = DocLib.Instance.GetDocReader(pdfPath, new PageDimensions(2.0))) // Kalite: 2.0
                {
                    int pageCount = docReader.GetPageCount();

                    for (int i = 0; i < pageCount; i++)
                    {
                        using (var pageReader = docReader.GetPageReader(i))
                        {
                            var rawBytes = pageReader.GetImage();
                            var width = pageReader.GetPageWidth();
                            var height = pageReader.GetPageHeight();

                            if (rawBytes == null || rawBytes.Length == 0)
                                continue;

                            using (var image = Image.LoadPixelData<Bgra32>(rawBytes, width, height))
                            {
                                image.Mutate(x => x.BackgroundColor(Color.White));

                                var imageName = $"{Path.GetFileNameWithoutExtension(pdfFileName)}_page_{i + 1}.png";
                                var savePath = Path.Combine(outputFolder, imageName);

                                // Asenkron kaydet
                                image.SaveAsPng(savePath);

                                // URL formatına çevir (Ters slash sorununu çöz)
                                imagePaths.Add($"uploads/pages/{imageName}");
                            }
                        }
                    }
                }
            }

            return imagePaths;
        }
    }
}