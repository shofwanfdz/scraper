"""
Blibli.com Scraper - Using undetected-chromedriver to bypass anti-bot
Based on research from successful Blibli scraping projects on GitHub.

Key findings:
- Blibli uses CloudFlare-like challenge page
- Regular HTTP requests and Playwright get blocked (403 / redirect to /challenge/)
- Solution: undetected-chromedriver (modified Selenium that bypasses bot detection)
- CSS selectors: a.elf-product-card, span.els-product__title, div.els-product__fixed-price
- Need slow scrolling + long wait times (20s first page, 12s subsequent)
- URL pattern: https://www.blibli.com/cari/{keyword}?page={n}&start={offset}
"""
import time
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from loguru import logger

from scrapers.base import BaseScraper


class BlibliScraper(BaseScraper):
    """
    Blibli.com scraper using undetected-chromedriver.
    Bypasses CloudFlare anti-bot protection.
    """

    SCRAPER_NAME = "blibli"
    CATEGORY = "ecommerce"
    REQUIRES_BROWSER = True  # Uses its own browser (undetected-chromedriver)

    PRODUCTS_PER_PAGE = 40

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.driver = None

    async def setup(self):
        """Override: we use undetected-chromedriver instead of Playwright"""
        logger.info(f"[{self.SCRAPER_NAME}] Initializing undetected-chromedriver...")

    async def teardown(self):
        """Cleanup the Chrome driver"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        logger.info(f"[{self.SCRAPER_NAME}] Driver closed")

    def _init_driver(self):
        """Initialize undetected Chrome driver"""
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')

        # Auto-detect Chrome version or use configured version
        chrome_version = self.config.get("chrome_version", 147)
        self.driver = uc.Chrome(
            options=options,
            use_subprocess=True,
            version_main=chrome_version,
        )
        self.driver.set_page_load_timeout(60)
        logger.info(f"[{self.SCRAPER_NAME}] Chrome driver initialized (v{chrome_version})")

    async def scrape(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape products from Blibli.

        Args:
            target_url: Search URL or keyword
            max_pages: Number of pages to scrape (default: 3)
            keyword: Search keyword (alternative to URL)
            location: Province filter (e.g., "DKI+Jakarta")

        Returns:
            List of product dictionaries
        """
        max_pages = kwargs.get("max_pages", 3)
        keyword = kwargs.get("keyword", None)
        location = kwargs.get("location", None)

        # Extract keyword from URL if not provided
        if not keyword:
            if "/cari/" in target_url:
                keyword = target_url.split("/cari/")[-1].split("?")[0]
            else:
                keyword = "laptop"  # default

        # Initialize driver
        self._init_driver()

        all_products = []

        try:
            keyword_encoded = quote_plus(keyword)

            for page_num in range(1, max_pages + 1):
                # Build URL
                if page_num == 1:
                    url = f"https://www.blibli.com/cari/{keyword_encoded}"
                    if location:
                        url += f"?location={location}"
                else:
                    start = (page_num - 1) * self.PRODUCTS_PER_PAGE
                    url = f"https://www.blibli.com/cari/{keyword_encoded}?page={page_num}&start={start}"
                    if location:
                        url += f"&location={location}"

                logger.info(f"[{self.SCRAPER_NAME}] Page {page_num}/{max_pages}: {url}")

                # Navigate
                self.driver.get(url)

                # Wait for page to load (first page needs more time due to challenge)
                wait_time = 20 if page_num == 1 else 12
                time.sleep(wait_time)

                # Check if we got redirected to challenge page
                current_url = self.driver.current_url
                if 'challenge' in current_url:
                    logger.warning(f"[{self.SCRAPER_NAME}] Challenge page detected, waiting longer...")
                    time.sleep(15)
                    # Try to navigate again
                    self.driver.get(url)
                    time.sleep(15)
                    current_url = self.driver.current_url
                    if 'challenge' in current_url:
                        logger.error(f"[{self.SCRAPER_NAME}] Still on challenge page. Stopping.")
                        break

                # Scroll gradually to load lazy content
                for i in range(5):
                    self.driver.execute_script(
                        f"window.scrollTo(0, document.body.scrollHeight * {(i+1)*20}/100);"
                    )
                    time.sleep(2)

                # Final wait for all content to render
                time.sleep(5)

                # Wait for price elements to appear
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                try:
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//*[contains(text(), 'Rp') and string-length(text()) > 2]")
                        )
                    )
                except Exception:
                    logger.warning(f"[{self.SCRAPER_NAME}] Timeout waiting for price elements")

                # Parse the page
                html = self.driver.page_source
                soup = BeautifulSoup(html, "html.parser")

                # Extract products using known selectors
                products = self._extract_products_selenium(soup)
                all_products.extend(products)

                logger.info(f"[{self.SCRAPER_NAME}] Page {page_num}: Found {len(products)} products")

                # Delay between pages
                if page_num < max_pages:
                    time.sleep(5)

        except Exception as e:
            logger.error(f"[{self.SCRAPER_NAME}] Error: {e}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        return all_products

    def _extract_products_selenium(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract products from parsed HTML using Selenium-obtained page source"""
        products = []

        # Strategy 1: Find product cards by class (most reliable)
        boxes = soup.find_all('a', class_='elf-product-card')

        # Strategy 2: Fallback selectors
        if not boxes:
            boxes = soup.find_all('div', attrs={'data-testid': re.compile(r'product')})
        if not boxes:
            boxes = soup.find_all('a', href=re.compile(r'/p/'))

        for box in boxes:
            product = self.parse_item(box)
            if product:
                products.append(product)

        return products

    def parse_item(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """Parse a single product card from Blibli"""
        if raw_data is None:
            return None

        box = raw_data
        product = {}

        # === Extract product name ===
        try:
            # Primary: els-product__title
            nama_el = box.find('span', class_='els-product__title')
            if not nama_el:
                nama_el = box.find('div', class_=re.compile(r'title'))
            if nama_el:
                product['name'] = nama_el.get_text(strip=True)
            else:
                # Fallback: get from link title attribute
                title_attr = box.get('title', '')
                if title_attr:
                    product['name'] = title_attr
                else:
                    return None
        except Exception:
            return None

        if not product.get('name') or len(product['name']) < 3:
            return None

        # === Extract price ===
        try:
            price_el = box.find('div', class_='els-product__fixed-price')
            if not price_el:
                price_el = box.find('div', class_=re.compile(r'price'))
            if not price_el:
                # Try finding any element with Rp text
                price_el = box.find(string=re.compile(r'Rp\s*[\d.]+'))

            if price_el:
                price_text = price_el.get_text(strip=True) if hasattr(price_el, 'get_text') else str(price_el)
                product['price_text'] = price_text
                product['price'] = self._parse_price(price_text)
        except Exception:
            pass

        # === Extract seller ===
        try:
            seller_spans = box.find_all('span', class_='els-product__seller-name')
            if seller_spans:
                if len(seller_spans) >= 3:
                    product['seller'] = seller_spans[1].get_text(strip=True)
                    product['location'] = seller_spans[2].get_text(strip=True)
                elif len(seller_spans) == 2:
                    text1 = seller_spans[0].get_text(strip=True)
                    text2 = seller_spans[1].get_text(strip=True)
                    if text1.startswith(('Kota ', 'Kab. ')):
                        product['location'] = text1
                    else:
                        product['seller'] = text1
                        product['location'] = text2
                elif len(seller_spans) == 1:
                    text = seller_spans[0].get_text(strip=True)
                    if text.startswith(('Kota ', 'Kab. ')):
                        product['location'] = text
                    else:
                        product['seller'] = text
        except Exception:
            pass

        # === Extract sold count ===
        try:
            sold_el = box.find('div', class_='els-product__sold')
            if sold_el:
                product['sold_text'] = sold_el.get_text(strip=True)
                product['sold_count'] = self._parse_sold(sold_el.get_text(strip=True))
        except Exception:
            pass

        # === Extract rating ===
        try:
            rate_wrapper = box.find('div', class_='els-product__rating-wrapper')
            if rate_wrapper:
                rate_span = rate_wrapper.find_next('span')
                if rate_span:
                    rating_text = rate_span.get_text(strip=True)
                    product['rating'] = float(rating_text.replace(',', '.'))
        except Exception:
            pass

        # === Extract link ===
        try:
            href = box.get('href', '')
            if href:
                if not href.startswith('http'):
                    href = 'https://www.blibli.com' + href
                product['link'] = href
        except Exception:
            pass

        # === Extract image ===
        try:
            img = box.find('img')
            if img:
                product['image'] = img.get('data-src') or img.get('src', '')
        except Exception:
            pass

        return product

    def _parse_price(self, price_text: str) -> Optional[int]:
        """Parse Blibli price format: Rp328.060 -> 328060"""
        if not price_text:
            return None
        # Remove everything except digits
        cleaned = re.sub(r'[^\d]', '', price_text)
        try:
            price = int(cleaned)
            return price if price > 0 else None
        except (ValueError, TypeError):
            return None

    def _parse_sold(self, sold_text: str) -> Optional[int]:
        """Parse sold count: 'Terjual 4,2 rb' -> 4200"""
        if not sold_text:
            return None

        text = sold_text.lower().replace('terjual', '').strip()

        multiplier = 1
        if 'rb' in text:
            multiplier = 1000
            text = text.replace('rb', '').strip()
        elif 'jt' in text:
            multiplier = 1000000
            text = text.replace('jt', '').strip()

        # Handle comma as decimal separator
        text = text.replace(',', '.').strip()

        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return None
