"""Core modules - AI işleme modülleri."""

from .detector import HotspotDetector
from .ocr import HotspotOCR
from .table_reader import PaddleTableReader

__all__ = ['HotspotDetector', 'HotspotOCR', 'PaddleTableReader']