using Google.Cloud.DocumentAI.V1;
using Google. Protobuf;
using Google.Apis.Auth.OAuth2;
using Grpc.Auth;
using Katalogcu.Domain. Entities;
using SixLabors.ImageSharp;
using SixLabors. ImageSharp.Processing;
using SixLabors.ImageSharp. Formats. Png;
using System.Text. RegularExpressions;
using System.Text;
using PdfSharpCore.Pdf;
using PdfSharpCore.Pdf. IO;

namespace Katalogcu.API. Services
{
    public class RectObj
    {
        public double X { get; set; }
        public double Y { get; set; }
        public double W { get; set; }
        public double H { get; set; }
    }

    public class CloudOcrService
    {
        private readonly string _projectId;
        private readonly string _location;
        private readonly string _processorId;
        private readonly IWebHostEnvironment _env;

        public CloudOcrService(IConfiguration configuration, IWebHostEnvironment env)
        {
            _projectId = configuration["GoogleCloudSettings:ProjectId"]!;
            _location = configuration["GoogleCloudSettings:Location"]!;
            _processorId = configuration["GoogleCloudSettings:ProcessorId"]!;
            _env = env;
        }

        public async Task<(List<Product> products, List<Hotspot> hotspots)> AnalyzeCatalogPage(
            string pdfFileName,
            int pageNumber,
            string imageFilePath,
            Guid catalogId,
            Guid pageId,
            RectObj tableRect,
            RectObj imageRect)
        {
            var products = new List<Product>();
            var hotspots = new List<Hotspot>();
            var foundRefNumbers = new HashSet<int>();

            var webRoot = _env.WebRootPath ??  Path.Combine(Directory.GetCurrentDirectory(), "wwwroot");

            var fullPdfPath = Path. Combine(webRoot, "uploads", pdfFileName);
            if (!File.Exists(fullPdfPath))
            {
                var altPath = Path.Combine(webRoot, "wwwroot", "uploads", pdfFileName);
                if (File.Exists(altPath)) fullPdfPath = altPath;
            }

            if (! File.Exists(fullPdfPath))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"❌ PDF Dosyası bulunamadı: {fullPdfPath}");
                Console.ResetColor();
                return (products, hotspots);
            }

            Console.WriteLine("\n" + new string('=', 80));
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console. WriteLine($"📄 GOOGLE CLOUD - ENHANCED TABLE PARSER V5");
            Console.ResetColor();
            Console.WriteLine($"   PDF: {pdfFileName} (Sayfa:  {pageNumber})");

            await AnalyzeTableFromPdf(fullPdfPath, pageNumber, tableRect, catalogId, products, foundRefNumbers);

            string imageFileName = Path.GetFileName(imageFilePath);
            string fullImagePath = Path. Combine(webRoot, "uploads", "pages", imageFileName);
            if (!File.Exists(fullImagePath))
            {
                fullImagePath = Path. Combine(webRoot, "wwwroot", "uploads", "pages", imageFileName);
            }

            if (foundRefNumbers.Count > 0 && File.Exists(fullImagePath))
            {
                using var originalImage = await Image.LoadAsync(fullImagePath);
                await CreateHotspotsWithGoogle(originalImage, imageRect, pageId, products, foundRefNumbers, hotspots);
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                Console. WriteLine("⚠️ Hotspot atlandı (Ürün yok veya resim bulunamadı).");
                Console.ResetColor();
            }

            Console.WriteLine("\n" + new string('=', 80));
            Console.ForegroundColor = ConsoleColor.Green;
            Console. WriteLine($"✅ İŞLEM TAMAMLANDI");
            Console.ResetColor();
            Console.WriteLine($"   📦 Bulunan Ürün:  {products.Count}");

            return (products, hotspots);
        }

        private DocumentProcessorServiceClient CreateClient()
        {
            var endpoint = $"{_location}-documentai.googleapis.com";
            string fullCredentialPath = Path. Combine(_env.ContentRootPath, "google-key.json");

            if (!File.Exists(fullCredentialPath)) throw new FileNotFoundException($"Google Key bulunamadı:  {fullCredentialPath}");

            var credential = GoogleCredential. FromFile(fullCredentialPath)
                    .CreateScoped(DocumentProcessorServiceClient. DefaultScopes);

            return new DocumentProcessorServiceClientBuilder
            {
                Endpoint = endpoint,
                ChannelCredentials = credential.ToChannelCredentials()
            }.Build();
        }

        private class TableStructure
        {
            public int RefIndex { get; set; } = -1;
            public int CodeIndex { get; set; } = -1;
            public int NameIndex { get; set; } = -1;
            public int TotalColumns { get; set; } = 0;
            public int HeaderRowIndex { get; set; } = 0;
            public bool IsMergedRefCode { get; set; } = false;
            public int MergedRefCodeIndex { get; set; } = -1;
        }

        private TableStructure DetectTableStructure(Document. Types.Page. Types.Table table, string fullText)
        {
            var structure = new TableStructure();

            var allRows = table.HeaderRows. Concat(table. BodyRows).ToList();
            structure.TotalColumns = allRows.FirstOrDefault()?.Cells.Count ?? 0;

            Console.WriteLine($"   🔍 Tablo analizi:  {structure.TotalColumns} sütun, {allRows.Count} satır");

            for (int rowIdx = 0; rowIdx < Math.Min(3, allRows.Count); rowIdx++)
            {
                var row = allRows[rowIdx];
                var cells = row. Cells. Select(c => GetTextFromLayout(fullText, c. Layout).ToLower().Trim()).ToList();

                Console.WriteLine($"   📝 Satır {rowIdx} hücreleri: [{string.Join("] [", cells)}]");

                for (int colIdx = 0; colIdx < cells.Count; colIdx++)
                {
                    string cellText = cells[colIdx];
                    if (string.IsNullOrEmpty(cellText)) continue;

                    if (IsMergedRefCodeHeader(cellText))
                    {
                        structure.IsMergedRefCode = true;
                        structure.MergedRefCodeIndex = colIdx;
                        structure.RefIndex = colIdx;
                        structure.CodeIndex = colIdx;
                        Console.ForegroundColor = ConsoleColor.Magenta;
                        Console.WriteLine($"      ✓ BİRLEŞİK SÜTUN tespit edildi:  [{colIdx}] = '{cellText. Replace("\n", "\\n")}'");
                        Console.ResetColor();
                    }
                    else if (structure.RefIndex == -1 && IsRefNoColumn(cellText))
                    {
                        structure.RefIndex = colIdx;
                        Console.WriteLine($"      ✓ Ref sütunu:  [{colIdx}] = '{cellText}'");
                    }
                    else if (structure.CodeIndex == -1 && ! structure.IsMergedRefCode && IsPartsCodeColumn(cellText))
                    {
                        structure.CodeIndex = colIdx;
                        Console. WriteLine($"      ✓ Code sütunu: [{colIdx}] = '{cellText}'");
                    }
                    else if (structure.NameIndex == -1 && IsPartsNameColumn(cellText))
                    {
                        structure. NameIndex = colIdx;
                        Console.WriteLine($"      ✓ Name sütunu: [{colIdx}] = '{cellText}'");
                    }
                }

                if (structure. IsMergedRefCode || structure.CodeIndex != -1 || structure.NameIndex != -1)
                {
                    structure.HeaderRowIndex = rowIdx;
                    break;
                }
            }

            if (structure.IsMergedRefCode)
            {
                if (structure. NameIndex == -1)
                {
                    structure.NameIndex = structure.MergedRefCodeIndex + 1;
                }
            }
            else
            {
                if (structure.RefIndex == -1) structure.RefIndex = 0;
                if (structure.CodeIndex == -1) structure.CodeIndex = structure.RefIndex + 1;
                if (structure. NameIndex == -1) structure.NameIndex = structure.CodeIndex + 1;
            }

            if (structure. NameIndex >= structure.TotalColumns)
                structure.NameIndex = structure.TotalColumns - 1;

            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine($"   ✅ Final Yapı:  Ref[{structure.RefIndex}], Code[{structure. CodeIndex}], Name[{structure. NameIndex}], Merged={structure.IsMergedRefCode}");
            Console.ResetColor();

            return structure;
        }

        private bool IsMergedRefCodeHeader(string text)
        {
            var patterns = new[]
            {
                @"no\. ?\s*\n\s*parts\s*no",
                @"no\.?\s+parts\s*no",
                @"ref\. ?\s*no\. ?\s*\n.*parts",
                @"item\s*\n\s*parts",
            };

            return patterns.Any(p => Regex.IsMatch(text, p, RegexOptions. IgnoreCase));
        }

        private bool IsRefNoColumn(string text)
        {
            if (text.Contains("parts")) return false;

            var exactMatches = new[] { "no", "no.", "ref", "ref.", "pos", "pos.", "item", "#" };
            return exactMatches.Contains(text);
        }

        private bool IsPartsCodeColumn(string text)
        {
            var patterns = new[]
            {
                "parts no", "parts no.", "part no", "part no.",
                "code", "part code", "parts code",
                "parça no", "parça kodu", "ürün kodu",
                "部品番号", "品番"
            };
            return patterns.Any(p => text.Contains(p));
        }

        private bool IsPartsNameColumn(string text)
        {
            var patterns = new[]
            {
                "name", "parts name", "part name",
                "description", "desc", "desc.",
                "açıklama", "parça adı", "ürün adı",
                "品名", "部品名"
            };
            return patterns.Any(p => text.Contains(p));
        }

        private bool IsHeaderRow(string rowText)
        {
            var headerPatterns = new[]
            {
                "parts no", "part no", "description", "parts name", "part name",
                "ref. no", "ref no", "品名", "amt.  req", "remarks", "level", "cons", "qty"
            };
            string lowerText = rowText.ToLower();
            int matchCount = headerPatterns.Count(p => lowerText.Contains(p));
            return matchCount >= 2;
        }

        private (string refNo, string partCode) SplitMergedRefCode(string mergedValue, int expectedRefNo)
        {
            if (string.IsNullOrWhiteSpace(mergedValue))
                return ("", "");

            string cleaned = mergedValue. Replace("\n", " ").Replace("\r", "").Trim();
            cleaned = Regex.Replace(cleaned, @"\s+", " ");

            // YÖNTEM 1: Boşlukla ayrılmış
            var spaceMatch = Regex.Match(cleaned, @"^(\d{1,3})\s+(. +)$");
            if (spaceMatch.Success)
            {
                string refNo = spaceMatch.Groups[1]. Value;
                string partCode = spaceMatch.Groups[2]. Value. Replace(" ", "");
                return (refNo, partCode);
            }

            // YÖNTEM 2: Sayaç bazlı ayırma
            string expectedStr = expectedRefNo. ToString();
            if (cleaned.StartsWith(expectedStr))
            {
                string remaining = cleaned.Substring(expectedStr.Length);
                if (remaining.Length >= 5 && (char.IsDigit(remaining[0]) || char.IsLetter(remaining[0])))
                {
                    return (expectedStr, remaining);
                }
            }

            // YÖNTEM 3: Regex ile sayı + harf paterni
            var letterMatch = Regex. Match(cleaned, @"^(\d{1,2})([A-Z][A-Z0-9]. *)$");
            if (letterMatch. Success)
            {
                string refNo = letterMatch.Groups[1].Value;
                string partCode = letterMatch.Groups[2].Value;
                return (refNo, partCode);
            }

            // YÖNTEM 4: İlk 1-2 rakamı ref olarak al
            if (cleaned.Length >= 8 && char.IsDigit(cleaned[0]))
            {
                if (expectedRefNo < 10)
                {
                    string refNo = cleaned. Substring(0, 1);
                    string partCode = cleaned. Substring(1);
                    if (int.TryParse(refNo, out int r) && r == expectedRefNo && partCode.Length >= 6)
                    {
                        return (refNo, partCode);
                    }
                }

                if (expectedRefNo >= 10 && cleaned.Length >= 9)
                {
                    string refNo = cleaned.Substring(0, 2);
                    string partCode = cleaned. Substring(2);
                    if (int.TryParse(refNo, out int r) && r == expectedRefNo && partCode.Length >= 6)
                    {
                        return (refNo, partCode);
                    }
                }
            }

            return ("", cleaned. Replace(" ", ""));
        }

        private bool IsValidPartCode(string code)
        {
            if (string. IsNullOrWhiteSpace(code)) return false;
            if (code. Length < 2) return false;
            if (code.Length > 25) return false;

            bool hasDigit = code.Any(char.IsDigit);
            bool hasOnlyValidChars = code.All(c => char.IsLetterOrDigit(c) || c == '-' || c == '_' || c == '.' || c == '=' || c == '/');
            bool startsWithUpperOrDigit = char.IsUpper(code[0]) || char.IsDigit(code[0]);

            return hasOnlyValidChars && (hasDigit || startsWithUpperOrDigit);
        }

        private bool IsValidRefNumber(string refNo, out int number)
        {
            number = 0;
            if (string. IsNullOrWhiteSpace(refNo)) return false;

            string cleanRef = Regex.Replace(refNo, @"[^\d]", "");
            if (int.TryParse(cleanRef, out number))
            {
                return number >= 1 && number <= 999;
            }
            return false;
        }

        private async Task AnalyzeTableFromPdf(
            string pdfPath,
            int pageNumber,
            RectObj tableRect,
            Guid catalogId,
            List<Product> products,
            HashSet<int> foundRefNumbers)
        {
            try
            {
                using var outputStream = new MemoryStream();
                var inputDocument = PdfReader.Open(pdfPath, PdfDocumentOpenMode.Import);
                int pageIndex = pageNumber - 1;
                if (pageIndex < 0 || pageIndex >= inputDocument. PageCount) return;

                var outputDocument = new PdfDocument();
                outputDocument. AddPage(inputDocument.Pages[pageIndex]);
                outputDocument.Save(outputStream);
                outputStream.Position = 0;
                var pdfBytes = await ByteString.FromStreamAsync(outputStream);

                var client = CreateClient();
                var processorName = ProcessorName. FromProjectLocationProcessor(_projectId, _location, _processorId);
                var request = new ProcessRequest
                {
                    Name = processorName. ToString(),
                    RawDocument = new RawDocument { Content = pdfBytes, MimeType = "application/pdf" }
                };

                Console.ForegroundColor = ConsoleColor.Cyan;
                Console. WriteLine($"☁️ Google Cloud'a PDF gönderiliyor...");
                Console.ResetColor();

                var response = await client.ProcessDocumentAsync(request);
                var document = response.Document;
                var page = document.Pages. FirstOrDefault();

                if (page == null || page.Tables. Count == 0)
                {
                    Console.ForegroundColor = ConsoleColor.Red;
                    Console.WriteLine("❌ Google bu PDF sayfasında tablo yapısı bulamadı.");
                    Console. ResetColor();
                    return;
                }

                Console.WriteLine($"📊 Sayfada {page. Tables.Count} tablo bulundu.");

                foreach (var table in page.Tables)
                {
                    var vertices = table.Layout.BoundingPoly.NormalizedVertices;
                    double tX = (vertices[0].X + vertices[2].X) / 2.0 * 100;
                    double tY = (vertices[0].Y + vertices[2].Y) / 2.0 * 100;
                    bool isTargetTable = tX >= tableRect.X && tX <= (tableRect.X + tableRect.W) &&
                                         tY >= tableRect.Y && tY <= (tableRect.Y + tableRect.H);

                    if (isTargetTable)
                    {
                        Console.WriteLine($"✅ Hedef Tablo İşleniyor ({table. BodyRows.Count} satır)...");

                        var structure = DetectTableStructure(table, document.Text);

                        int processedRows = 0;
                        int skippedRows = 0;
                        int duplicateRows = 0;
                        int expectedRefNo = 1;

                        var allRows = table.HeaderRows.Concat(table.BodyRows).ToList();
                        int startRowIndex = structure.HeaderRowIndex + 1;

                        Console.WriteLine($"   🚀 Veri satırları işleniyor (Satır {startRowIndex}'den itibaren)...");

                        for (int rowIdx = startRowIndex; rowIdx < allRows. Count; rowIdx++)
                        {
                            var row = allRows[rowIdx];

                            string rawRowText = string.Join(" ", row.Cells.Select(c => GetTextFromLayout(document.Text, c.Layout)));
                            if (IsHeaderRow(rawRowText))
                            {
                                skippedRows++;
                                continue;
                            }

                            string GetCell(int index)
                            {
                                if (index < 0 || index >= row.Cells. Count) return "";
                                return GetTextFromLayout(document.Text, row. Cells[index]. Layout).Trim();
                            }

                            string refNo = "";
                            string partCode = "";
                            string partName = "";

                            if (structure.IsMergedRefCode)
                            {
                                string mergedValue = GetCell(structure.MergedRefCodeIndex);
                                (refNo, partCode) = SplitMergedRefCode(mergedValue, expectedRefNo);
                                partName = GetCell(structure. NameIndex);

                                if (rowIdx - startRowIndex < 5)
                                {
                                    Console.WriteLine($"   📄 Row[{rowIdx}]:  Merged='{mergedValue}' -> Ref='{refNo}' | Code='{partCode}' | Name='{partName}'");
                                }
                            }
                            else
                            {
                                refNo = GetCell(structure. RefIndex);
                                partCode = GetCell(structure.CodeIndex);
                                partName = GetCell(structure.NameIndex);

                                if (rowIdx - startRowIndex < 5)
                                {
                                    Console.WriteLine($"   📄 Row[{rowIdx}]: Ref='{refNo}' | Code='{partCode}' | Name='{partName}'");
                                }

                                partCode = CleanPartCode(partCode);
                                (refNo, partCode, partName) = FixColumnShift(refNo, partCode, partName);
                            }

                            partCode = CleanPartCode(partCode);
                            partName = CleanPartName(partName);

                            if (IsValidPartCode(partCode))
                            {
                                int refNumber = 0;
                                if (IsValidRefNumber(refNo, out int parsedRef))
                                {
                                    refNumber = parsedRef;
                                    expectedRefNo = refNumber + 1;
                                }
                                else
                                {
                                    expectedRefNo++;
                                }

                                // ✨ DÜZELTİLMİŞ:  RefNo dahil edildi
                                bool added = AddProduct(products, catalogId, partCode, partName, refNumber, pageNumber);
                                
                                if (added)
                                {
                                    if (refNumber > 0)
                                    {
                                        foundRefNumbers.Add(refNumber);
                                    }
                                    processedRows++;
                                }
                                else
                                {
                                    duplicateRows++;
                                }
                            }
                            else
                            {
                                if (rowIdx - startRowIndex < 10)
                                {
                                    Console.WriteLine($"   ⚠️ Geçersiz kod atlandı: '{partCode}'");
                                }
                                skippedRows++;
                                expectedRefNo++;
                            }
                        }

                        Console.WriteLine($"   📊 İşlenen:  {processedRows}, Duplicate: {duplicateRows}, Atlanan: {skippedRows}");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"❌ Hata: {ex. Message}");
                Console.ResetColor();
            }
        }

        private string CleanPartCode(string code)
        {
            if (string.IsNullOrEmpty(code)) return "";

            code = code.Replace("\n", "").Replace("\r", "");
            code = Regex.Replace(code, @"\s+", "");

            return code. Trim();
        }

        private string CleanPartName(string name)
        {
            if (string.IsNullOrEmpty(name)) return "";

            name = name.Replace("_", " ");
            name = Regex.Replace(name, @"\s+", " ");

            return name.Trim();
        }

        private (string refNo, string partCode, string partName) FixColumnShift(
            string refNo, string partCode, string partName)
        {
            if (! string.IsNullOrEmpty(refNo) && refNo.Contains(" "))
            {
                var parts = refNo. Split(' ', 2);
                if (parts.Length == 2 && IsValidRefNumber(parts[0], out _) && IsValidPartCode(parts[1]))
                {
                    if (string.IsNullOrEmpty(partCode) || partCode == partName)
                    {
                        partCode = parts[1];
                    }
                    refNo = parts[0];
                }
            }

            if (string.IsNullOrEmpty(partCode) && !string.IsNullOrEmpty(refNo) && refNo.Length > 4)
            {
                if (IsValidPartCode(refNo) && ! IsValidRefNumber(refNo, out _))
                {
                    partCode = refNo;
                    refNo = "";
                }
            }

            return (refNo, partCode, partName);
        }

        private async Task CreateHotspotsWithGoogle(Image originalImage, RectObj imageRect, Guid pageId, List<Product> products, HashSet<int> foundRefNumbers, List<Hotspot> hotspots)
        {
            Console.WriteLine("\n🎯 HOTSPOT ANALİZİ.. .");
            using var drawingCropStream = new MemoryStream();
            int x = Math.Max(0, (int)((imageRect.X / 100.0) * originalImage.Width));
            int y = Math.Max(0, (int)((imageRect.Y / 100.0) * originalImage.Height));
            int w = Math.Min(originalImage.Width - x, (int)((imageRect.W / 100.0) * originalImage.Width));
            int h = Math.Min(originalImage.Height - y, (int)((imageRect.H / 100.0) * originalImage.Height));
            if (w <= 10 || h <= 10) return;

            originalImage.Clone(ctx => ctx. Crop(new Rectangle(x, y, w, h))).Save(drawingCropStream, new PngEncoder());
            drawingCropStream.Position = 0;

            try
            {
                var client = CreateClient();
                var processorName = ProcessorName.FromProjectLocationProcessor(_projectId, _location, _processorId);
                var imageBytes = await ByteString.FromStreamAsync(drawingCropStream);
                var request = new ProcessRequest { Name = processorName.ToString(), RawDocument = new RawDocument { Content = imageBytes, MimeType = "image/png" } };
                var response = await client.ProcessDocumentAsync(request);

                if (response.Document?. Pages?. FirstOrDefault() == null) return;

                foreach (var token in response.Document. Pages[0].Tokens)
                {
                    string text = GetTextFromLayout(response.Document.Text, token.Layout).Trim();
                    if (int.TryParse(text, out int number) && foundRefNumbers.Contains(number))
                    {
                        var matchedProduct = products. FirstOrDefault(p => p.RefNo == number);
                        var vertices = token.Layout. BoundingPoly.NormalizedVertices;
                        double centerX = (vertices[0].X + vertices[2]. X) / 2.0;
                        double centerY = (vertices[0]. Y + vertices[2].Y) / 2.0;
                        double finalX = imageRect.X + (centerX * imageRect.W);
                        double finalY = imageRect.Y + (centerY * imageRect. H);

                        if (matchedProduct != null && ! hotspots.Any(h => h.Number == number))
                        {
                            hotspots.Add(new Hotspot { Id = Guid.NewGuid(), PageId = pageId, ProductId = matchedProduct.Id, Number = number, X = finalX, Y = finalY, CreatedDate = DateTime. UtcNow });
                            Console.WriteLine($"   ✅ Hotspot:  {number}");
                        }
                    }
                }
            }
            catch (Exception ex) { Console.WriteLine($"Hotspot Hatası: {ex. Message}"); }
        }

        private string GetTextFromLayout(string fullText, Document.Types.Page. Types.Layout layout)
        {
            if (layout?. TextAnchor?. TextSegments == null) return "";
            StringBuilder sb = new StringBuilder();
            foreach (var segment in layout.TextAnchor.TextSegments)
            {
                int start = (int)segment.StartIndex; int end = (int)segment.EndIndex;
                if (start >= 0 && end > start && end <= fullText.Length) sb.Append(fullText.Substring(start, end - start));
            }
            return sb. ToString();
        }

        /// <summary>
        /// Ürün ekleme - RefNo ile birlikte duplicate kontrolü
        /// Aynı RefNo ile aynı sayfada zaten varsa ekleme yapılmaz
        /// Aynı Code farklı RefNo ile eklenebilir (tabloda aynı parça farklı pozisyonlarda olabilir)
        /// </summary>
        private bool AddProduct(List<Product> products, Guid catalogId, string code, string name, int refNo, int pageNumber)
        {
            // ✨ YENİ KONTROL: RefNo bazlı duplicate kontrolü
            // Aynı RefNo aynı sayfada zaten varsa ekleme
            if (refNo > 0 && products.Any(p => p.RefNo == refNo && p.PageNumber == pageNumber. ToString()))
            {
                Console.WriteLine($"   🔄 Duplicate (RefNo): Ref={refNo}, Code={code}");
                return false;
            }

            // RefNo yoksa (0), aynı kod aynı sayfada varsa ekleme
            if (refNo == 0 && products.Any(p => p.Code == code && p.PageNumber == pageNumber. ToString()))
            {
                Console.WriteLine($"   🔄 Duplicate (Code): Code={code}");
                return false;
            }

            products.Add(new Product
            {
                Id = Guid.NewGuid(),
                CatalogId = catalogId,
                Code = code,
                Name = name,
                Category = "Genel",
                Price = 0,
                StockQuantity = 10,
                CreatedDate = DateTime. UtcNow,
                PageNumber = pageNumber. ToString(),
                RefNo = refNo,
                Description = refNo > 0 ? $"Ref:  {refNo}" :  ""
            });

            return true;
        }
    }
}