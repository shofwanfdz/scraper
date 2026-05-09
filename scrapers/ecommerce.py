"""
E-Commerce Scraper
Scrapes product data: prices, names, ratings, descriptions from e-commerce sites
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base import BaseScraper


class EcommerceScraper(BaseScraper):
    """
    Scraper for e-commerce websites.
    Extracts product information including prices, names, ratings, etc.
    """

    SCRAPER_NAME = "ecommerce"
    CATEGORY = "ecommerce"
    REQUIRES_BROWSER = False  # Set True for JS-heavy sites like Tokopedia

    # Common CSS selectors for product data (configurable)
    DEFAULT_SELECTORS = {
        "product_container": ".product-card, .product-item, .product, [data-product]",
        "name": "h2, h3, .product-name, .product-title, [data-product-name]",
        "price": ".price, .product-price, [data-price], .harga",
        "original_price": ".original-price, .old-price, .price-old, del",
        "rating": ".rating, .star-rating, [data-rating]",
        "image": "img",
        "link": "a",
        "description": ".description, .product-desc, p",
        "seller": ".seller, .shop-name, .store-name",
        "location": ".location, .city",
        "sold_count": ".sold, .terjual",
    }

    def __init__(self, selectors: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.selectors = selectors or self.DEFAULT_SELECTORS

    async def scrape(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape product listings from an e-commerce page.

        Args:
            target_url: URL of the product listing page
            max_pages: Maximum number of pages to scrape (default: 1)
            pagination_selector: CSS selector for next page button

        Returns:
            List of product data dictionaries
        """
        max_pages = kwargs.get("max_pages", 1)
        all_products = []
        current_url = target_url

        for page_num in range(1, max_pages + 1):
            logger.info(f"[{self.SCRAPER_NAME}] Scraping page {page_num}/{max_pages}: {current_url}")

            if self.REQUIRES_BROWSER:
                html = await self.browser.fetch_rendered(current_url)
            else:
                html = await self.engine.fetch_html(current_url)

            if not html:
                logger.warning(f"Failed to fetch page {page_num}")
                break

            soup = self.engine.parse_html(html)
            products = self._extract_products(soup, current_url)
            all_products.extend(products)

            logger.info(f"Page {page_num}: Found {len(products)} products")

            # Find next page URL
            if page_num < max_pages:
                next_url = self._find_next_page(soup, current_url)
                if next_url:
                    current_url = next_url
                else:
                    logger.info("No more pages found")
                    break

        return all_products

    def _extract_products(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract all products from a page"""
        products = []
        containers = soup.select(self.selectors["product_container"])

        # Filter honeypots
        from core.anti_detection import AntiDetection
        containers = AntiDetection.filter_honeypots(containers)

        for container in containers:
            product = self.parse_item(container)
            if product:
                # Make URLs absolute
                if product.get("link") and not product["link"].startswith("http"):
                    product["link"] = urljoin(base_url, product["link"])
                if product.get("image") and not product["image"].startswith("http"):
                    product["image"] = urljoin(base_url, product["image"])
                products.append(product)

        return products

    def parse_item(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """Parse a single product from a BeautifulSoup element"""
        if not isinstance(raw_data, Tag):
            return None

        container = raw_data
        product = {}

        # Extract name
        name_el = container.select_one(self.selectors["name"])
        if name_el:
            product["name"] = name_el.get_text(strip=True)
        else:
            return None  # Name is required

        # Extract price
        price_el = container.select_one(self.selectors["price"])
        if price_el:
            product["price"] = self._parse_price(price_el.get_text(strip=True))
            product["price_text"] = price_el.get_text(strip=True)

        # Extract original price (for discount calculation)
        orig_price_el = container.select_one(self.selectors["original_price"])
        if orig_price_el:
            product["original_price"] = self._parse_price(orig_price_el.get_text(strip=True))
            if product.get("price") and product.get("original_price"):
                discount = round(
                    (1 - product["price"] / product["original_price"]) * 100, 1
                )
                product["discount_percent"] = max(0, discount)

        # Extract rating
        rating_el = container.select_one(self.selectors["rating"])
        if rating_el:
            product["rating"] = self._parse_rating(rating_el)

        # Extract image
        img_el = container.select_one(self.selectors["image"])
        if img_el:
            product["image"] = (
                img_el.get("data-src") or img_el.get("src") or img_el.get("data-lazy-src")
            )

        # Extract link
        link_el = container.select_one(self.selectors["link"])
        if link_el:
            product["link"] = link_el.get("href", "")

        # Extract seller
        seller_el = container.select_one(self.selectors["seller"])
        if seller_el:
            product["seller"] = seller_el.get_text(strip=True)

        # Extract location
        location_el = container.select_one(self.selectors["location"])
        if location_el:
            product["location"] = location_el.get_text(strip=True)

        # Extract sold count
        sold_el = container.select_one(self.selectors["sold_count"])
        if sold_el:
            product["sold_count"] = self._parse_number(sold_el.get_text(strip=True))

        # Validate minimum required fields
        if not self.validate_item(product, ["name"]):
            return None

        return product

    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text (handles various formats)"""
        if not price_text:
            return None
        # Remove currency symbols and formatting
        cleaned = re.sub(r"[^\d.,]", "", price_text)
        # Handle Indonesian format (1.000.000 or 1,000,000)
        cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_rating(self, element: Tag) -> Optional[float]:
        """Parse rating from element"""
        # Try data attribute first
        rating = element.get("data-rating") or element.get("data-score")
        if rating:
            try:
                return float(rating)
            except ValueError:
                pass

        # Try text content
        text = element.get_text(strip=True)
        match = re.search(r"(\d+\.?\d*)", text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        # Try counting star elements
        stars = element.select(".star-full, .active-star, .filled")
        if stars:
            return float(len(stars))

        return None

    def _parse_number(self, text: str) -> Optional[int]:
        """Parse a number from text (handles 'rb', 'k', etc.)"""
        if not text:
            return None
        text = text.lower().strip()

        # Handle Indonesian abbreviations
        multiplier = 1
        if "rb" in text or "k" in text:
            multiplier = 1000
        elif "jt" in text or "m" in text:
            multiplier = 1000000

        match = re.search(r"(\d+\.?\d*)", text.replace(",", "."))
        if match:
            try:
                return int(float(match.group(1)) * multiplier)
            except ValueError:
                pass
        return None

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Find the next page URL"""
        # Common pagination patterns
        next_selectors = [
            "a.next", "a[rel='next']", ".pagination .next a",
            "a[aria-label='Next']", ".page-next a", "li.next a",
            "a:contains('Next')", "a:contains('»')",
        ]

        for selector in next_selectors:
            try:
                next_el = soup.select_one(selector)
                if next_el and next_el.get("href"):
                    return urljoin(current_url, next_el["href"])
            except Exception:
                continue

        return None
