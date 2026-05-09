"""
Scraper Modules - Pre-built scrapers for various data categories
"""
from .base import BaseScraper
from .ecommerce import EcommerceScraper
from .jobs_scraper import JobsScraper
from .news_scraper import NewsScraper
from .property_scraper import PropertyScraper

__all__ = [
    "BaseScraper",
    "EcommerceScraper",
    "JobsScraper",
    "NewsScraper",
    "PropertyScraper",
]
