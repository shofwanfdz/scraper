"""
Robots.txt Parser
Respects website crawling rules
"""
import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import httpx
from loguru import logger


class RobotsParser:
    """
    Parses and caches robots.txt files to respect website crawling rules.
    """

    def __init__(self):
        self._cache: Dict[str, RobotFileParser] = {}
        self._user_agent = "*"

    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given page URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    async def _fetch_robots(self, robots_url: str) -> Optional[RobotFileParser]:
        """Fetch and parse a robots.txt file"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
                    return parser
                else:
                    # If robots.txt doesn't exist, allow everything
                    parser = RobotFileParser()
                    parser.allow_all = True
                    return parser
        except Exception as e:
            logger.debug(f"Could not fetch robots.txt from {robots_url}: {e}")
            # On error, be permissive
            parser = RobotFileParser()
            parser.allow_all = True
            return parser

    async def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        """
        Check if a URL is allowed to be scraped according to robots.txt.

        Args:
            url: The URL to check
            user_agent: The user agent to check for

        Returns:
            True if allowed, False if disallowed
        """
        robots_url = self._get_robots_url(url)

        # Check cache
        if robots_url not in self._cache:
            parser = await self._fetch_robots(robots_url)
            if parser:
                self._cache[robots_url] = parser
            else:
                return True  # Allow if we can't fetch robots.txt

        parser = self._cache[robots_url]

        # Check if URL is allowed
        try:
            return parser.can_fetch(user_agent, url)
        except Exception:
            return True  # Allow on error

    def get_crawl_delay(self, url: str, user_agent: str = "*") -> Optional[float]:
        """Get the crawl delay specified in robots.txt"""
        robots_url = self._get_robots_url(url)
        if robots_url in self._cache:
            try:
                delay = self._cache[robots_url].crawl_delay(user_agent)
                return delay
            except Exception:
                return None
        return None

    def clear_cache(self):
        """Clear the robots.txt cache"""
        self._cache.clear()
        logger.debug("Robots.txt cache cleared")
