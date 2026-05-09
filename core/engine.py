"""
Core Scraping Engine - The heart of the scraping tools
Handles HTTP requests, browser automation, and orchestration
"""
import asyncio
import random
import time
from typing import Optional, Dict, Any, List, Callable
from urllib.parse import urlparse, urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import SCRAPING, DEFAULT_USER_AGENTS
from .anti_detection import AntiDetection
from .proxy_manager import ProxyManager
from .rate_limiter import RateLimiter
from .robots_parser import RobotsParser


class ScrapingEngine:
    """
    Main scraping engine that orchestrates all scraping operations.
    Supports both HTTP-based and browser-based scraping.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or SCRAPING
        self.anti_detection = AntiDetection()
        self.proxy_manager = ProxyManager()
        self.rate_limiter = RateLimiter(
            delay_min=self.config["delay_min"],
            delay_max=self.config["delay_max"],
            max_concurrent=self.config["max_concurrent"],
        )
        self.robots_parser = RobotsParser()
        self.session: Optional[httpx.AsyncClient] = None
        self._request_count = 0
        self._success_count = 0
        self._fail_count = 0
        logger.info("ScrapingEngine initialized")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        """Initialize the HTTP client session"""
        self.session = httpx.AsyncClient(
            timeout=self.config["timeout"],
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self.config["max_concurrent"],
                max_keepalive_connections=5,
            ),
        )
        logger.info("ScrapingEngine started")

    async def stop(self):
        """Close the HTTP client session"""
        if self.session:
            await self.session.aclose()
            self.session = None
        logger.info(
            f"ScrapingEngine stopped. "
            f"Requests: {self._request_count}, "
            f"Success: {self._success_count}, "
            f"Failed: {self._fail_count}"
        )

    def _get_headers(self) -> Dict[str, str]:
        """Generate randomized request headers"""
        return self.anti_detection.get_headers()

    async def check_robots(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt"""
        if not self.config.get("respect_robots_txt", True):
            return True
        return await self.robots_parser.is_allowed(url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        use_proxy: bool = False,
    ) -> Optional[httpx.Response]:
        """
        Fetch a URL with anti-detection measures.

        Args:
            url: Target URL
            method: HTTP method (GET, POST, etc.)
            headers: Custom headers (merged with anti-detection headers)
            params: Query parameters
            data: Form data
            json_data: JSON body
            use_proxy: Whether to use proxy rotation

        Returns:
            httpx.Response or None if failed
        """
        # Check robots.txt
        if not await self.check_robots(url):
            logger.warning(f"URL blocked by robots.txt: {url}")
            return None

        # Rate limiting
        await self.rate_limiter.wait()

        # Prepare headers
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)

        # Prepare proxy
        proxy = None
        if use_proxy:
            proxy = self.proxy_manager.get_proxy()

        self._request_count += 1

        try:
            if not self.session:
                await self.start()

            response = await self.session.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                data=data,
                json=json_data,
            )

            # Check for blocking indicators
            if response.status_code == 403:
                logger.warning(f"403 Forbidden: {url} - Possible block detected")
                self._fail_count += 1
                raise httpx.HTTPStatusError(
                    "Blocked", request=response.request, response=response
                )
            elif response.status_code == 429:
                logger.warning(f"429 Too Many Requests: {url} - Rate limited")
                self._fail_count += 1
                await asyncio.sleep(random.uniform(5, 15))
                raise httpx.HTTPStatusError(
                    "Rate limited", request=response.request, response=response
                )
            elif response.status_code >= 400:
                logger.warning(f"HTTP {response.status_code}: {url}")
                self._fail_count += 1
                return None

            self._success_count += 1
            logger.debug(f"Successfully fetched: {url} ({response.status_code})")
            return response

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching: {url}")
            self._fail_count += 1
            raise
        except httpx.ConnectError as e:
            logger.error(f"Connection error for {url}: {e}")
            self._fail_count += 1
            raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self._fail_count += 1
            raise

    async def fetch_html(self, url: str, **kwargs) -> Optional[str]:
        """Fetch URL and return HTML content"""
        response = await self.fetch(url, **kwargs)
        if response:
            return response.text
        return None

    async def fetch_json(self, url: str, **kwargs) -> Optional[Dict]:
        """Fetch URL and return JSON content"""
        response = await self.fetch(url, **kwargs)
        if response:
            return response.json()
        return None

    def parse_html(self, html: str, parser: str = "lxml") -> BeautifulSoup:
        """Parse HTML content with BeautifulSoup"""
        return BeautifulSoup(html, parser)

    async def scrape_page(
        self,
        url: str,
        extract_fn: Callable[[BeautifulSoup], Any],
        **kwargs,
    ) -> Optional[Any]:
        """
        Scrape a single page and extract data using provided function.

        Args:
            url: Target URL
            extract_fn: Function that takes BeautifulSoup and returns extracted data
            **kwargs: Additional arguments for fetch()

        Returns:
            Extracted data or None
        """
        html = await self.fetch_html(url, **kwargs)
        if html:
            soup = self.parse_html(html)
            return extract_fn(soup)
        return None

    async def scrape_multiple(
        self,
        urls: List[str],
        extract_fn: Callable[[BeautifulSoup], Any],
        **kwargs,
    ) -> List[Any]:
        """
        Scrape multiple pages concurrently with rate limiting.

        Args:
            urls: List of target URLs
            extract_fn: Extraction function
            **kwargs: Additional arguments for fetch()

        Returns:
            List of extracted data
        """
        semaphore = asyncio.Semaphore(self.config["max_concurrent"])
        results = []

        async def _scrape_one(url: str):
            async with semaphore:
                result = await self.scrape_page(url, extract_fn, **kwargs)
                if result:
                    results.append(result)

        tasks = [_scrape_one(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Scraped {len(results)}/{len(urls)} pages successfully")
        return results

    @property
    def stats(self) -> Dict[str, int]:
        """Get scraping statistics"""
        return {
            "total_requests": self._request_count,
            "successful": self._success_count,
            "failed": self._fail_count,
            "success_rate": (
                round(self._success_count / self._request_count * 100, 2)
                if self._request_count > 0
                else 0
            ),
        }
