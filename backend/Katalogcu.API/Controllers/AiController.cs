using Katalogcu.API.Services;
using Katalogcu.Domain.Entities;
using Microsoft.AspNetCore.Mvc;
using Newtonsoft.Json; // JSON Dönüşümü için gerekli

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class AiController : ControllerBase
    {
        private readonly IPartalogAiService _aiService;
        private readonly ILogger<AiController> _logger;

        public AiController(IPartalogAiService aiService, ILogger<AiController> logger)
        {
            _aiService = aiService;
            _logger = logger;
        }

        // 1. Hotspot Tespiti (YOLO) 
        [HttpPost("detect-hotspots")]
        public async Task<IActionResult> DetectHotspots(IFormFile file, [FromQuery] Guid pageId)
        {
            if (file == null) return BadRequest("Dosya yüklenmedi.");
            var result = await _aiService.DetectHotspotsAsync(file, pageId);
            return Ok(result);
        }

        // 2. Tablo Okuma (Gemini) 
        [HttpPost("extract-table")]
        public async Task<IActionResult> ExtractTable(IFormFile file, [FromQuery] int pageNumber)
        {
            if (file == null) return BadRequest("Dosya yüklenmedi.");
            
            using var memoryStream = new MemoryStream();
            await file.CopyToAsync(memoryStream);
            var bytes = memoryStream.ToArray();

            var result = await _aiService.ExtractTableAsync(bytes, pageNumber);
            return Ok(result);
        }

        // 3. Sayfa Analizi (Başlık ve Tür)
        [HttpPost("analyze-page")]
        public async Task<IActionResult> AnalyzePage(IFormFile file)
        {
            if (file == null) return BadRequest("Dosya yüklenmedi.");

            using var memoryStream = new MemoryStream();
            await file.CopyToAsync(memoryStream);
            var bytes = memoryStream.ToArray();

            var result = await _aiService.AnalyzePageAsync(bytes);
            return Ok(result);
        }

        // 4. Expert Chat (Basit Proxy)
        // DÜZELTME: Parametre olarak ChatController'da tanımladığımız 'AiChatRequestWithHistoryDto'yu kullanıyoruz.
        // Bu sayede formdan gelen string History'yi alıp servisin istediği List formatına çevirebiliriz.
        [HttpPost("expert-chat")]
        public async Task<IActionResult> ExpertChat([FromForm] AiChatRequestWithHistoryDto request)
        {
            // 1. String History -> List<ChatMessageDto> Dönüşümü
            List<ChatMessageDto> chatHistory = new();
            if (!string.IsNullOrEmpty(request.History))
            {
                try {
                    chatHistory = JsonConvert.DeserializeObject<List<ChatMessageDto>>(request.History) ?? new();
                } catch { _logger.LogWarning("History parse edilemedi"); }
            }

            // 2. Service DTO'suna Mapleme (Hatanın asıl çözümü burası)
            // Katalogcu.API.Services.AiChatRequestDto türünde yeni bir nesne oluşturuyoruz.
            var serviceRequest = new Katalogcu.API.Services.AiChatRequestDto
            {
                Text = request.Text,
                Image = request.Image,
                History = chatHistory
            };

            var result = await _aiService.GetExpertChatResponseAsync(serviceRequest);
            return Ok(result);
        }
    }
}