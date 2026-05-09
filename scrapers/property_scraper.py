"""
Property/Real Estate Scraper
Scrapes property listings: prices, locations, specifications
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base import BaseScraper


class PropertyScraper(BaseScraper):
    """
    Scraper for real estate/property listing websites.
    Extracts property details including prices, locations, and specifications.
    """

    SCRAPER_NAME = "property"
    CATEGORY = "property"
    REQUIRES_BROWSER = False

    DEFAULT_SELECTORS = {
        "property_container": ".property-card, .listing-item, .property, .card",
        "title": "h2, h3, .property-title, .listing-title",
        "price": ".price, .property-price, .listing-price, [data-price]",
        "location": ".location, .address, .property-location",
        "bedrooms": ".bed, .bedroom, [data-bed]",
        "bathrooms": ".bath, .bathroom, [data-bath]",
        "area": ".area, .size, .land-size, .sqft, [data-area]",
        "property_type": ".type, .property-type, .category",
        "image": "img",
        "link": "a",
        "agent": ".agent, .realtor, .contact-name",
        "description": ".description, .property-desc",
        "features": ".features li, .amenities li, .facility",
    }

    def __init__(self, selectors: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.selectors = selectors or self.DEFAULT_SELECTORS

    async def scrape(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape property listings.

        Args:
            target_url: URL of the property listing page
            max_pages: Maximum pages to scrape
            property_type: Filter by type (house, apartment, land)

        Returns:
            List of property data dictionaries
        """
        max_pages = kwargs.get("max_pages", 1)
        all_properties = []
        current_url = target_url

        for page_num in range(1, max_pages + 1):
            logger.info(f"[{self.SCRAPER_NAME}] Scraping page {page_num}: {current_url}")

            html = await self.engine.fetch_html(current_url)
            if not html:
                break

            soup = self.engine.parse_html(html)
            properties = self._extract_properties(soup, current_url)
            all_properties.extend(properties)

            logger.info(f"Page {page_num}: Found {len(properties)} properties")

            if page_num < max_pages:
                next_url = self._find_next_page(soup, current_url)
                if next_url:
                    current_url = next_url
                else:
                    break

        return all_properties

    def _extract_properties(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract all properties from a page"""
        properties = []
        containers = soup.select(self.selectors["property_container"])

        from core.anti_detection import AntiDetection
        containers = AntiDetection.filter_honeypots(containers)

        for container in containers:
            prop = self.parse_item(container)
            if prop:
                if prop.get("link") and not prop["link"].startswith("http"):
                    prop["link"] = urljoin(base_url, prop["link"])
                if prop.get("image") and not prop["image"].startswith("http"):
                    prop["image"] = urljoin(base_url, prop["image"])
                properties.append(prop)

        return properties

    def parse_item(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """Parse a single property listing"""
        if not isinstance(raw_data, Tag):
            return None

        container = raw_data
        prop = {}

        # Title
        title_el = container.select_one(self.selectors["title"])
        if title_el:
            prop["title"] = title_el.get_text(strip=True)
        else:
            return None

        # Price
        price_el = container.select_one(self.selectors["price"])
        if price_el:
            price_text = price_el.get_text(strip=True)
            prop["price_text"] = price_text
            prop["price"] = self._parse_price(price_text)

        # Location
        location_el = container.select_one(self.selectors["location"])
        if location_el:
            prop["location"] = location_el.get_text(strip=True)

        # Bedrooms
        bed_el = container.select_one(self.selectors["bedrooms"])
        if bed_el:
            prop["bedrooms"] = self._extract_number(bed_el.get_text(strip=True))

        # Bathrooms
        bath_el = container.select_one(self.selectors["bathrooms"])
        if bath_el:
            prop["bathrooms"] = self._extract_number(bath_el.get_text(strip=True))

        # Area/Size
        area_el = container.select_one(self.selectors["area"])
        if area_el:
            area_text = area_el.get_text(strip=True)
            prop["area_text"] = area_text
            prop["area_sqm"] = self._parse_area(area_text)

        # Property type
        type_el = container.select_one(self.selectors["property_type"])
        if type_el:
            prop["property_type"] = type_el.get_text(strip=True)

        # Image
        img_el = container.select_one(self.selectors["image"])
        if img_el:
            prop["image"] = img_el.get("data-src") or img_el.get("src")

        # Link
        link_el = container.select_one(self.selectors["link"])
        if link_el:
            prop["link"] = link_el.get("href", "")

        # Agent
        agent_el = container.select_one(self.selectors["agent"])
        if agent_el:
            prop["agent"] = agent_el.get_text(strip=True)

        # Features
        feature_els = container.select(self.selectors["features"])
        if feature_els:
            prop["features"] = [f.get_text(strip=True) for f in feature_els[:10]]

        if not self.validate_item(prop, ["title"]):
            return None

        return prop

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse property price"""
        if not price_text:
            return None

        # Handle Indonesian format
        text = price_text.lower()
        multiplier = 1

        if "miliar" in text or "m" in text:
            multiplier = 1_000_000_000
        elif "juta" in text or "jt" in text:
            multiplier = 1_000_000

        cleaned = re.sub(r"[^\d.,]", "", price_text)
        cleaned = cleaned.replace(".", "").replace(",", ".")

        try:
            return float(cleaned) * multiplier
        except (ValueError, TypeError):
            return None

    def _parse_area(self, area_text: str) -> Optional[float]:
        """Parse area in square meters"""
        if not area_text:
            return None

        match = re.search(r"(\d+[\d.,]*)", area_text)
        if match:
            try:
                value = float(match.group(1).replace(",", "."))
                # Convert sqft to sqm if needed
                if "sqft" in area_text.lower() or "sq ft" in area_text.lower():
                    value *= 0.0929
                return value
            except ValueError:
                pass
        return None

    def _extract_number(self, text: str) -> Optional[int]:
        """Extract a number from text"""
        match = re.search(r"(\d+)", text)
        if match:
            return int(match.group(1))
        return None

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Find next page URL"""
        next_selectors = [
            "a.next", "a[rel='next']", ".pagination .next a",
            "a[aria-label='Next']", "li.next a",
        ]
        for selector in next_selectors:
            try:
                el = soup.select_one(selector)
                if el and el.get("href"):
                    return urljoin(current_url, el["href"])
            except Exception:
                continue
        return None
