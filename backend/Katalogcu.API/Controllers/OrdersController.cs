using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Katalogcu.Domain.Entities;
using Katalogcu.Infrastructure.Persistence;

namespace Katalogcu.API.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class OrdersController : ControllerBase
    {
        private readonly AppDbContext _context;

        public OrdersController(AppDbContext context)
        {
            _context = context;
        }

        // POST: api/orders
        [HttpPost]
        public async Task<IActionResult> CreateOrder([FromBody] CreateOrderRequest request)
        {
            // 1. Basit Validasyon
            if (request.Items == null || !request.Items.Any())
            {
                return BadRequest("Sepet boş, sipariş oluşturulamaz.");
            }

            if (string.IsNullOrEmpty(request.CustomerName) || string.IsNullOrEmpty(request.CustomerPhone))
            {
                return BadRequest("Müşteri adı ve telefon numarası zorunludur.");
            }

            // 2. Sipariş Nesnesini Oluştur
            var order = new Order
            {
                Id = Guid.NewGuid(),
                // Sipariş No Örn: SP-20240127-1234
                OrderNumber = $"SP-{DateTime.Now:yyyyMMdd}-{new Random().Next(1000, 9999)}",
                
                CustomerName = request.CustomerName,
                CustomerEmail = request.CustomerEmail,
                CustomerPhone = request.CustomerPhone,
                
                CreatedDate = DateTime.UtcNow,
                Status = OrderStatus.Pending,
                
                Items = new List<OrderItem>()
            };

            decimal calculatedTotalAmount = 0;

            // 3. Kalemleri Tek Tek İşle
            foreach (var itemDto in request.Items)
            {
                // GÜVENLİK: Fiyatı asla Frontend'den alma! Veritabanından çek.
                var product = await _context.Products.FindAsync(itemDto.ProductId);

                if (product == null)
                {
                    // Ürün bulunamadıysa (silinmiş olabilir), bu kalemi atla veya hata fırlat
                    continue; 
                }

                var quantity = itemDto.Quantity;
                if (quantity <= 0) quantity = 1;

                var lineTotal = product.Price * quantity; // Varsayalım Product.Price var
                calculatedTotalAmount += lineTotal;

                // Kalemi ekle
                order.Items.Add(new OrderItem
                {
                    Id = Guid.NewGuid(),
                    OrderId = order.Id,
                    ProductId = product.Id,
                    Quantity = quantity,
                    UnitPrice = product.Price // O anki fiyatı tarihe not düşüyoruz
                });
            }

            // Eğer geçerli ürün yoksa siparişi iptal et
            if (!order.Items.Any())
            {
                return BadRequest("Sepetteki ürünlerin hiçbiri sistemde bulunamadı.");
            }

            order.TotalAmount = calculatedTotalAmount;

            // 4. Veritabanına Kaydet
            try
            {
                _context.Orders.Add(order);
                await _context.SaveChangesAsync();

                // Başarılı yanıt dön
                return Ok(new 
                { 
                    message = "Sipariş başarıyla oluşturuldu.", 
                    orderId = order.Id,
                    orderNumber = order.OrderNumber 
                });
            }
            catch (Exception ex)
            {
                // Gerçek hayatta buraya loglama (Serilog vs.) eklenir
                return StatusCode(500, $"Sipariş kaydedilirken hata oluştu: {ex.Message}");
            }
        }
    }

    // --- DTO (Data Transfer Objects) ---
    // Frontend'den gelen JSON verisini karşılayan modeller
    // İstersen bunları ayrı bir klasöre (DTOs) taşıyabilirsin ama MVP için burada kalması pratik.

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
}