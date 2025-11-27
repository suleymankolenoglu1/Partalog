using Microsoft.AspNetCore.Mvc;

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class FilesController : ControllerBase
    {
        private readonly IWebHostEnvironment _env;

        public FilesController(IWebHostEnvironment env)
        {
            _env = env;
        }

        [HttpPost("upload")]
        public async Task<IActionResult> Upload(IFormFile file)
        {
            if (file == null || file.Length == 0)
                return BadRequest("Lütfen bir dosya seçin.");

            // 1. Kök dizini garantiye al (PdfService ile AYNI mantık)
            var webRoot = _env.WebRootPath ?? Path.Combine(Directory.GetCurrentDirectory(), "wwwroot");
            
            // 2. Klasör yolu
            string uploadsFolder = Path.Combine(webRoot, "uploads");
            
            // 3. Klasör yoksa oluştur
            if (!Directory.Exists(uploadsFolder))
                Directory.CreateDirectory(uploadsFolder);

            // 4. Benzersiz isim oluştur
            string uniqueFileName = Guid.NewGuid().ToString() + "_" + file.FileName;
            string filePath = Path.Combine(uploadsFolder, uniqueFileName);

            // 5. Dosyayı Fiziksel Olarak Kaydet
            using (var fileStream = new FileStream(filePath, FileMode.Create))
            {
                await file.CopyToAsync(fileStream);
            }

            // 6. URL Oluştur
            var baseUrl = $"{Request.Scheme}://{Request.Host}/uploads/{uniqueFileName}";
            
            return Ok(new { url = baseUrl });
        }
    }
}