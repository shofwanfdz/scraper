"""
Proxy Manager
Handles proxy rotation, health checking, and pool management
"""
import random
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from loguru import logger

from config.settings import PROXY


@dataclass
class ProxyInfo:
    """Proxy information container"""
    url: str
    protocol: str = "http"
    username: Optional[str] = None
    password: Optional[str] = None
    last_used: float = 0
    fail_count: int = 0
    success_count: int = 0
    is_active: bool = True

    @property
    def full_url(self) -> str:
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.url}"
        return f"{self.protocol}://{self.url}"

    @property
    def success_rate(self) -> float:
        total = self.fail_count + self.success_count
        if total == 0:
            return 1.0
        return self.success_count / total


class ProxyManager:
    """
    Manages a pool of proxies with rotation, health checking, and failover.
    """

    MAX_FAILS = 5  # Max failures before deactivating a proxy

    def __init__(self, proxies: Optional[List[str]] = None):
        self.proxy_pool: List[ProxyInfo] = []
        self._current_index = 0
        self._rotation_count = 0

        if proxies:
            self.load_proxies(proxies)

        logger.info(f"ProxyManager initialized with {len(self.proxy_pool)} proxies")

    def load_proxies(self, proxy_list: List[str]):
        """
        Load proxies from a list of URLs.
        Format: protocol://user:pass@host:port or host:port
        """
        for proxy_url in proxy_list:
            proxy_url = proxy_url.strip()
            if not proxy_url:
                continue

            # Parse proxy URL
            if "://" in proxy_url:
                protocol, rest = proxy_url.split("://", 1)
            else:
                protocol = "http"
                rest = proxy_url

            username = None
            password = None

            if "@" in rest:
                auth, host = rest.rsplit("@", 1)
                if ":" in auth:
                    username, password = auth.split(":", 1)
            else:
                host = rest

            self.proxy_pool.append(ProxyInfo(
                url=host,
                protocol=protocol,
                username=username,
                password=password,
            ))

    def load_from_file(self, filepath: str):
        """Load proxies from a text file (one per line)"""
        try:
            with open(filepath, "r") as f:
                proxies = [line.strip() for line in f if line.strip()]
            self.load_proxies(proxies)
            logger.info(f"Loaded {len(proxies)} proxies from {filepath}")
        except FileNotFoundError:
            logger.error(f"Proxy file not found: {filepath}")

    def get_proxy(self) -> Optional[str]:
        """
        Get the next available proxy using round-robin rotation.
        Returns None if no proxies are available.
        """
        active_proxies = [p for p in self.proxy_pool if p.is_active]

        if not active_proxies:
            logger.warning("No active proxies available")
            return None

        # Round-robin with weighted selection (prefer higher success rate)
        proxy = random.choices(
            active_proxies,
            weights=[p.success_rate + 0.1 for p in active_proxies],
            k=1,
        )[0]

        proxy.last_used = time.time()
        self._rotation_count += 1

        return proxy.full_url

    def report_success(self, proxy_url: str):
        """Report a successful request through a proxy"""
        for proxy in self.proxy_pool:
            if proxy.full_url == proxy_url:
                proxy.success_count += 1
                break

    def report_failure(self, proxy_url: str):
        """Report a failed request through a proxy"""
        for proxy in self.proxy_pool:
            if proxy.full_url == proxy_url:
                proxy.fail_count += 1
                if proxy.fail_count >= self.MAX_FAILS:
                    proxy.is_active = False
                    logger.warning(f"Proxy deactivated due to failures: {proxy.url}")
                break

    def get_stats(self) -> Dict:
        """Get proxy pool statistics"""
        active = [p for p in self.proxy_pool if p.is_active]
        return {
            "total": len(self.proxy_pool),
            "active": len(active),
            "inactive": len(self.proxy_pool) - len(active),
            "total_rotations": self._rotation_count,
        }

    def reset_all(self):
        """Reset all proxy stats and reactivate all proxies"""
        for proxy in self.proxy_pool:
            proxy.fail_count = 0
            proxy.success_count = 0
            proxy.is_active = True
        logger.info("All proxies reset and reactivated")
