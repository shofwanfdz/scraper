"""
Browser Engine (Playwright-based)
For scraping JavaScript-heavy / dynamic websites
"""
import asyncio
import random
from typing import Optional, Dict, Any, List

from loguru import logger

from config.settings import SCRAPING, DEFAULT_USER_AGENTS


class BrowserEngine:
    """
    Headless browser engine using Playwright for dynamic content scraping.
    Handles JavaScript rendering, infinite scroll, and complex interactions.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.context = None
        self._playwright = None

    async def start(self):
        """Launch the browser"""
        try:
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

            logger.info("Browser engine started (headless={})".format(self.headless))

        except ImportError:
            logger.error(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )
            raise

    async def stop(self):
        """Close the browser"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
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

        # Block unnecessary resources for speed
        await page.route(
            "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )

        return page

    async def fetch_rendered(self, url: str, wait_for: str = "networkidle") -> Optional[str]:
        """
        Fetch a page with full JavaScript rendering.

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

            content = await page.content()
            return content

        except Exception as e:
            logger.error(f"Browser fetch error for {url}: {e}")
            return None
        finally:
            await page.close()

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
