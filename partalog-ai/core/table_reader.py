"""
PaddleOCR Table Reader - PDF/Görüntüden Tablo Okuma
"""

from paddleocr import PaddleOCR, PPStructure
import numpy as np
import cv2
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from loguru import logger
import re
import fitz  # PyMuPDF
from bs4 import BeautifulSoup


@dataclass
class TableRow:
    """Tablo satırı."""
    index: int
    cells: List[str]
    is_header: bool = False
    
    def get_cell(self, col_index: int) -> str:
        if 0 <= col_index < len(self.cells):
            return self.cells[col_index]. strip()
        return ""


@dataclass
class TableStructure:
    """Tablo yapısı analizi."""
    ref_index: int = -1
    code_index: int = -1
    name_index: int = -1
    header_row_index: int = 0
    is_merged_ref_code: bool = False
    total_columns: int = 0


@dataclass
class ExtractedProduct:
    """Tablodan çıkarılan ürün."""
    ref_number: int
    part_code: str
    part_name: str
    confidence: float = 1.0
    raw_row: List[str] = field(default_factory=list)


@dataclass
class TableResult:
    """Tablo okuma sonucu."""
    page_number: int
    table_index: int
    rows: List[TableRow]
    products: List[ExtractedProduct]
    bbox: Optional[List[float]] = None
    html: Optional[str] = None


class PaddleTableReader: 
    """
    PaddleOCR tabanlı tablo okuyucu. 
    """
    
    REF_PATTERNS = [
        r'^ref\. ? $', r'^no\.?$', r'^poz\.?$', r'^item\.?$', r'^pos\.?$', r'^#$'
    ]
    
    CODE_PATTERNS = [
        r'code', r'kod', r'part\s*n', r'parça\s*n', r'article', r'malzeme'
    ]
    
    NAME_PATTERNS = [
        r'name', r'ad[ıi]? $', r'isim', r'açıklama', r'description', r'tanım'
    ]
    
    HEADER_KEYWORDS = [
        'ref', 'no', 'code', 'kod', 'name', 'adı', 'description',
        'part', 'parça', 'poz', 'item', 'açıklama', 'malzeme'
    ]
    
    def __init__(
        self,
        use_gpu: bool = False,
        lang: str = 'en',
        show_log: bool = False,
        table_max_len: int = 800
    ):
        self.use_gpu = use_gpu
        self.lang = lang
        self. show_log = show_log
        self.table_max_len = table_max_len
        
        logger.info(f"🐼 PaddleOCR Table Reader başlatılıyor (GPU={use_gpu}, Lang={lang})")
        
        # PPStructure - Tablo yapısı tanıma
        self.table_engine = PPStructure(
            show_log=show_log,
            use_gpu=use_gpu,
            layout=True,
            table=True,
            ocr=True,
            recovery=True,
            lang=lang,
            table_max_len=table_max_len
        )
        
        # Düz OCR - Metin okuma için
        self.ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=use_gpu,
            show_log=show_log
        )
        
        logger.success("✅ PaddleOCR Table Reader hazır")
    
    def get_info(self) -> Dict[str, Any]:
        """Servis bilgilerini döndür."""
        return {
            "engine": "PaddleOCR",
            "version": "PP-StructureV2",
            "use_gpu": self.use_gpu,
            "lang": self. lang,
            "capabilities": ["table_extraction", "layout_analysis", "text_ocr", "pdf_processing"]
        }
    
    def extract_tables_from_pdf(
        self,
        pdf_path: str,
        page_number: int,
        table_rect: Optional[Dict[str, float]] = None
    ) -> List[TableResult]:
        """PDF'den tablo çıkar."""
        logger.info(f"📄 PDF'den tablo çıkarılıyor: {pdf_path}, Sayfa:  {page_number}")
        
        try:
            image = self._pdf_page_to_image(pdf_path, page_number)
            
            if image is None:
                logger. error("PDF sayfası görüntüye dönüştürülemedi")
                return []
            
            return self. extract_tables_from_image(image, page_number, table_rect)
            
        except Exception as e: 
            logger.error(f"PDF tablo çıkarma hatası:  {e}")
            return []
    
    def extract_tables_from_image(
        self,
        image: np.ndarray,
        page_number: int = 1,
        table_rect: Optional[Dict[str, float]] = None
    ) -> List[TableResult]:
        """Görüntüden tablo çıkar."""
        logger.info(f"🖼️ Görüntüden tablo çıkarılıyor (boyut: {image.shape})")
        
        results = []
        
        try:
            structure_result = self.table_engine(image)
            
            if not structure_result:
                logger. warning("PPStructure sonuç döndürmedi")
                return results
            
            img_height, img_width = image.shape[:2]
            table_index = 0
            
            for item in structure_result: 
                item_type = item.get('type', '')
                
                if item_type != 'table':
                    continue
                
                bbox = item.get('bbox', [])
                
                if table_rect and bbox:
                    if not self._is_in_target_region(bbox, img_width, img_height, table_rect):
                        continue
                
                table_html = item.get('res', {}).get('html', '')
                
                if not table_html:
                    continue
                
                rows = self._parse_table_html(table_html)
                
                if not rows:
                    continue
                
                structure = self._detect_table_structure(rows)
                products = self._extract_products(rows, structure)
                
                table_result = TableResult(
                    page_number=page_number,
                    table_index=table_index,
                    rows=rows,
                    products=products,
                    bbox=bbox,
                    html=table_html
                )
                
                results.append(table_result)
                table_index += 1
                
                logger.info(f"✅ Tablo {table_index}:  {len(rows)} satır, {len(products)} ürün")
            
            return results
            
        except Exception as e:
            logger.error(f"Görüntü tablo çıkarma hatası: {e}")
            import traceback
            traceback.print_exc()
            return results
    
    def extract_tables_from_bytes(
        self,
        file_bytes: bytes,
        page_number: int = 1,
        table_rect: Optional[Dict[str, float]] = None,
        is_pdf: bool = False
    ) -> List[TableResult]:
        """Byte dizisinden tablo çıkar."""
        try:
            if is_pdf: 
                image = self._pdf_bytes_to_image(file_bytes, page_number)
            else:
                nparr = np.frombuffer(file_bytes, np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                logger.error("Dosya görüntüye dönüştürülemedi")
                return []
            
            return self.extract_tables_from_image(image, page_number, table_rect)
            
        except Exception as e:
            logger.error(f"Bytes'dan tablo çıkarma hatası: {e}")
            return []
    
    def read_text_from_image(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Görüntüden düz metin oku."""
        try:
            result = self.ocr_engine. ocr(image, cls=True)
            
            texts = []
            if result and result[0]:
                for line in result[0]:
                    bbox = line[0]
                    text = line[1][0]
                    confidence = line[1][1]
                    
                    texts.append({
                        "text": text,
                        "bbox": bbox,
                        "confidence": confidence,
                        "center": {
                            "x": (bbox[0][0] + bbox[2][0]) / 2,
                            "y": (bbox[0][1] + bbox[2][1]) / 2
                        }
                    })
            
            return texts
            
        except Exception as e:
            logger.error(f"OCR hatası: {e}")
            return []
    
    # ==========================================
    # YARDIMCI METODLAR
    # ==========================================
    
    def _pdf_page_to_image(self, pdf_path: str, page_number: int, dpi: int = 200) -> Optional[np.ndarray]:
        """PDF sayfasını görüntüye dönüştür."""
        try:
            doc = fitz.open(pdf_path)
            
            if page_number < 1 or page_number > len(doc):
                doc.close()
                return None
            
            page = doc[page_number - 1]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            img_data = pix.tobytes("png")
            nparr = np.frombuffer(img_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            doc.close()
            return image
            
        except Exception as e:
            logger.error(f"PDF sayfa dönüştürme hatası: {e}")
            return None
    
    def _pdf_bytes_to_image(self, pdf_bytes: bytes, page_number: int, dpi: int = 200) -> Optional[np.ndarray]:
        """PDF bytes'ını görüntüye dönüştür."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            if page_number < 1 or page_number > len(doc):
                doc.close()
                return None
            
            page = doc[page_number - 1]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            img_data = pix.tobytes("png")
            nparr = np.frombuffer(img_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            doc.close()
            return image
            
        except Exception as e: 
            logger.error(f"PDF bytes dönüştürme hatası: {e}")
            return None
    
    def _is_in_target_region(
        self,
        bbox: List[float],
        img_width: int,
        img_height: int,
        target:  Dict[str, float]
    ) -> bool:
        """Tablo hedef bölgede mi?"""
        if not bbox or len(bbox) < 4:
            return True
        
        center_x = (bbox[0] + bbox[2]) / 2 / img_width * 100
        center_y = (bbox[1] + bbox[3]) / 2 / img_height * 100
        
        in_x = target['x'] <= center_x <= (target['x'] + target['w'])
        in_y = target['y'] <= center_y <= (target['y'] + target['h'])
        
        return in_x and in_y
    
    def _parse_table_html(self, html: str) -> List[TableRow]:
        """HTML tablosunu parse et."""
        if not html:
            return []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            rows = []
            
            for row_idx, tr in enumerate(soup.find_all('tr')):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    cell_text = td.get_text(strip=True)
                    cell_text = re.sub(r'\s+', ' ', cell_text)
                    cells.append(cell_text)
                
                if cells:
                    is_header = row_idx == 0 or bool(tr.find('th'))
                    rows.append(TableRow(index=row_idx, cells=cells, is_header=is_header))
            
            return rows
            
        except Exception as e: 
            logger.error(f"HTML parse hatası: {e}")
            return []
    
    def _detect_table_structure(self, rows: List[TableRow]) -> TableStructure:
        """Tablo yapısını analiz et."""
        structure = TableStructure()
        
        if not rows:
            return structure
        
        structure.total_columns = max(len(row.cells) for row in rows) if rows else 0
        
        for row_idx, row in enumerate(rows[: 3]):
            cells_lower = [c.lower().strip() for c in row.cells]
            
            for col_idx, cell in enumerate(cells_lower):
                if not cell: 
                    continue
                
                if structure.ref_index == -1:
                    for pattern in self.REF_PATTERNS:
                        if re.search(pattern, cell, re.IGNORECASE):
                            structure.ref_index = col_idx
                            break
                
                if structure.code_index == -1:
                    for pattern in self.CODE_PATTERNS:
                        if re.search(pattern, cell, re.IGNORECASE):
                            structure.code_index = col_idx
                            break
                
                if structure.name_index == -1:
                    for pattern in self.NAME_PATTERNS:
                        if re.search(pattern, cell, re. IGNORECASE):
                            structure.name_index = col_idx
                            break
            
            if self._has_header_keywords(cells_lower):
                structure.header_row_index = row_idx
                break
        
        # Varsayılan değerler
        if structure.ref_index == -1:
            structure.ref_index = 0
        if structure. code_index == -1:
            structure.code_index = min(1, structure.total_columns - 1)
        if structure.name_index == -1:
            structure. name_index = min(2, structure.total_columns - 1)
        
        logger.debug(f"Yapı:  Ref[{structure.ref_index}], Code[{structure.code_index}], Name[{structure.name_index}]")
        
        return structure
    
    def _has_header_keywords(self, cells: List[str]) -> bool:
        """Header anahtar kelimeleri içeriyor mu?"""
        all_text = ' '.join(cells).lower()
        matches = sum(1 for kw in self.HEADER_KEYWORDS if kw in all_text)
        return matches >= 2
    
    def _extract_products(self, rows: List[TableRow], structure: TableStructure) -> List[ExtractedProduct]:
        """Tablodan ürünleri çıkar."""
        products = []
        seen_refs = set()
        expected_ref = 1
        
        start_row = structure.header_row_index + 1
        
        for row in rows[start_row:]:
            try:
                if self._is_header_row(row):
                    continue
                
                ref_no = row.get_cell(structure.ref_index)
                part_code = row.get_cell(structure.code_index)
                part_name = row.get_cell(structure.name_index)
                
                part_code = self._clean_part_code(part_code)
                part_name = self._clean_part_name(part_name)
                
                ref_number = self._parse_ref_number(ref_no)
                
                if ref_number is None:
                    ref_number = expected_ref
                
                if not self._is_valid_part_code(part_code):
                    expected_ref += 1
                    continue
                
                if ref_number in seen_refs: 
                    continue
                
                products.append(ExtractedProduct(
                    ref_number=ref_number,
                    part_code=part_code,
                    part_name=part_name,
                    raw_row=row. cells
                ))
                
                seen_refs.add(ref_number)
                expected_ref = ref_number + 1
                
            except Exception as e:
                logger.debug(f"Satır işleme hatası: {e}")
                continue
        
        return products
    
    def _is_header_row(self, row: TableRow) -> bool:
        """Satır header mı?"""
        text = ' '.join(row.cells).lower()
        matches = sum(1 for kw in self.HEADER_KEYWORDS if kw in text)
        return matches >= 2
    
    def _parse_ref_number(self, ref_str: str) -> Optional[int]:
        """Ref numarasını parse et."""
        if not ref_str:
            return None
        numbers = re.findall(r'\d+', ref_str)
        if numbers:
            num = int(numbers[0])
            if 1 <= num <= 999:
                return num
        return None
    
    def _clean_part_code(self, code: str) -> str:
        """Parça kodunu temizle."""
        if not code:
            return ''
        code = code.strip()
        code = re.sub(r'\s+', '', code)
        return code
    
    def _clean_part_name(self, name: str) -> str:
        """Parça adını temizle."""
        if not name:
            return ''
        name = name.strip()
        name = re.sub(r'\s+', ' ', name)
        return name
    
    def _is_valid_part_code(self, code: str) -> bool:
        """Geçerli parça kodu mu?"""
        if not code or len(code) < 2:
            return False
        if not re.search(r'[a-zA-Z0-9]', code):
            return False
        return True


# Geriye uyumluluk
TableReader = PaddleTableReader