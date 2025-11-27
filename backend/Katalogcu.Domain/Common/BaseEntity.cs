using System;

namespace Katalogcu.Domain.Common
{
    public abstract class BaseEntity
    {
        public Guid Id { get; set; } = Guid.NewGuid();
        
        // 👇 Düzeltme 1: İsmi 'CreateDate' yerine 'CreatedDate' yaptık (Standart)
        public DateTime CreatedDate { get; set; } = DateTime.UtcNow;
        
        // 👇 Düzeltme 2: Soru işareti (?) ekledik. Güncelleme tarihi başta boş olabilir.
        public DateTime? UpdatedDate { get; set; } 
    }
}