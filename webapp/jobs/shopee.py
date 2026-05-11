"""
Shopee scraping job runner.
Uses undetected-chromedriver with network intercept (CDP) for API data extraction.
Supports Camoufox as alternative engine.
"""
import os
import sys
import time
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from webapp.jobs.base import (
    BrowserEngine,
    send_ws_message,
    wait_for_confirmation,
    detect_challenge,
    scroll_page_gradually,
    scroll_page_gradually_async,
)
from webapp.parsers.shopee import parse_api_items, extract_via_js_script

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PROFILE_DIR = str(PROJECT_ROOT / "scrapers" / "shopee_profile")


def build_shopee_url(keyword: str, page: int, filters: dict) -> str:
    """Build Shopee search URL with filters.

    Args:
        keyword: Search keyword
        page: Page number (0-based)
        filters: Dict with optional keys: min_price, max_price, rating, sort
    """
    keyword_encoded = quote_plus(keyword)
    url = f"https://shopee.co.id/search?keyword={keyword_encoded}"
    if page > 0:
        url += f"&page={page}"
    if filters.get("min_price"):
        url += f"&minPrice={filters['min_price']}"
    if filters.get("max_price"):
        url += f"&maxPrice={filters['max_price']}"
    if filters.get("rating"):
        url += f"&ratingFilter={filters['rating']}"
    if filters.get("sort"):
        url += f"&sortBy={filters['sort']}"
    return url


def run_shopee_job(job_id: str, keyword: str, pages: int, mode: str,
                   filters: dict, engine: BrowserEngine = BrowserEngine.UNDETECTED_CHROME):
    """Run Shopee scraping job.

    Args:
        job_id: Unique job identifier for WebSocket messaging
        keyword: Search keyword
        pages: Number of pages to scrape
        mode: 'cepat' (fast) or 'lengkap' (complete)
        filters: Search filters dict
        engine: Browser engine to use

    Returns:
        dict with 'total' and 'file' keys, or None on failure
    """
    if engine == BrowserEngine.CAMOUFOX:
        return _run_with_camoufox(job_id, keyword, pages, mode, filters)
    else:
        return _run_with_uc(job_id, keyword, pages, mode, filters)


# ============================================================
# CAMOUFOX ENGINE (Firefox-based, recommended for anti-detection)
# ============================================================

def _run_with_camoufox(job_id, keyword, pages, mode, filters):
    """Run Shopee scraping using Camoufox with network intercept via Playwright."""
    from exporters.excel_analytics import export_with_analytics

    send_ws_message(job_id, "status", {
        "message": "[SHOPEE] 🦊 Membuka Camoufox (Firefox anti-detection)..."
    })

    async def _scrape():
        from camoufox.async_api import AsyncCamoufox

        async with AsyncCamoufox(headless=False) as browser:
            all_products = []
            page = await browser.new_page()

            # Intercept API responses
            api_responses = []

            async def handle_response(response):
                url = response.url
                if "search_items" in url or "search/search_items" in url:
                    try:
                        body = await response.json()
                        items = parse_api_items(body)
                        api_responses.extend(items)
                    except Exception:
                        pass

            page.on("response", handle_response)

            # Login check - navigate to Shopee first
            await page.goto("https://shopee.co.id/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)

            # Check if login needed
            html = await page.content()
            if "buyer/login" in page.url or "login" in html.lower()[:500]:
                send_ws_message(job_id, "need_action", {
                    "message": "[SHOPEE] Login diperlukan. Silakan login di browser, lalu klik 'Konfirmasi'.",
                    "action": "login_shopee",
                })
                if not wait_for_confirmation(job_id, 600):
                    send_ws_message(job_id, "error", {"message": "[SHOPEE] Timeout login."})
                    return []
                send_ws_message(job_id, "progress", {"message": "[SHOPEE] ✓ Login berhasil!"})
                await asyncio.sleep(3)

            # Scraping loop
            for page_num in range(pages):
                url = build_shopee_url(keyword, page_num, filters)
                api_responses.clear()

                send_ws_message(job_id, "progress", {
                    "message": f"[SHOPEE] 📄 Page {page_num + 1}/{pages}: Memuat halaman...",
                    "page": page_num + 1,
                })

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(8)

                # Check CAPTCHA
                if page_num == 0:
                    html = await page.content()
                    if detect_challenge(html, page.url):
                        send_ws_message(job_id, "need_action", {
                            "message": "[SHOPEE] CAPTCHA terdeteksi! Selesaikan di browser, lalu klik 'Konfirmasi'.",
                            "action": "solve_captcha",
                        })
                        if not wait_for_confirmation(job_id, 300):
                            send_ws_message(job_id, "error", {"message": "[SHOPEE] Timeout CAPTCHA."})
                            break
                        send_ws_message(job_id, "progress", {"message": "[SHOPEE] ✓ CAPTCHA berhasil!"})
                        await asyncio.sleep(3)
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(8)

                # Scroll to trigger API calls
                send_ws_message(job_id, "status", {
                    "message": f"[SHOPEE] 📄 Page {page_num + 1}/{pages}: Scrolling & intercept API..."
                })
                await scroll_page_gradually_async(page, steps=6, delay=2.0)

                # Collect from intercepted API
                page_products = list(api_responses)

                # Fallback: JS DOM extraction
                if not page_products:
                    send_ws_message(job_id, "status", {
                        "message": "[SHOPEE] ⚠️ API kosong, mencoba DOM extraction..."
                    })
                    js_script = extract_via_js_script()
                    page_products = await page.evaluate(js_script) or []

                all_products.extend(page_products)
                send_ws_message(job_id, "progress", {
                    "message": f"[SHOPEE] ✅ Page {page_num + 1}/{pages}: {len(page_products)} produk "
                               f"(Total: {len(all_products)})",
                    "products": len(all_products),
                })

                if page_num < pages - 1:
                    send_ws_message(job_id, "status", {
                        "message": "[SHOPEE] Menunggu sebelum page berikutnya..."
                    })
                    await asyncio.sleep(5)

            return all_products

    try:
        all_products = asyncio.run(_scrape())
    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[SHOPEE] Camoufox error: {str(e)[:100]}"
        })
        return None

    return _export_results(all_products, keyword, filters, job_id)


# ============================================================
# UNDETECTED-CHROMEDRIVER ENGINE (Current default)
# ============================================================

def _run_with_uc(job_id, keyword, pages, mode, filters):
    """Run Shopee scraping using undetected-chromedriver + CDP network intercept."""
    import undetected_chromedriver as uc
    import json as json_mod
    from exporters.excel_analytics import export_with_analytics

    # Kill existing Chrome to avoid profile lock
    send_ws_message(job_id, "status", {
        "message": "[SHOPEE] Menutup Chrome yang aktif (menghindari profile lock)..."
    })
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"],
                       capture_output=True, timeout=10)
        time.sleep(3)
    except Exception:
        pass

    # Check if profile has valid login
    os.makedirs(PROFILE_DIR, exist_ok=True)
    cookies_file = os.path.join(PROFILE_DIR, "Default", "Cookies")
    first_time = not os.path.exists(cookies_file)

    if first_time:
        send_ws_message(job_id, "status", {
            "message": "[SHOPEE] Belum ada session login. Memulai proses login..."
        })
    else:
        send_ws_message(job_id, "status", {
            "message": "[SHOPEE] Session ditemukan. Membuka Chrome..."
        })

    # Open Chrome with profile
    send_ws_message(job_id, "progress", {"message": "[SHOPEE] Membuka Chrome browser..."})
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    try:
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=147)
    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[SHOPEE] Gagal buka Chrome: {str(e)[:50]}"
        })
        return None

    driver.set_page_load_timeout(90)
    all_products = []

    try:
        # Login flow (only if first time)
        if first_time:
            driver = _handle_shopee_login(job_id, driver, uc)
            if driver is None:
                return None

        # Scraping loop
        send_ws_message(job_id, "progress", {
            "message": "[SHOPEE] [Step 2/2] Memulai scraping..."
        })

        for page_num in range(pages):
            url = build_shopee_url(keyword, page_num, filters)

            send_ws_message(job_id, "progress", {
                "message": f"[SHOPEE] 📄 Page {page_num + 1}/{pages}: Memuat halaman...",
                "page": page_num + 1,
            })

            # Clear performance logs before navigation
            try:
                driver.get_log("performance")
            except Exception:
                pass

            # Navigate
            try:
                driver.get(url)
            except Exception:
                send_ws_message(job_id, "status", {
                    "message": "[SHOPEE] ⚠️ Navigate timeout, menunggu..."
                })
                time.sleep(5)

            time.sleep(10)

            # Check CAPTCHA on first page
            if page_num == 0:
                page_src = driver.page_source
                current_url = driver.current_url
                if detect_challenge(page_src, current_url):
                    send_ws_message(job_id, "need_action", {
                        "message": "[SHOPEE] CAPTCHA terdeteksi! Selesaikan puzzle, lalu klik 'Konfirmasi'.",
                        "action": "solve_captcha",
                    })
                    if not wait_for_confirmation(job_id, 300):
                        send_ws_message(job_id, "error", {
                            "message": "[SHOPEE] Timeout CAPTCHA (5 menit)."
                        })
                        break
                    send_ws_message(job_id, "progress", {
                        "message": "[SHOPEE] ✓ CAPTCHA berhasil! Melanjutkan..."
                    })
                    time.sleep(3)
                    try:
                        driver.get_log("performance")
                        driver.get(url)
                        time.sleep(10)
                    except Exception:
                        pass
                else:
                    send_ws_message(job_id, "progress", {
                        "message": "[SHOPEE] ✓ Tidak ada CAPTCHA. Lanjut scraping..."
                    })

            # Scroll to trigger API calls
            send_ws_message(job_id, "status", {
                "message": f"[SHOPEE] 📄 Page {page_num + 1}/{pages}: Scrolling & intercept API..."
            })
            try:
                for i in range(6):
                    driver.execute_script(
                        f"window.scrollTo(0, document.body.scrollHeight * {(i+1)*16}/100);"
                    )
                    time.sleep(2)
                time.sleep(5)
            except Exception:
                pass

            # Extract from network logs (CDP)
            send_ws_message(job_id, "status", {
                "message": f"[SHOPEE] 📄 Page {page_num + 1}/{pages}: Extracting data dari network..."
            })
            page_products = _extract_from_network(driver)

            # Fallback: JS DOM extraction
            if not page_products:
                send_ws_message(job_id, "status", {
                    "message": "[SHOPEE] ⚠️ Network kosong, mencoba JS DOM extraction..."
                })
                page_products = _extract_via_js(driver)

            all_products.extend(page_products)
            send_ws_message(job_id, "progress", {
                "message": f"[SHOPEE] ✅ Page {page_num + 1}/{pages}: {len(page_products)} produk "
                           f"(Total: {len(all_products)})",
                "products": len(all_products),
            })

            if page_num < pages - 1:
                send_ws_message(job_id, "status", {
                    "message": "[SHOPEE] Menunggu sebelum page berikutnya..."
                })
                time.sleep(5)

    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[SHOPEE] Error: {str(e)[:80]}"
        })
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return _export_results(all_products, keyword, filters, job_id)


# ============================================================
# HELPERS
# ============================================================

def _handle_shopee_login(job_id, driver, uc):
    """Handle Shopee login flow. Returns driver or None on failure."""
    send_ws_message(job_id, "progress", {
        "message": "[SHOPEE] [Step 1/2] Membuka halaman login Shopee..."
    })
    try:
        driver.get("https://shopee.co.id/buyer/login")
    except Exception:
        pass
    time.sleep(5)

    send_ws_message(job_id, "need_action", {
        "message": "[SHOPEE] [Step 1/2] Login di browser yang terbuka:\n"
                   "1. Pilih metode login (Google / SMS / QR Code / Password)\n"
                   "2. Selesaikan proses login\n"
                   "3. Jika ada CAPTCHA, selesaikan puzzle verifikasi\n"
                   "4. Tunggu sampai masuk ke halaman utama Shopee\n\n"
                   "Klik 'Konfirmasi' setelah berhasil masuk ke Shopee.",
        "action": "login_shopee",
    })
    if not wait_for_confirmation(job_id, 600):
        send_ws_message(job_id, "error", {"message": "[SHOPEE] Timeout login (10 menit)."})
        driver.quit()
        return None

    send_ws_message(job_id, "progress", {"message": "[SHOPEE] [Step 1/2] Login berhasil! ✓"})
    time.sleep(2)

    # Verify session
    send_ws_message(job_id, "status", {
        "message": "[SHOPEE] Memverifikasi session & menyimpan cookies..."
    })
    try:
        driver.switch_to.window(driver.window_handles[0])
    except Exception:
        pass
    try:
        driver.get("https://shopee.co.id/")
    except Exception:
        pass
    time.sleep(5)

    cookies = driver.get_cookies()
    shopee_cookies = [c["name"] for c in cookies if "SPC" in c.get("name", "")]
    if shopee_cookies:
        send_ws_message(job_id, "progress", {
            "message": f"[SHOPEE] ✓ Cookies tersimpan: {', '.join(shopee_cookies[:3])}"
        })
    else:
        send_ws_message(job_id, "status", {
            "message": "[SHOPEE] ⚠️ Cookies belum terdeteksi, tetap lanjut..."
        })
    time.sleep(2)

    # Restart browser with saved session
    send_ws_message(job_id, "status", {
        "message": "[SHOPEE] Restart browser dengan session tersimpan..."
    })
    try:
        driver.quit()
    except Exception:
        pass
    time.sleep(3)

    options2 = uc.ChromeOptions()
    options2.add_argument("--start-maximized")
    options2.add_argument("--no-sandbox")
    options2.add_argument("--disable-dev-shm-usage")
    options2.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options2.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    try:
        driver = uc.Chrome(options=options2, use_subprocess=True, version_main=147)
        driver.set_page_load_timeout(90)
    except Exception as e:
        send_ws_message(job_id, "error", {
            "message": f"[SHOPEE] Gagal restart Chrome: {str(e)[:50]}"
        })
        return None

    send_ws_message(job_id, "progress", {
        "message": "[SHOPEE] ✓ Browser siap dengan session login."
    })
    time.sleep(2)
    return driver


def _extract_from_network(driver) -> list:
    """Extract Shopee products from intercepted network API responses (CDP)."""
    import json as json_mod
    products = []

    try:
        logs = driver.get_log("performance")
    except Exception:
        return []

    for entry in logs:
        try:
            log_data = json_mod.loads(entry["message"])
            message = log_data.get("message", {})

            if message.get("method") == "Network.responseReceived":
                response = message.get("params", {}).get("response", {})
                url = response.get("url", "")

                if "search_items" in url or "search/search_items" in url:
                    request_id = message.get("params", {}).get("requestId")
                    if request_id:
                        try:
                            body = driver.execute_cdp_cmd(
                                "Network.getResponseBody", {"requestId": request_id}
                            )
                            if body and body.get("body"):
                                data = json_mod.loads(body["body"])
                                items = parse_api_items(data)
                                products.extend(items)
                        except Exception:
                            pass
        except Exception:
            continue

    return products


def _extract_via_js(driver) -> list:
    """Fallback: Extract products via JavaScript DOM."""
    try:
        js_script = extract_via_js_script()
        products = driver.execute_script(js_script)
        return products or []
    except Exception:
        return []


def _export_results(products: list, keyword: str, filters: dict, job_id: str):
    """Export scraped products to Excel with analytics."""
    if not products:
        return None

    from exporters.excel_analytics import export_with_analytics

    send_ws_message(job_id, "status", {
        "message": f"[SHOPEE] Mengexport {len(products)} produk ke Excel..."
    })
    hasil_dir = str(PROJECT_ROOT / "hasil" / "shopee")
    filepath = export_with_analytics(products, keyword, filters, output_dir=hasil_dir)
    return {"total": len(products), "file": os.path.basename(filepath)}
