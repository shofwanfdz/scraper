"""
Blibli scraping job runner.
Supports: API mode (fastest, stealth), CloakBrowser (browser fallback),
and undetected-chromedriver (legacy).
"""
import os
import sys
import re
import time
import random
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from webapp.jobs.base import (
    BrowserEngine,
    send_ws_message,
    wait_for_confirmation,
    detect_challenge,
    scroll_page_gradually,
    scroll_page_gradually_async,
)
from webapp.parsers.blibli import parse_product_card


# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "blibli"))


def build_blibli_url(keyword: str, page: int, filters: dict) -> str:
    """Build Blibli search URL with filters.

    Args:
        keyword: Search keyword
        page: Page number (1-based)
        filters: Dict with optional keys: min_price, max_price, rating, sort
    """
    from test_full_scrape import build_url
    return build_url(keyword, page, filters)


def run_blibli_job(job_id: str, keyword: str, pages: int, mode: str,
                   filters: dict, engine: BrowserEngine = BrowserEngine.API):
    """Run Blibli scraping job.

    Args:
        job_id: Unique job identifier for WebSocket messaging
        keyword: Search keyword
        pages: Number of pages to scrape
        mode: 'cepat' (fast) or 'lengkap' (complete with seller details)
        filters: Search filters dict
        engine: Browser engine to use (default: API)

    Returns:
        dict with 'total' and 'file' keys, or None on failure
    """
    if engine == BrowserEngine.API:
        return _run_with_api(job_id, keyword, pages, mode, filters)
    elif engine == BrowserEngine.CLOAKBROWSER:
        return _run_with_cloakbrowser(job_id, keyword, pages, mode, filters)
    else:
        return _run_with_uc(job_id, keyword, pages, mode, filters)


# ============================================================
# API MODE (Fastest, stealth - no browser needed)
# ============================================================

# Rotating User-Agents to mimic real browser diversity
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _build_stealth_headers(keyword: str) -> dict:
    """Build request headers that mimic a real browser session.

    Anti-detection measures:
    - Rotating User-Agent from real browser pool
    - Realistic Accept/Accept-Language headers
    - Proper Referer chain (looks like user navigated from search)
    - sec-ch-ua headers matching the UA
    - Random ordering variation via session
    """
    ua = random.choice(_USER_AGENTS)

    # Determine sec-ch-ua based on selected UA
    if "Chrome/125" in ua:
        sec_ch_ua = '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"'
    elif "Chrome/124" in ua:
        sec_ch_ua = '"Google Chrome";v="124", "Chromium";v="124", "Not-A.Brand";v="99"'
    elif "Firefox" in ua:
        sec_ch_ua = None  # Firefox doesn't send sec-ch-ua
    elif "Safari" in ua and "Chrome" not in ua:
        sec_ch_ua = None  # Safari doesn't send sec-ch-ua
    else:
        sec_ch_ua = '"Chromium";v="125", "Not.A/Brand";v="24"'

    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": f"https://www.blibli.com/cari/{quote_plus(keyword)}",
        "Origin": "https://www.blibli.com",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    if sec_ch_ua:
        headers["sec-ch-ua"] = sec_ch_ua
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = '"Windows"' if "Windows" in ua else '"macOS"'
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
        headers["Sec-Fetch-Site"] = "same-origin"

    return headers


def _parse_api_product(item: dict, page_num: int, keyword: str) -> dict:
    """Parse a single product from Blibli API response into our standard format."""
    price_data = item.get("price", {})
    review_data = item.get("review", {})
    location = item.get("location", "")

    # Extract merchant/seller info
    merchant_name = item.get("merchantName", "")
    if not merchant_name:
        merchant_name = item.get("seller", {}).get("name", "")

    # Build product link
    url_path = item.get("url", "")
    link = f"https://www.blibli.com{url_path}" if url_path else ""

    # Extract image
    images = item.get("images", [])
    image = images[0] if images else ""

    # Format prices as "Rp..." string (same as stealth mode)
    sale_price = price_data.get("salePrice", 0) or 0
    list_price = price_data.get("listPrice", 0) or 0
    harga_str = f"Rp{sale_price:,.0f}".replace(",", ".") if sale_price else ""
    harga_asli_str = f"Rp{list_price:,.0f}".replace(",", ".") if list_price else ""

    # Convert terjual to int (same as stealth mode parser)
    # API provides soldCountTotal (exact int) and soldRangeCount (dict with 'id'/'en' text)
    sold_total = item.get("soldCountTotal")
    if sold_total and isinstance(sold_total, (int, float)) and sold_total > 0:
        terjual_int = int(sold_total)
    else:
        # Fallback: try soldRangeCount text
        sold_range = item.get("soldRangeCount", {})
        if isinstance(sold_range, dict):
            sold_text = sold_range.get("id", "") or sold_range.get("en", "") or sold_range.get("soldCountText", "")
        else:
            sold_text = str(sold_range) if sold_range else ""
        sold_digits = re.sub(r"[^\d]", "", str(sold_text))
        terjual_int = int(sold_digits) if sold_digits else None

    # Review count for dashboard compatibility
    review_count = review_data.get("count", 0) or 0

    product = {
        "nama_produk": item.get("name", ""),
        "harga": harga_str,
        "harga_angka": sale_price,
        "harga_sebelum_diskon": harga_asli_str,
        "diskon_persen": price_data.get("discount", 0),
        "rating": review_data.get("rating", 0),
        "ulasan": review_count,
        "terjual": terjual_int,
        "penjual": merchant_name,
        "kota": location,
        "link": link,
        "gambar": image,
        "item_id": item.get("id", ""),
        "brand": item.get("brand", ""),
        "kategori": item.get("rootCategory", {}).get("name", ""),
        "status": item.get("status", ""),
        "tags": ", ".join(item.get("tags", [])),
        "page": page_num,
        "keyword": keyword,
        "scrape_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # Dashboard fields: comment_count & liked_count needed for rekomendasi_score
        "comment_count": review_count,
        "liked_count": terjual_int if terjual_int else 0,
        "stock": 0,
    }

    return product


def _run_with_api(job_id, keyword, pages, mode, filters):
    """Run Blibli scraping via backend API (no browser needed).

    Stealth measures:
    - Rotating User-Agent per session
    - Realistic browser headers (sec-ch-ua, Sec-Fetch-*)
    - Random delays between requests (mimics human browsing)
    - Session-based cookies (persistent like real browser)
    - Proper Referer chain
    """
    from exporters.excel_analytics import export_with_analytics

    send_ws_message(job_id, "status", {
        "message": "[BLIBLI] ⚡ Mode API — mengambil data langsung..."
    })

    session = requests.Session()
    all_products = []
    items_per_page = 24

    # First, visit the main page to get cookies (like a real user)
    try:
        init_headers = _build_stealth_headers(keyword)
        init_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        session.get(
            "https://www.blibli.com",
            headers=init_headers,
            timeout=10,
            allow_redirects=True,
        )
        time.sleep(random.uniform(1.0, 2.5))
    except Exception:
        pass  # Continue even if cookie prefetch fails

    for page_num in range(1, pages + 1):
        start = (page_num - 1) * items_per_page

        # Build API params
        params = {
            "searchTerm": keyword,
            "start": start,
            "itemPerPage": items_per_page,
        }

        # Apply filters
        if filters:
            if filters.get("min_price"):
                params["minPrice"] = filters["min_price"]
            if filters.get("max_price"):
                params["maxPrice"] = filters["max_price"]
            if filters.get("rating"):
                params["rating"] = filters["rating"]
            if filters.get("sort"):
                sort_map = {
                    "relevan": 0,
                    "terbaru": 1,
                    "harga_asc": 2,
                    "harga_desc": 3,
                    "terlaris": 4,
                }
                params["sort"] = sort_map.get(filters["sort"], 0)

        send_ws_message(job_id, "progress", {
            "message": f"[BLIBLI] ⚡ Page {page_num}/{pages}: Fetching API...",
            "page": page_num,
        })

        # Make API request with stealth headers
        headers = _build_stealth_headers(keyword)

        try:
            resp = session.get(
                "https://www.blibli.com/backend/search/products",
                params=params,
                headers=headers,
                timeout=15,
            )

            if resp.status_code != 200:
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] ⚠️ Page {page_num} status {resp.status_code}, "
                               f"fallback ke CloakBrowser..."
                })
                # Fallback to CloakBrowser if API blocked
                return _run_with_cloakbrowser(job_id, keyword, pages, mode, filters)

            data = resp.json()
            products_data = data.get("data", {}).get("products", [])

            if not products_data:
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] Page {page_num}: Tidak ada produk lagi."
                })
                break

            # Parse products
            page_products = []
            for item in products_data:
                product = _parse_api_product(item, page_num, keyword)
                if product.get("nama_produk"):
                    page_products.append(product)

            all_products.extend(page_products)
            send_ws_message(job_id, "progress", {
                "message": f"[BLIBLI] ✅ Page {page_num}/{pages}: {len(page_products)} produk "
                           f"(Total: {len(all_products)})",
                "page": page_num,
                "products": len(all_products),
            })

        except requests.exceptions.Timeout:
            send_ws_message(job_id, "status", {
                "message": f"[BLIBLI] ⚠️ Page {page_num} timeout, retrying..."
            })
            time.sleep(random.uniform(3.0, 5.0))
            try:
                resp = session.get(
                    "https://www.blibli.com/backend/search/products",
                    params=params,
                    headers=_build_stealth_headers(keyword),
                    timeout=20,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    products_data = data.get("data", {}).get("products", [])
                    for item in products_data:
                        product = _parse_api_product(item, page_num, keyword)
                        if product.get("nama_produk"):
                            all_products.append(product)
            except Exception:
                send_ws_message(job_id, "error", {
                    "message": f"[BLIBLI] ❌ Page {page_num} gagal setelah retry"
                })
                continue

        except Exception as e:
            send_ws_message(job_id, "error", {
                "message": f"[BLIBLI] ❌ Page {page_num} error: {str(e)[:80]}"
            })
            continue

        # Random delay between pages (mimic human behavior)
        if page_num < pages:
            delay = random.uniform(2.0, 5.0)
            send_ws_message(job_id, "status", {
                "message": f"[BLIBLI] Menunggu {delay:.1f}s sebelum page berikutnya..."
            })
            time.sleep(delay)

    # Fill missing sellers if needed
    _fill_missing_sellers(all_products, mode, job_id)

    return _export_results(all_products, keyword, filters, job_id)


# ============================================================
# CLOAKBROWSER ENGINE (Recommended - C++ patches, Turnstile bypass)
# ============================================================

def _run_with_cloakbrowser(job_id, keyword, pages, mode, filters):
    """Run Blibli scraping using CloakBrowser (Chromium C++ anti-detection)."""
    import cloakbrowser
    from exporters.excel_analytics import export_with_analytics

    send_ws_message(job_id, "status", {
        "message": "[BLIBLI] Membuka CloakBrowser (C++ anti-detection)..."
    })

    async def _scrape():
        browser = await cloakbrowser.launch_async(headless=True, geoip=True)
        all_products = []

        try:
            for page_num in range(1, pages + 1):
                url = build_blibli_url(keyword, page_num, filters)
                send_ws_message(job_id, "progress", {
                    "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Memuat halaman...",
                    "page": page_num,
                })

                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(5)

                # Check challenge
                if "challenge" in page.url.lower():
                    send_ws_message(job_id, "status", {
                        "message": f"[BLIBLI] ⚠️ Challenge terdeteksi di page {page_num}"
                    })
                    await asyncio.sleep(10)

                # Scroll
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Scrolling..."
                })
                await scroll_page_gradually_async(page, steps=8, delay=2.0)

                # Parse
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Extracting produk..."
                })
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                boxes = soup.find_all("a", class_="elf-product-card")
                if not boxes:
                    boxes = soup.select('a[href*="/p/"]')

                page_products = []
                for box in boxes:
                    product = parse_product_card(box)
                    if product:
                        product["page"] = page_num
                        product["keyword"] = keyword
                        product["scrape_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        page_products.append(product)

                all_products.extend(page_products)
                send_ws_message(job_id, "progress", {
                    "message": f"[BLIBLI] ✅ Page {page_num}/{pages}: {len(page_products)} produk "
                               f"(Total: {len(all_products)})",
                    "page": page_num,
                    "products": len(all_products),
                })

                await page.close()

                if page_num < pages:
                    await asyncio.sleep(8)

            _fill_missing_sellers(all_products, mode, job_id)

        finally:
            await browser.close()

        return all_products

    try:
        all_products = asyncio.run(_scrape())
    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[BLIBLI] CloakBrowser error: {str(e)[:100]}"
        })
        return None

    return _export_results(all_products, keyword, filters, job_id)


# ============================================================
# UNDETECTED-CHROMEDRIVER ENGINE (Legacy, least effective)
# ============================================================

def _run_with_uc(job_id, keyword, pages, mode, filters):
    """Run Blibli scraping using undetected-chromedriver (Selenium).

    Note: This is the least effective against Cloudflare.
    Consider using API mode or CloakBrowser instead.
    """
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from exporters.excel_analytics import export_with_analytics
    from core.brand_manager import BrandManager

    send_ws_message(job_id, "status", {"message": "[BLIBLI] Membuka Chrome browser (UC)..."})

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = uc.Chrome(options=options, use_subprocess=True, version_main=147)
    driver.set_page_load_timeout(90)

    all_products = []

    try:
        for page_num in range(1, pages + 1):
            url = build_blibli_url(keyword, page_num, filters)
            send_ws_message(job_id, "progress", {
                "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Memuat halaman...",
                "page": page_num,
            })

            driver.get(url)
            wait_time = 25 if page_num == 1 else 15
            time.sleep(wait_time)

            # Check challenge
            if "challenge" in driver.current_url:
                send_ws_message(job_id, "status", {
                    "message": "[BLIBLI] ⚠️ Challenge/anti-bot terdeteksi, menunggu..."
                })
                time.sleep(15)
                if "challenge" in driver.current_url:
                    send_ws_message(job_id, "error", {
                        "message": "[BLIBLI] Challenge tidak bisa dilewati. Gunakan CloakBrowser atau API mode."
                    })
                    break

            # Scroll
            send_ws_message(job_id, "status", {
                "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Scrolling..."
            })
            scroll_page_gradually(driver, steps=8, delay=2.5)

            # Wait for elements
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a.elf-product-card")
                    )
                )
            except Exception:
                pass
            time.sleep(6)

            # Auto brand on first page
            if page_num == 1:
                try:
                    brand_mgr = BrandManager()
                    brands = brand_mgr.scrape_brands_from_sidebar(driver, keyword)
                    if brands:
                        brand_mgr.save_to_database(brands, keyword)
                except Exception:
                    pass

            # Parse
            send_ws_message(job_id, "status", {
                "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Extracting produk..."
            })
            soup = BeautifulSoup(driver.page_source, "html.parser")
            boxes = soup.find_all("a", class_="elf-product-card")

            page_products = []
            for box in boxes:
                product = parse_product_card(box)
                if product:
                    product["page"] = page_num
                    product["keyword"] = keyword
                    product["scrape_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    page_products.append(product)

            all_products.extend(page_products)
            send_ws_message(job_id, "progress", {
                "message": f"[BLIBLI] ✅ Page {page_num}/{pages}: {len(page_products)} produk "
                           f"(Total: {len(all_products)})",
                "page": page_num,
                "products": len(all_products),
            })

            if page_num < pages:
                send_ws_message(job_id, "status", {
                    "message": "[BLIBLI] Menunggu sebelum page berikutnya..."
                })
                time.sleep(8)

        # Handle missing sellers (UC can fetch detail pages)
        missing = [p for p in all_products if not p.get("penjual")]
        if missing:
            if mode == "cepat":
                for p in missing:
                    p["penjual"] = "Seller Individu"
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] {len(missing)} seller ditandai 'Individu' (mode cepat)"
                })
            elif mode == "lengkap":
                from test_full_scrape import fetch_seller_from_detail
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] Mengambil detail {len(missing)} seller..."
                })
                for i, p in enumerate(missing):
                    link = p.get("link", "")
                    if link:
                        seller = fetch_seller_from_detail(driver, link)
                        p["penjual"] = seller if seller else "Seller Individu"
                    else:
                        p["penjual"] = "Seller Individu"
                    time.sleep(2)

    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[BLIBLI] Error: {str(e)[:80]}"
        })
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return _export_results(all_products, keyword, filters, job_id)


# ============================================================
# SHARED HELPERS
# ============================================================

def _fill_missing_sellers(products: list, mode: str, job_id: str):
    """Fill missing seller info based on scraping mode."""
    missing = [p for p in products if not p.get("penjual")]
    if not missing:
        return

    if mode == "cepat":
        for p in missing:
            p["penjual"] = "Seller Individu"
        send_ws_message(job_id, "status", {
            "message": f"[BLIBLI] {len(missing)} seller ditandai 'Individu' (mode cepat)"
        })
    # mode 'lengkap' for async engines would need separate detail page fetching
    # which is handled per-engine above


def _export_results(products: list, keyword: str, filters: dict, job_id: str):
    """Export scraped products to Excel with analytics."""
    if not products:
        return None

    from exporters.excel_analytics import export_with_analytics

    send_ws_message(job_id, "status", {
        "message": f"[BLIBLI] Mengexport {len(products)} produk ke Excel..."
    })
    hasil_dir = str(PROJECT_ROOT / "hasil" / "blibli")
    filepath = export_with_analytics(products, keyword, filters, output_dir=hasil_dir)
    return {"total": len(products), "file": os.path.basename(filepath)}
