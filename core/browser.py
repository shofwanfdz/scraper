"""
Browser Engine (Playwright-based with CloakBrowser fallback)
For scraping JavaScript-heavy / dynamic websites.
Auto-fallback to CloakBrowser if anti-bot detection is detected.
"""
import asyncio
import random
from typing import Optional, Any, List

from loguru import logger

from config.settings import SCRAPING, DEFAULT_USER_AGENTS


class BrowserEngine:
    """
    Headless browser engine using Playwright for dynamic content scraping.
    Handles JavaScript rendering, infinite scroll, and complex interactions.

    Auto-fallback to CloakBrowser (C++ anti-detection) when stock Playwright
    is blocked by anti-bot systems (Cloudflare, challenge pages, etc.).
    """

    def __init__(self, headless: bool = True, force_cloak: bool = False):
        self.headless = headless
        self.force_cloak = force_cloak
        self.browser = None
        self.context = None
        self._playwright = None
        self._using_cloak = False
        self._fallback_triggered = False

    async def start(self):
        """Launch the browser, auto-fallback to CloakBrowser if blocked."""
        # Option: force CloakBrowser from the start
        if self.force_cloak:
            await self._start_cloak()
            return

        # Try stock Playwright first
        try:
            await self._start_playwright()
            logger.info("Browser engine started (stock Playwright)")
            return
        except Exception as e:
            logger.warning(f"Stock Playwright failed: {str(e)[:80]}, trying CloakBrowser...")
            self._fallback_triggered = True

        # Fallback to CloakBrowser (C++ anti-detection patches)
        try:
            await self._start_cloak()
        except Exception as e:
            logger.error(f"CloakBrowser also failed: {e}")
            raise RuntimeError(
                f"Both browsers failed. Playwright error: {e}"
            ) from e

    def detect_blocked(self, page_url: str) -> bool:
        """Check if page was blocked by anti-bot (challenge/verify redirect)."""
        blocked_patterns = ["challenge", "verify", "blocked", "captcha", "/landing/"]
        return any(p in page_url.lower() for p in blocked_patterns)

    async def _start_playwright(self):
        """Start stock Playwright browser."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--disable-extensions",
            ],
        )

        # Create context with realistic settings
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(DEFAULT_USER_AGENTS),
            locale="en-US",
            timezone_id="Asia/Jakarta",
            permissions=["geolocation"],
            java_script_enabled=True,
        )

        # Add stealth scripts to avoid detection
        await self.context.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override chrome detection
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );

            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'id']
            });
        """)

        self._using_cloak = False

    async def _start_cloak(self):
        """Start CloakBrowser (C++ anti-detection patches)."""
        import cloakbrowser

        self.browser = await cloakbrowser.launch_async(
            headless=self.headless,
            geoip=True,
        )
        # CloakBrowser doesn't use Playwright's context model.
        # Wrap it with a compat layer so self.context.new_page() works.
        self._cloak_page_pool: List[Any] = []
        self._using_cloak = True

        # Create a fake context that mimics Playwright's context API
        class CloakContextCompat:
            """Compatibility layer: Playwright context API → CloakBrowser."""
            def __init__(inner_self, browser):
                inner_self._browser = browser
                inner_self._pages: List[Any] = []

            async def new_page(inner_self):
                page = await inner_self._browser.new_page()
                inner_self._pages.append(page)
                return page

            async def close(inner_self):
                for p in inner_self._pages:
                    try:
                        await p.close()
                    except Exception:
                        pass
                inner_self._pages.clear()

        self.context = CloakContextCompat(self.browser)
        logger.info("Browser engine started (CloakBrowser - anti-detection)")

    async def stop(self):
        """Close the browser (handles both Playwright and CloakBrowser)."""
        if self._using_cloak:
            # CloakBrowser cleanup
            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass
            if self.browser:
                await self.browser.close()
            self._playwright = None
        else:
            # Stock Playwright cleanup
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
        self.browser = None
        self.context = None
        logger.info("Browser engine stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def new_page(self):
        """Create a new browser page"""
        if not self.context:
            await self.start()
        page = await self.context.new_page()

        # Block unnecessary resources for speed (Playwright only)
        if not self._using_cloak:
            try:
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot}",
                    lambda route: route.abort(),
                )
            except Exception:
                pass  # Skip if route not supported

        return page

    async def fetch_rendered(self, url: str, wait_for: str = "networkidle") -> Optional[str]:
        """
        Fetch a page with full JavaScript rendering.

        Auto-retry with CloakBrowser if stock Playwright detects anti-bot blocking.

        Args:
            url: Target URL
            wait_for: Wait condition ('networkidle', 'load', 'domcontentloaded')

        Returns:
            Rendered HTML content
        """
        page = await self.new_page()
        try:
            await page.goto(url, wait_until=wait_for, timeout=30000)

            # Random delay to appear more human
            await asyncio.sleep(random.uniform(1, 3))

            # Check if blocked by anti-bot (content-level detection)
            if not self._using_cloak and not self.force_cloak:
                content = await page.content()
                if self._detect_blocked_content(content):
                    logger.warning("Anti-bot detected on page, retrying with CloakBrowser...")
                    await page.close()

                    # Restart with CloakBrowser
                    await self.stop()
                    self.force_cloak = True
                    await self._start_cloak()
                    page = await self.context.new_page()
                    await page.goto(url, wait_until=wait_for, timeout=30000)
                    await asyncio.sleep(random.uniform(2, 4))
                    content = await page.content()
                    if self._detect_blocked_content(content):
                        logger.error(f"Even CloakBrowser blocked for {url}")
                    else:
                        logger.info(f"CloakBrowser succeeded for {url}")
                    return content

            content = await page.content()
            return content

        except Exception as e:
            logger.error(f"Browser fetch error for {url}: {e}")
            return None
        finally:
            await page.close()

    def _detect_blocked_content(self, html_content: str) -> bool:
        """Detect anti-bot challenge page from HTML content."""
        blocked_indicators = [
            "cloudflare", "challenge", "checking your browser",
            "please wait", "redirecting", "/landing/",
            "cf-challenge", "_cf_chl", "RayID",
        ]
        content_lower = html_content.lower()
        return any(ind in content_lower for ind in blocked_indicators)

    async def fetch_with_scroll(
        self,
        url: str,
        scroll_count: int = 5,
        scroll_delay: float = 2.0,
    ) -> Optional[str]:
        """
        Fetch a page with infinite scroll handling.

        Args:
            url: Target URL
            scroll_count: Number of times to scroll
            scroll_delay: Delay between scrolls

        Returns:
            Rendered HTML after scrolling
        """
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            for i in range(scroll_count):
                # Scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(scroll_delay + random.uniform(0.5, 1.5))

                # Check if new content loaded
                new_height = await page.evaluate("document.body.scrollHeight")
                logger.debug(f"Scroll {i+1}/{scroll_count}, page height: {new_height}")

            content = await page.content()
            return content

        except Exception as e:
            logger.error(f"Browser scroll error for {url}: {e}")
            return None
        finally:
            await page.close()

    async def screenshot(self, url: str, path: str = "screenshot.png"):
        """Take a screenshot of a page (useful for debugging)"""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle")
            await page.screenshot(path=path, full_page=True)
            logger.info(f"Screenshot saved: {path}")
        finally:
            await page.close()

    async def execute_script(self, url: str, script: str) -> Any:
        """Execute custom JavaScript on a page"""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle")
            result = await page.evaluate(script)
            return result
        finally:
            await page.close()
