using System;
using Katalogcu.Domain.Common;

namespace Katalogcu.Domain.Entities
{
    public class OrderItem : BaseEntity
    {
        public Guid OrderId { get; set; }
        public Order Order { get; set; } = null!;

        public Guid ProductId { get; set; }
        public Product Product { get; set; } = null!;

        public int Quantity { get; set; }
        
        // O anki fiyatı saklamak önemli (Ürün fiyatı değişse bile sipariş fiyatı değişmemeli)
        public decimal UnitPrice { get; set; } 
    }
}