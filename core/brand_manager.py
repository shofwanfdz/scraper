"""
Brand Manager
Auto-scrapes brand names from Blibli sidebar filter and stores in database.
Only adds new brands, skips existing ones.
"""
import re
import time
from typing import List, Optional
from datetime import datetime

from bs4 import BeautifulSoup
from loguru import logger


class BrandManager:
    """
    Manages brand detection:
    1. Scrapes brands from Blibli sidebar filter (auto-detect per keyword)
    2. Stores new brands in database
    3. Provides brand matching for product names
    """

    def __init__(self):
        self._brands_cache: List[str] = []

    def scrape_brands_from_sidebar(self, driver, keyword: str = "") -> List[str]:
        """
        Scrape all brand names from Blibli's Brand filter modal.
        Call this AFTER the search page has loaded.
        
        Args:
            driver: Active undetected_chromedriver instance (already on search page)
            keyword: The search keyword (for categorization)
            
        Returns:
            List of clean brand names
        """
        brands = []

        try:
            # Click "Lihat semua" inside Brand section
            result = driver.execute_script("""
                var allElements = document.querySelectorAll('*');
                var foundBrand = false;
                
                for (var i = 0; i < allElements.length; i++) {
                    var el = allElements[i];
                    var directText = '';
                    for (var j = 0; j < el.childNodes.length; j++) {
                        if (el.childNodes[j].nodeType === 3) directText += el.childNodes[j].textContent.trim();
                    }
                    
                    if (directText === 'Brand' && !foundBrand) {
                        foundBrand = true;
                        var parent = el.parentElement;
                        for (var k = 0; k < 5; k++) {
                            if (parent && parent.parentElement) {
                                parent = parent.parentElement;
                                var seeAll = parent.querySelector('[class*="see-all"], [class*="show-more"]');
                                if (seeAll) {
                                    seeAll.click();
                                    return 'clicked';
                                }
                            }
                        }
                        return 'no-button';
                    }
                }
                return 'not-found';
            """)

            if result != "clicked":
                logger.debug("Brand 'Lihat semua' not found: {}".format(result))
                # Fallback: get the 5 visible brands from sidebar
                return self._get_sidebar_brands(driver)

            # Wait for modal to open
            time.sleep(4)

            # Extract brands from modal
            modal_html = driver.execute_script("""
                var modal = document.querySelector('.filter-desktop-modal');
                return modal ? modal.innerHTML : '';
            """)

            if modal_html:
                brands = self._parse_brands_from_modal(modal_html)

            # Close modal
            driver.execute_script("""
                var closeBtn = document.querySelector('.filter-desktop-modal [class*="close"], .filter-desktop-modal [class*="back"]');
                if (closeBtn) closeBtn.click();
                else {
                    var modal = document.querySelector('.filter-desktop-modal');
                    if (modal) modal.style.display = 'none';
                }
            """)
            time.sleep(1)

        except Exception as e:
            logger.debug("Error scraping brands: {}".format(str(e)[:60]))

        # Fallback if modal didn't work
        if not brands:
            brands = self._get_sidebar_brands(driver)

        logger.info("Scraped {} brands for keyword '{}'".format(len(brands), keyword))
        self._brands_cache = brands
        return brands

    def _get_sidebar_brands(self, driver) -> List[str]:
        """Get the 5 visible brands from sidebar (without clicking Lihat semua)"""
        try:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            brands = []
            # Find Brand section text, then get sibling items
            for el in soup.find_all(string=re.compile(r"^Brand$")):
                parent = el.parent
                container = parent
                for _ in range(5):
                    if container.parent:
                        container = container.parent
                    items = container.find_all(["label", "span"])
                    for item in items:
                        text = item.get_text(strip=True)
                        if (text and 2 < len(text) < 30
                            and text not in ["Brand", "Lihat semua"]
                            and not text.startswith("Rp")):
                            brands.append(text)
                    if len(brands) >= 3:
                        break
                if brands:
                    break
            return self._clean_brands(brands)
        except Exception:
            return []

    def _parse_brands_from_modal(self, html: str) -> List[str]:
        """Parse brand names from the filter modal HTML"""
        soup = BeautifulSoup(html, "html.parser")
        raw_brands = []

        # Find all checkbox labels / items
        for item in soup.find_all(["label", "span", "div"]):
            text = item.get_text(strip=True)
            # Filter criteria for valid brand names
            if (text and 2 < len(text) < 35
                and text not in ["Brand", "Merek", "Lihat semua", "Terapkan", "Reset",
                                 "Cari brand", "#ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
                and not text.startswith("Rp")
                and not text.startswith("Cari")
                and not text.isdigit()
                and "(" not in text
                and len(text.split()) <= 3):  # Brand names are max 3 words
                raw_brands.append(text)

        return self._clean_brands(raw_brands)

    def _clean_brands(self, raw_brands: List[str]) -> List[str]:
        """Clean and deduplicate brand list"""
        # Invalid entries to skip
        invalid = [
            "Lainnya", "no brand", "ResetSimpan", "Reset", "Simpan",
            "Terapkan", "Cari brand", "Brand", "Merek",
            "#ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        ]

        seen = set()
        clean = []
        for brand in raw_brands:
            brand = brand.strip()

            # Skip empty or too short
            if not brand or len(brand) < 2:
                continue

            # Skip known invalid entries
            if brand in invalid or brand.lower() in [i.lower() for i in invalid]:
                continue

            # Skip concatenated brands (e.g., "HPHUAWEI", "SAMSUNGSPC")
            # Heuristic: if no spaces and has multiple uppercase transitions
            if " " not in brand and len(brand) > 6:
                caps_transitions = len(re.findall(r"[a-z][A-Z]|[A-Z][A-Z][a-z]", brand))
                if caps_transitions >= 1:
                    continue

            # Skip if all uppercase and > 10 chars (likely concatenated)
            if brand.isupper() and len(brand) > 10:
                continue

            normalized = brand.strip()
            if normalized.lower() not in seen and len(normalized) > 1:
                seen.add(normalized.lower())
                clean.append(normalized)

        return clean

    def save_to_database(self, brands: List[str], keyword: str = "", source: str = "blibli"):
        """
        Save brands to database. Only adds NEW brands, skips existing.
        
        Args:
            brands: List of brand names to save
            keyword: Category/keyword where brands were found
            source: Marketplace source
            
        Returns:
            Tuple of (new_count, existing_count)
        """
        from database.connection import get_db
        from database.models import Brand

        db = get_db()
        new_count = 0
        existing_count = 0

        with db.get_session() as session:
            for brand_name in brands:
                # Check if brand already exists
                existing = session.query(Brand).filter(
                    Brand.name == brand_name
                ).first()

                if existing:
                    # Update category if new keyword found
                    if keyword and existing.category:
                        categories = existing.category.split(",")
                        if keyword not in categories:
                            existing.category = existing.category + "," + keyword
                            existing.updated_at = datetime.utcnow()
                    existing_count += 1
                else:
                    # Add new brand
                    new_brand = Brand(
                        name=brand_name,
                        source=source,
                        category=keyword,
                        is_active=True,
                    )
                    session.add(new_brand)
                    new_count += 1

            session.commit()

        logger.info("Brands saved: {} new, {} existing (skipped)".format(new_count, existing_count))
        return new_count, existing_count

    def get_all_brands_from_db(self, source: str = None) -> List[str]:
        """Get all brand names from database"""
        from database.connection import get_db
        from database.models import Brand

        db = get_db()
        with db.get_session() as session:
            query = session.query(Brand.name).filter(Brand.is_active == True)
            if source:
                query = query.filter(Brand.source == source)
            brands = [row[0] for row in query.all()]

        return brands

    def match_brand(self, product_name: str, brands: List[str] = None) -> str:
        """
        Match a product name to a brand.
        Uses cached brands or provided list.
        
        Args:
            product_name: Product name to match
            brands: Optional list of brands (uses cache/DB if not provided)
            
        Returns:
            Brand name or "Lainnya"
        """
        if not product_name:
            return "Lainnya"

        if brands is None:
            brands = self._brands_cache if self._brands_cache else self.get_all_brands_from_db()

        name_upper = product_name.upper()
        for brand in brands:
            if brand.upper() in name_upper:
                return brand

        return "Lainnya"
