"""
Base utilities for scraping jobs.
Shared messaging, confirmation, and browser engine abstraction.
"""
import json
import time
import queue
from enum import Enum
from typing import Optional


class BrowserEngine(Enum):
    """Available browser engines for scraping."""
    UNDETECTED_CHROME = "uc"
    CLOAKBROWSER = "cloak"
    CAMOUFOX = "camoufox"


# Global references (set by server.py at startup)
active_jobs: dict = {}
message_queues: dict = {}  # job_id -> Queue


def init_globals(jobs_ref: dict, queues_ref: dict):
    """Initialize global references from server.py."""
    global active_jobs, message_queues
    active_jobs = jobs_ref
    message_queues = queues_ref


def send_ws_message(job_id: str, msg_type: str, data: dict):
    """Send message to WebSocket client (thread-safe via queue).

    Args:
        job_id: Unique job identifier
        msg_type: Message type (status, progress, error, complete, need_action)
        data: Message payload dict
    """
    q = message_queues.get(job_id)
    if q:
        message = json.dumps({"type": msg_type, **data})
        q.put(message)


def wait_for_confirmation(job_id: str, timeout: int = 300) -> bool:
    """Wait for user confirmation via WebSocket (blocking, called from thread).

    Args:
        job_id: Unique job identifier
        timeout: Max seconds to wait (default 5 minutes)

    Returns:
        True if confirmed, False if timeout
    """
    active_jobs[job_id]["confirmed"] = False
    elapsed = 0
    while elapsed < timeout:
        if active_jobs.get(job_id, {}).get("confirmed"):
            active_jobs[job_id]["confirmed"] = False
            return True
        time.sleep(1)
        elapsed += 1
    return False


def detect_challenge(page_source: str, current_url: str) -> bool:
    """Detect Cloudflare or other anti-bot challenges.

    Args:
        page_source: HTML source of the page
        current_url: Current browser URL

    Returns:
        True if challenge/CAPTCHA detected
    """
    indicators = [
        "challenge", "cf-browser-verification", "turnstile",
        "checking your browser", "just a moment", "ray id",
        "cloudflare", "verify", "captcha"
    ]
    source_lower = page_source.lower()
    url_lower = current_url.lower()
    return any(x in source_lower or x in url_lower for x in indicators)


def scroll_page_gradually(driver, steps: int = 8, delay: float = 2.5):
    """Scroll page gradually to trigger lazy loading (Selenium).

    Args:
        driver: Selenium WebDriver instance
        steps: Number of scroll steps
        delay: Seconds between each scroll
    """
    for i in range(steps):
        pct = (i + 1) * (100 // steps)
        driver.execute_script(
            f"window.scrollTo(0, document.body.scrollHeight * {pct}/100);"
        )
        time.sleep(delay)
    # Scroll to top then bottom for full load
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(delay * 2)


async def scroll_page_gradually_async(page, steps: int = 8, delay: float = 2.0):
    """Scroll page gradually to trigger lazy loading (Playwright/async).

    Args:
        page: Playwright page instance
        steps: Number of scroll steps
        delay: Seconds between each scroll
    """
    import asyncio
    for i in range(steps):
        pct = (i + 1) * (100 // steps)
        await page.evaluate(
            f"window.scrollTo(0, document.body.scrollHeight * {pct}/100);"
        )
        await asyncio.sleep(delay)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
    await asyncio.sleep(delay * 2.5)
