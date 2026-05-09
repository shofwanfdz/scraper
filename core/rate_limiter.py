"""
Rate Limiter
Implements intelligent rate limiting to avoid detection and server overload
"""
import asyncio
import random
import time
from typing import Optional

from loguru import logger


class RateLimiter:
    """
    Intelligent rate limiter that mimics human browsing patterns.
    Uses random delays and adaptive throttling.
    """

    def __init__(
        self,
        delay_min: float = 1.0,
        delay_max: float = 3.0,
        max_concurrent: int = 5,
        burst_limit: int = 10,
        burst_window: float = 60.0,
    ):
        """
        Args:
            delay_min: Minimum delay between requests (seconds)
            delay_max: Maximum delay between requests (seconds)
            max_concurrent: Maximum concurrent requests
            burst_limit: Max requests allowed in burst_window
            burst_window: Time window for burst detection (seconds)
        """
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.max_concurrent = max_concurrent
        self.burst_limit = burst_limit
        self.burst_window = burst_window

        self._last_request_time: float = 0
        self._request_times: list = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._total_wait_time: float = 0

    def _get_random_delay(self) -> float:
        """
        Generate a random delay that mimics human behavior.
        Uses a slightly skewed distribution (humans tend to be slower).
        """
        # Use triangular distribution - more natural than uniform
        delay = random.triangular(self.delay_min, self.delay_max, self.delay_min * 1.5)
        return round(delay, 2)

    def _check_burst(self) -> bool:
        """Check if we're within burst limits"""
        now = time.time()
        # Remove old timestamps outside the window
        self._request_times = [
            t for t in self._request_times if now - t < self.burst_window
        ]
        return len(self._request_times) < self.burst_limit

    async def wait(self):
        """
        Wait for the appropriate delay before making the next request.
        Implements both per-request delay and burst protection.
        """
        async with self._semaphore:
            now = time.time()

            # Check burst limit
            if not self._check_burst():
                # If burst limit reached, wait longer
                extra_wait = random.uniform(5, 15)
                logger.debug(f"Burst limit reached, waiting {extra_wait:.1f}s")
                await asyncio.sleep(extra_wait)
                self._total_wait_time += extra_wait

            # Calculate time since last request
            elapsed = now - self._last_request_time
            delay = self._get_random_delay()

            # Only wait if not enough time has passed
            if elapsed < delay:
                wait_time = delay - elapsed
                await asyncio.sleep(wait_time)
                self._total_wait_time += wait_time

            # Record this request
            self._last_request_time = time.time()
            self._request_times.append(self._last_request_time)

    def adjust_speed(self, factor: float):
        """
        Dynamically adjust speed based on response patterns.
        factor > 1.0 = slow down, factor < 1.0 = speed up
        """
        self.delay_min *= factor
        self.delay_max *= factor
        # Ensure minimum bounds
        self.delay_min = max(0.5, self.delay_min)
        self.delay_max = max(1.0, self.delay_max)
        logger.info(f"Rate limiter adjusted: {self.delay_min:.1f}s - {self.delay_max:.1f}s")

    @property
    def stats(self) -> dict:
        """Get rate limiter statistics"""
        return {
            "delay_range": f"{self.delay_min:.1f}s - {self.delay_max:.1f}s",
            "max_concurrent": self.max_concurrent,
            "burst_limit": f"{self.burst_limit} per {self.burst_window}s",
            "total_wait_time": f"{self._total_wait_time:.1f}s",
            "requests_in_window": len(self._request_times),
        }
