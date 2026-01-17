"""API - FastAPI router'ları."""

from .hotspot import router as hotspot_router
from .table import router as table_router

__all__ = ['hotspot_router', 'table_router']