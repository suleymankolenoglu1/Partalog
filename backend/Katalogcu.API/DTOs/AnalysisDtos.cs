
namespace Katalogcu.API.Dtos
{
    // Eski RectObj sınıfını geri getirdik
    public class RectObj
    {
        public double X { get; set; }
        public double Y { get; set; }
        public double W { get; set; }
        public double H { get; set; }
    }

    // Frontend'den gelen analiz isteği
    public class AnalyzePageRequestDto
    {
        public Guid PageId { get; set; }
    }

    // Frontend'den gelen çoklu sayfa analiz isteği
    public class AnalyzeMultiPageRequestDto
    {
        public Guid TablePageId { get; set; }
        public RectObj? TableRect { get; set; }

        public Guid ImagePageId { get; set; }
        public RectObj? ImageRect { get; set; }
    }
}