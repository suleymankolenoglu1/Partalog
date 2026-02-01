using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization; // Yetki için
using System.Security.Claims; // User ID için

namespace Katalogcu.API.Controllers
{
    // 🔥 Varsayılan olarak her şey kilitli (Admin Paneli İçin)
    [Authorize] 
    [Route("api/[controller]")]
    [ApiController]
    public class OrdersController : ControllerBase
    {
        private readonly AppDbContext _context;

        public OrdersController(AppDbContext context)
        {
            _context = context;
        }

        // 🛠️ Helper: Token'dan Admin UserID'sini okur
        private Guid GetCurrentUserId()
        {
            var idString = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
            if (Guid.TryParse(idString, out var guid)) return guid;
            return Guid.Empty;
        }

        // ============================================================
        // 🟢 PUBLIC (HALKA AÇIK) ENDPOINTLER
        // ============================================================

        // 1. SİPARİŞ OLUŞTUR (Vitrinden gelir, Login gerektirmez)
        [AllowAnonymous] 
        [HttpPost]
        public async Task<IActionResult> CreateOrder([FromBody] CreateOrderRequest request)
        {
            // --- Validasyonlar ---
            if (request.Items == null || !request.Items.Any())
                return BadRequest("Sepet boş, sipariş oluşturulamaz.");

            if (string.IsNullOrEmpty(request.CustomerName) || string.IsNullOrEmpty(request.CustomerPhone))
                return BadRequest("Müşteri adı ve telefon numarası zorunludur.");

            // --- Sipariş Nesnesi ---
            var order = new Order
            {
                Id = Guid.NewGuid(),
                OrderNumber = $"SP-{DateTime.Now:yyyyMMdd}-{new Random().Next(1000, 9999)}",
                
                CustomerName = request.CustomerName,
                CustomerEmail = request.CustomerEmail,
                CustomerPhone = request.CustomerPhone,
                
                CreatedDate = DateTime.UtcNow,
                Status = OrderStatus.Pending, // Varsayılan: Bekliyor
                Items = new List<OrderItem>()
            };

            decimal calculatedTotalAmount = 0;

            // --- Kalemleri İşle ---
            foreach (var itemDto in request.Items)
            {
                // Fiyatı DB'den çek (Güvenlik)
                var product = await _context.Products.FindAsync(itemDto.ProductId);

                if (product == null) continue; // Ürün silinmişse atla

                var quantity = itemDto.Quantity > 0 ? itemDto.Quantity : 1;
                var lineTotal = product.Price * quantity;
                calculatedTotalAmount += lineTotal;

                order.Items.Add(new OrderItem
                {
                    Id = Guid.NewGuid(),
                    OrderId = order.Id,
                    ProductId = product.Id,
                    Quantity = quantity,
                    UnitPrice = product.Price 
                });
            }

            if (!order.Items.Any())
                return BadRequest("Sepetteki ürünlerin hiçbiri sistemde bulunamadı.");

            order.TotalAmount = calculatedTotalAmount;

            // --- Kaydet ---
            try
            {
                _context.Orders.Add(order);
                await _context.SaveChangesAsync();

                // 💡 İPUCU: İstersen burada sipariş veren kişiyi otomatik olarak "Customers" tablosuna da ekleyebilirsin.
                // Şimdilik sadece Order olarak tutuyoruz.

                return Ok(new 
                { 
                    message = "Sipariş başarıyla alındı.", 
                    orderId = order.Id, 
                    orderNumber = order.OrderNumber 
                });
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"Hata: {ex.Message}");
            }
        }

        // ============================================================
        // 🔒 ADMIN (YETKİLİ) ENDPOINTLER
        // ============================================================

        // 2. GELEN SİPARİŞLERİ LİSTELE (Sadece Benim Ürünlerim)
        [HttpGet]
        public async Task<IActionResult> GetIncomingOrders()
        {
            var userId = GetCurrentUserId();

            // 🔥 SORGUNUN MANTIĞI:
            // Bir siparişi, eğer içindeki ürünlerden EN AZ BİRİ benim kataloğuma aitse getir.
            var orders = await _context.Orders
                .Include(o => o.Items)
                .ThenInclude(i => i.Product)
                .ThenInclude(p => p.Catalog)
                .Where(o => o.Items.Any(i => i.Product.Catalog.UserId == userId)) // 🔒 İzolasyon
                .OrderByDescending(o => o.CreatedDate)
                .ToListAsync();

            return Ok(orders);
        }

        // 3. SİPARİŞ DETAYI
        [HttpGet("{id}")]
        public async Task<IActionResult> GetOrderDetails(Guid id)
        {
            var userId = GetCurrentUserId();

            var order = await _context.Orders
                .Include(o => o.Items)
                .ThenInclude(i => i.Product)
                .FirstOrDefaultAsync(o => o.Id == id);

            if (order == null) return NotFound();

            // Güvenlik: Bu siparişteki ürünlerin sahibi ben miyim?
            var belongsToMe = order.Items.Any(i => i.Product?.Catalog?.UserId == userId);
            
            if (!belongsToMe) return Unauthorized("Bu siparişi görüntüleme yetkiniz yok.");

            return Ok(order);
        }

        // 4. SİPARİŞ DURUMU GÜNCELLE
        [HttpPut("{id}/status")]
        public async Task<IActionResult> UpdateStatus(Guid id, [FromBody] UpdateStatusDto request)
        {
             var userId = GetCurrentUserId();
             
             var order = await _context.Orders
                 .Include(o => o.Items)
                 .ThenInclude(i => i.Product)
                 .ThenInclude(p => p.Catalog)
                 .FirstOrDefaultAsync(o => o.Id == id && o.Items.Any(i => i.Product.Catalog.UserId == userId));

             if (order == null) return NotFound("Sipariş bulunamadı veya yetkiniz yok.");

             // Status enum ise parse et, string ise direkt ata
             // Burada basitlik için OrderStatus enum kullandığını varsayıyorum
             order.Status = request.Status; 
             
             await _context.SaveChangesAsync();
             return Ok(order);
        }
    }

    // --- DTO'lar ---
    public class CreateOrderRequest
    {
        public string CustomerName { get; set; }
        public string CustomerEmail { get; set; }
        public string CustomerPhone { get; set; }
        public List<CartItemDto> Items { get; set; }
    }

    public class CartItemDto
    {
        public Guid ProductId { get; set; }
        public int Quantity { get; set; }
    }

    public class UpdateStatusDto 
    {
        public OrderStatus Status { get; set; }
    }
}