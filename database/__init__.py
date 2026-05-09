"""
Database Layer
"""
from .connection import DatabaseManager, get_db
from .models import Base, ScrapingJob, ScrapedData, ProxyRecord

__all__ = ["DatabaseManager", "get_db", "Base", "ScrapingJob", "ScrapedData", "ProxyRecord"]
