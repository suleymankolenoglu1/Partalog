// Domain/Entities/Folder.cs
using System.ComponentModel.DataAnnotations;

namespace Katalogcu.Domain.Entities
{
    public class Folder
    {
        [Key]
        public Guid Id { get; set; }
        public string Name { get; set; } = string.Empty;
        public Guid UserId { get; set; } // Klasör kime ait?
        public DateTime CreatedDate { get; set; } = DateTime.UtcNow;
        public ICollection<Catalog> Catalogs { get; set; }
    }
}