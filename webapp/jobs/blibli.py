"""
Blibli scraping job runner.
Supports: undetected-chromedriver, CloakBrowser, and Camoufox (recommended).
"""
import os
import sys
import time
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

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
                   filters: dict, engine: BrowserEngine = BrowserEngine.CAMOUFOX):
    """Run Blibli scraping job.

    Args:
        job_id: Unique job identifier for WebSocket messaging
        keyword: Search keyword
        pages: Number of pages to scrape
        mode: 'cepat' (fast) or 'lengkap' (complete with seller details)
        filters: Search filters dict
        engine: Browser engine to use (default: Camoufox)

    Returns:
        dict with 'total' and 'file' keys, or None on failure
    """
    if engine == BrowserEngine.CAMOUFOX:
        return _run_with_camoufox(job_id, keyword, pages, mode, filters)
    elif engine == BrowserEngine.CLOAKBROWSER:
        return _run_with_cloakbrowser(job_id, keyword, pages, mode, filters)
    else:
        return _run_with_uc(job_id, keyword, pages, mode, filters)


# ============================================================
# CAMOUFOX ENGINE (Recommended - Firefox-based, best CF bypass)
# ============================================================

def _run_with_camoufox(job_id, keyword, pages, mode, filters):
    """Run Blibli scraping using Camoufox (Firefox-based anti-detection).

    Advantages over Chrome-based tools:
    - Different TLS fingerprint (JA3) - harder for Cloudflare to detect
    - C++ level fingerprint injection (not JS injection)
    - BrowserForge fingerprints matching real-world traffic distribution
    - Per-context fingerprint rotation
    - ~200mb RAM (debloated Firefox)
    - Playwright API (async/sync)
    """
    from exporters.excel_analytics import export_with_analytics

    send_ws_message(job_id, "status", {
        "message": "[BLIBLI] 🦊 Membuka Camoufox (Firefox anti-detection)..."
    })

    async def _scrape():
        from camoufox.async_api import AsyncCamoufox

        async with AsyncCamoufox(headless=True) as browser:
            all_products = []

            for page_num in range(1, pages + 1):
                url = build_blibli_url(keyword, page_num, filters)
                send_ws_message(job_id, "progress", {
                    "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Memuat halaman...",
                    "page": page_num,
                })

                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    send_ws_message(job_id, "status", {
                        "message": f"[BLIBLI] ⚠️ Page {page_num} timeout, retrying..."
                    })
                    await asyncio.sleep(5)
                    try:
                        await page.goto(url, wait_until="load", timeout=90000)
                    except Exception:
                        send_ws_message(job_id, "error", {
                            "message": f"[BLIBLI] ❌ Page {page_num} gagal dimuat"
                        })
                        await page.close()
                        continue

                # Wait for content render
                await asyncio.sleep(5)

                # Check challenge
                html_check = await page.content()
                url_check = page.url
                if detect_challenge(html_check, url_check):
                    send_ws_message(job_id, "status", {
                        "message": f"[BLIBLI] ⚠️ Challenge terdeteksi, menunggu auto-solve..."
                    })
                    # Camoufox biasanya bisa auto-solve Turnstile
                    await asyncio.sleep(10)
                    html_check = await page.content()
                    url_check = page.url
                    if detect_challenge(html_check, url_check):
                        send_ws_message(job_id, "need_action", {
                            "message": "[BLIBLI] Challenge tidak bisa di-bypass otomatis. Coba lagi nanti.",
                            "action": "challenge_failed",
                        })
                        await page.close()
                        break

                # Scroll to trigger lazy load
                send_ws_message(job_id, "status", {
                    "message": f"[BLIBLI] 📄 Page {page_num}/{pages}: Scrolling..."
                })
                await scroll_page_gradually_async(page, steps=8, delay=2.0)

                # Parse products
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
                    send_ws_message(job_id, "status", {
                        "message": "[BLIBLI] Menunggu sebelum page berikutnya..."
                    })
                    await asyncio.sleep(6)

            # Handle missing sellers
            _fill_missing_sellers(all_products, mode, job_id)

            return all_products

    try:
        all_products = asyncio.run(_scrape())
    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[BLIBLI] Camoufox error: {str(e)[:100]}"
        })
        return None

    return _export_results(all_products, keyword, filters, job_id)


# ============================================================
# CLOAKBROWSER ENGINE (Chrome-based, C++ patches)
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
    Consider using Camoufox instead.
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
                        "message": "[BLIBLI] Challenge tidak bisa dilewati. Gunakan Camoufox."
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
