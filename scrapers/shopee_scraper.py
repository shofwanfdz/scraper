"""
Shopee Scraper
Uses cookie-based authentication + undetected-chromedriver.

Flow:
1. Check if cookies exist → if not, prompt login
2. Load cookies into headless browser
3. Navigate to search page
4. Scrape product data
5. Export to Excel
"""
import time
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from loguru import logger

from scrapers.shopee_auth import ShopeeAuth


SHOPEE_SEARCH_URL = "https://shopee.co.id/search?keyword={}"


class ShopeeScraper:
    """
    Shopee product scraper with cookie-based authentication.
    """

    SCRAPER_NAME = "shopee"
    PRODUCTS_PER_PAGE = 60

    def __init__(self):
        self.auth = ShopeeAuth()
        self.driver = None

    def _init_driver(self, headless=True):
        """Initialize undetected Chrome driver."""
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = uc.Chrome(options=options, use_subprocess=True, version_main=147)
        self.driver.set_page_load_timeout(60)

    def ensure_login(self) -> bool:
        """
        Ensure user is logged in. If not, prompt manual login.
        
        Returns:
            True if logged in, False if user cancelled
        """
        if self.auth.has_valid_cookies():
            print("[+] Shopee session aktif (cookies tersimpan)")
            return True

        print("[!] Shopee memerlukan login.")
        print("    Pilihan:")
        print("    1. Login sekarang (buka browser)")
        print("    2. Batal")

        choice = input("\n    Pilih (1/2): ").strip()
        if choice == "1":
            return self.auth.login_manual()
        return False

    def scrape(self, keyword: str, max_pages: int = 3, filters: dict = None) -> List[Dict[str, Any]]:
        """
        Scrape products from Shopee.
        
        Args:
            keyword: Search keyword
            max_pages: Number of pages to scrape
            filters: Optional filters (price_min, price_max, rating, etc.)
            
        Returns:
            List of product dictionaries
        """
        filters = filters or {}

        # Ensure login
        if not self.ensure_login():
            print("[X] Login dibatalkan. Tidak bisa scrape Shopee.")
            return []

        print("\n" + "=" * 60)
        print("  SHOPEE SCRAPER")
        print("=" * 60)
        print("  Keyword : {}".format(keyword))
        print("  Pages   : {}".format(max_pages))
        print("=" * 60)

        # Init driver (non-headless for Shopee - anti-bot detects headless)
        print("\n[*] Starting Chrome (visible - Shopee blocks headless)...")
        self._init_driver(headless=False)

        all_products = []

        try:
            # Load cookies
            print("[*] Loading Shopee session...")
            if not self.auth.load_cookies_to_driver(self.driver):
                print("[!] Cookie expired. Perlu login ulang.")
                self.driver.quit()
                self.driver = None
                # Try manual login
                if self.auth.login_manual():
                    self._init_driver(headless=True)
                    self.auth.load_cookies_to_driver(self.driver)
                else:
                    return []

            # Scrape pages
            keyword_encoded = quote_plus(keyword)

            for page_num in range(max_pages):
                url = SHOPEE_SEARCH_URL.format(keyword_encoded)
                if page_num > 0:
                    url += "&page={}".format(page_num)

                # Apply filters to URL
                if filters.get("price_min"):
                    url += "&minPrice={}".format(filters["price_min"])
                if filters.get("price_max"):
                    url += "&maxPrice={}".format(filters["price_max"])
                if filters.get("rating"):
                    url += "&ratingFilter={}".format(filters["rating"])
                if filters.get("sort"):
                    # relevancy, ctime (newest), sales (top sales), price (price asc)
                    url += "&sortBy={}".format(filters["sort"])

                print("\n[*] Page {}/{}: {}".format(page_num + 1, max_pages, url[:80]))
                self.driver.get(url)

                # Wait for page to load
                wait_time = 15 if page_num == 0 else 10
                time.sleep(wait_time)

                # Scroll to load products
                for i in range(5):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight * {}/100);".format((i+1) * 20)
                    )
                    time.sleep(2)
                time.sleep(3)

                # Parse products
                html = self.driver.page_source
                products = self._parse_products(html)
                all_products.extend(products)

                print("    [+] Found {} products (Total: {})".format(len(products), len(all_products)))
                # Debug: save HTML if no products found
                if not products:
                    debug_file = "tests/shopee/debug_page{}.html".format(page_num + 1)
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(html[:200000])
                    print("    [DEBUG] HTML saved to {} ({} chars)".format(debug_file, len(html)))
                if page_num < max_pages - 1:
                    time.sleep(5)

        except Exception as e:
            print("\n[!] Error: {}".format(str(e)[:60]))
            import traceback
            traceback.print_exc()
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        print("\n[+] Scraping selesai: {} produk".format(len(all_products)))
        return all_products

    def _parse_products(self, html: str) -> List[Dict[str, Any]]:
        """Parse products from Shopee search page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        products = []

        # Shopee product card selectors (may change)
        # Common patterns: shopee-search-item-result__item, product-card
        product_cards = soup.find_all("div", class_=re.compile(r"shopee-search-item-result__item|product-card", re.I))

        if not product_cards:
            # Fallback: find by link pattern
            product_cards = soup.find_all("a", href=re.compile(r"/-i\.\d+\.\d+"))

        if not product_cards:
            # Fallback 2: find by data attribute
            product_cards = soup.find_all("div", attrs={"data-sqe": "item"})

        for card in product_cards:
            product = self._extract_product(card)
            if product:
                products.append(product)

        return products

    def _extract_product(self, card) -> Optional[Dict[str, Any]]:
        """Extract product data from a Shopee product card."""
        product = {}

        # Name
        name_el = card.find("div", class_=re.compile(r"name|title", re.I))
        if not name_el:
            name_el = card.find("span", class_=re.compile(r"name|title", re.I))
        if not name_el:
            # Try finding any long text
            for el in card.find_all(["div", "span"]):
                text = el.get_text(strip=True)
                if len(text) > 15 and not text.startswith("Rp") and "Terjual" not in text:
                    name_el = el
                    break

        if name_el:
            product["nama_produk"] = name_el.get_text(strip=True)
        else:
            return None

        if not product.get("nama_produk") or len(product["nama_produk"]) < 5:
            return None

        # Price
        price_el = card.find(string=re.compile(r"Rp[\d.]+"))
        if not price_el:
            price_el = card.find(class_=re.compile(r"price", re.I))
        if price_el:
            price_text = price_el.get_text(strip=True) if hasattr(price_el, "get_text") else str(price_el)
            product["harga"] = price_text
            product["harga_angka"] = self._parse_price(price_text)

        # Sold count
        sold_el = card.find(string=re.compile(r"Terjual|terjual|\d+\s*rb\+?\s*terjual", re.I))
        if not sold_el:
            sold_el = card.find(class_=re.compile(r"sold", re.I))
        if sold_el:
            sold_text = sold_el.get_text(strip=True) if hasattr(sold_el, "get_text") else str(sold_el)
            product["terjual_text"] = sold_text
            product["terjual"] = self._parse_sold(sold_text)

        # Rating
        rating_el = card.find(class_=re.compile(r"rating", re.I))
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            match = re.search(r"(\d+\.?\d*)", rating_text)
            if match:
                product["rating"] = float(match.group(1))

        # Location
        location_el = card.find(class_=re.compile(r"location|loc", re.I))
        if location_el:
            product["kota"] = location_el.get_text(strip=True)

        # Link
        link_el = card.find("a", href=True)
        if link_el:
            href = link_el.get("href", "")
            if not href.startswith("http"):
                href = "https://shopee.co.id" + href
            product["link"] = href

        # Image
        img_el = card.find("img")
        if img_el:
            product["gambar"] = img_el.get("src") or img_el.get("data-src") or ""

        # Discount
        discount_el = card.find(class_=re.compile(r"discount|promo", re.I))
        if discount_el:
            product["diskon"] = discount_el.get_text(strip=True)

        return product

    def _parse_price(self, text: str) -> Optional[int]:
        """Parse Shopee price: Rp89.000 -> 89000"""
        if not text:
            return None
        cleaned = re.sub(r"[^\d]", "", text)
        # Shopee sometimes shows price range "89.000 - 150.000"
        # Take the first price
        match = re.search(r"(\d{4,})", cleaned)
        if match:
            return int(match.group(1))
        return None

    def _parse_sold(self, text: str) -> Optional[int]:
        """Parse sold count: 'Terjual 4,2rb' -> 4200"""
        if not text:
            return None
        text = text.lower().replace("terjual", "").replace("+", "").strip()
        multiplier = 1
        if "rb" in text:
            multiplier = 1000
            text = text.replace("rb", "").strip()
        elif "jt" in text:
            multiplier = 1000000
            text = text.replace("jt", "").strip()
        text = text.replace(",", ".").strip()
        try:
            return int(float(text) * multiplier)
        except (ValueError, TypeError):
            return None
