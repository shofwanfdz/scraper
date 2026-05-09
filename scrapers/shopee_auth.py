"""
Shopee Authentication Manager
Handles login via manual browser session and cookie persistence.

Flow:
1. Open visible Chrome browser → navigate to Shopee login
2. User logs in manually (handles CAPTCHA/OTP themselves)
3. App detects successful login → saves cookies
4. Future scraping sessions load saved cookies (no re-login needed)
5. If cookies expire → prompt user to login again
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

COOKIES_DIR = Path(__file__).parent / "cookies"
COOKIES_FILE = COOKIES_DIR / "shopee_cookies.json"
SHOPEE_LOGIN_URL = "https://shopee.co.id/buyer/login"
SHOPEE_BASE_URL = "https://shopee.co.id"


class ShopeeAuth:
    """Manages Shopee authentication via cookie persistence."""

    def __init__(self):
        COOKIES_DIR.mkdir(exist_ok=True)

    def has_valid_cookies(self) -> bool:
        """Check if saved cookies exist and are not too old."""
        if not COOKIES_FILE.exists():
            return False
        # Check file age (cookies typically valid for 6-24 hours)
        file_age_hours = (time.time() - COOKIES_FILE.stat().st_mtime) / 3600
        if file_age_hours > 12:
            logger.warning("Shopee cookies are {} hours old (may be expired)".format(int(file_age_hours)))
            return False
        return True

    def login_manual(self) -> bool:
        """
        Open a VISIBLE browser for user to login manually.
        Waits for successful login, then saves cookies.
        
        Returns:
            True if login successful, False otherwise
        """
        import undetected_chromedriver as uc

        print("\n" + "=" * 60)
        print("  SHOPEE LOGIN")
        print("=" * 60)
        print("  Browser akan terbuka. Silakan login ke akun Shopee Anda.")
        print("  Setelah berhasil login, tunggu beberapa detik...")
        print("  App akan otomatis mendeteksi login dan menyimpan session.")
        print("=" * 60)

        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # VISIBLE browser (not headless) so user can login manually
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=147)
        driver.set_page_load_timeout(60)

        try:
            # Navigate to login page
            driver.get(SHOPEE_LOGIN_URL)
            print("\n[*] Browser terbuka. Silakan login...")
            print("[*] Menunggu login berhasil (max 5 menit)...")

            # Wait for user to login (check every 3 seconds, max 5 minutes)
            max_wait = 300  # 5 minutes
            elapsed = 0
            logged_in = False

            while elapsed < max_wait:
                time.sleep(3)
                elapsed += 3

                # Check if user is logged in by looking at URL or page content
                current_url = driver.current_url

                # If redirected away from login page = success
                if "buyer/login" not in current_url and "shopee.co.id" in current_url:
                    logged_in = True
                    break

                # Also check for user avatar/account element
                try:
                    page_source = driver.page_source
                    if "shopee-avatar" in page_source or "navbar__username" in page_source:
                        logged_in = True
                        break
                except Exception:
                    pass

                # Print progress every 15 seconds
                if elapsed % 15 == 0:
                    print("    Menunggu... ({} detik)".format(elapsed))

            if logged_in:
                # Wait a bit more for all cookies to be set
                time.sleep(3)

                # Navigate to main page to ensure all cookies are loaded
                driver.get(SHOPEE_BASE_URL)
                time.sleep(3)

                # Save cookies
                cookies = driver.get_cookies()
                self._save_cookies(cookies)
                print("\n[+] Login berhasil! Cookies tersimpan.")
                print("[+] Session valid untuk ~12 jam ke depan.")
                return True
            else:
                print("\n[!] Timeout - login tidak terdeteksi dalam 5 menit.")
                return False

        except Exception as e:
            print("\n[!] Error: {}".format(str(e)[:60]))
            return False
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def load_cookies_to_driver(self, driver) -> bool:
        """
        Load saved cookies into an existing driver session.
        
        Args:
            driver: Active Chrome driver instance
            
        Returns:
            True if cookies loaded successfully
        """
        if not COOKIES_FILE.exists():
            logger.warning("No saved Shopee cookies found")
            return False

        try:
            cookies = self._load_cookies()
            if not cookies:
                return False

            # Navigate to Shopee first (cookies need matching domain)
            driver.get(SHOPEE_BASE_URL)
            time.sleep(3)

            # Add each cookie
            for cookie in cookies:
                try:
                    # Remove problematic fields
                    cookie.pop("sameSite", None)
                    cookie.pop("storeId", None)
                    if "expiry" in cookie:
                        cookie["expiry"] = int(cookie["expiry"])
                    driver.add_cookie(cookie)
                except Exception:
                    pass

            # Refresh to apply cookies
            driver.refresh()
            time.sleep(3)

            # Verify login status
            if self._verify_login(driver):
                logger.info("Shopee cookies loaded successfully - logged in")
                return True
            else:
                logger.warning("Shopee cookies loaded but login not verified")
                return False

        except Exception as e:
            logger.error("Error loading cookies: {}".format(str(e)[:60]))
            return False

    def _verify_login(self, driver) -> bool:
        """Check if the current session is logged in."""
        try:
            page_source = driver.page_source
            # Check for logged-in indicators
            if any(indicator in page_source for indicator in [
                "shopee-avatar", "navbar__username", "stardust-dropdown",
                "account-info", "user-panel"
            ]):
                return True
            # Check URL - if on login page, not logged in
            if "buyer/login" in driver.current_url:
                return False
            return True  # Assume logged in if not on login page
        except Exception:
            return False

    def _save_cookies(self, cookies: list):
        """Save cookies to JSON file."""
        data = {
            "cookies": cookies,
            "saved_at": datetime.now().isoformat(),
            "expires_hint": "~12 hours from saved_at",
        }
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info("Shopee cookies saved ({} cookies)".format(len(cookies)))

    def _load_cookies(self) -> list:
        """Load cookies from JSON file."""
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("cookies", [])
        except Exception as e:
            logger.error("Error reading cookies: {}".format(str(e)[:40]))
            return []

    def clear_cookies(self):
        """Delete saved cookies (force re-login)."""
        if COOKIES_FILE.exists():
            COOKIES_FILE.unlink()
            logger.info("Shopee cookies cleared")
