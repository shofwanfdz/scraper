"""
Anti-Detection System
Handles User-Agent rotation, header randomization, and fingerprint evasion
"""
import random
from typing import Dict, List, Optional

from loguru import logger

from config.settings import DEFAULT_USER_AGENTS


class AntiDetection:
    """
    Anti-detection measures to avoid being blocked by target websites.
    Implements header rotation, realistic browser fingerprinting, and more.
    """

    # Common Accept-Language values
    ACCEPT_LANGUAGES = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.9",
        "en-US,en;q=0.9,id;q=0.8",
        "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "en-US,en;q=0.9,ja;q=0.8",
    ]

    # Common Accept headers
    ACCEPT_HEADERS = [
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    ]

    # Common Sec-CH-UA values (Client Hints)
    SEC_CH_UA = [
        '"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="99"',
        '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        '"Firefox";v="126", "Not-A.Brand";v="99"',
    ]

    # Platform hints
    SEC_CH_UA_PLATFORM = ['"Windows"', '"macOS"', '"Linux"']

    def __init__(self, user_agents: Optional[List[str]] = None):
        self.user_agents = user_agents or DEFAULT_USER_AGENTS
        self._request_count = 0

    def get_random_user_agent(self) -> str:
        """Get a random User-Agent string"""
        return random.choice(self.user_agents)

    def get_headers(self) -> Dict[str, str]:
        """
        Generate a complete set of realistic browser headers.
        Rotates values to avoid fingerprinting.
        """
        user_agent = self.get_random_user_agent()
        is_chrome = "Chrome" in user_agent
        is_firefox = "Firefox" in user_agent

        headers = {
            "User-Agent": user_agent,
            "Accept": random.choice(self.ACCEPT_HEADERS),
            "Accept-Language": random.choice(self.ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

        # Add Chrome-specific headers
        if is_chrome:
            headers.update({
                "Sec-CH-UA": random.choice(self.SEC_CH_UA),
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": random.choice(self.SEC_CH_UA_PLATFORM),
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            })

        # Add Firefox-specific headers
        if is_firefox:
            headers.update({
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "DNT": "1",
            })

        self._request_count += 1
        return headers

    def get_referer(self, url: str) -> str:
        """Generate a realistic referer for the given URL"""
        referers = [
            "https://www.google.com/",
            "https://www.google.co.id/",
            "https://www.bing.com/",
            "https://duckduckgo.com/",
            "",  # Sometimes no referer is more natural
        ]
        return random.choice(referers)

    def should_add_referer(self) -> bool:
        """Randomly decide whether to include a referer (more natural)"""
        return random.random() > 0.3  # 70% chance to include referer

    @staticmethod
    def is_honeypot(element) -> bool:
        """
        Detect if an HTML element is a honeypot trap.
        Checks for hidden elements that only bots would interact with.
        """
        if not element:
            return False

        # Check inline styles
        style = element.get("style", "")
        if any(prop in style.lower() for prop in [
            "display:none", "display: none",
            "visibility:hidden", "visibility: hidden",
            "opacity:0", "opacity: 0",
            "position:absolute", "left:-9999",
            "height:0", "width:0",
        ]):
            return True

        # Check CSS classes that suggest hidden content
        classes = element.get("class", [])
        if isinstance(classes, list):
            classes = " ".join(classes)
        hidden_indicators = ["hidden", "invisible", "d-none", "hide", "trap", "honeypot"]
        if any(indicator in classes.lower() for indicator in hidden_indicators):
            return True

        # Check aria-hidden attribute
        if element.get("aria-hidden") == "true":
            return True

        return False

    @staticmethod
    def filter_honeypots(elements: list) -> list:
        """Filter out honeypot elements from a list"""
        return [el for el in elements if not AntiDetection.is_honeypot(el)]
