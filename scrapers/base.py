"""
Base Scraper - Abstract base class for all scrapers
"""
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

from loguru import logger

from core.engine import ScrapingEngine
from core.browser import BrowserEngine
from database.connection import get_db
from database.repository import JobRepository, DataRepository


class BaseScraper(ABC):
    """
    Abstract base class for all scraper modules.
    Provides common functionality and enforces a consistent interface.
    """

    # Override in subclasses
    SCRAPER_NAME = "base"
    CATEGORY = "custom"
    REQUIRES_BROWSER = False  # Set True for JS-heavy sites

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.engine = ScrapingEngine()
        self.browser: Optional[BrowserEngine] = None
        self._results: List[Dict[str, Any]] = []
        self._errors: List[str] = []
        self._job_id: Optional[int] = None
        self._start_time: Optional[datetime] = None

    async def setup(self):
        """Initialize the scraper"""
        await self.engine.start()
        if self.REQUIRES_BROWSER:
            self.browser = BrowserEngine(headless=True)
            await self.browser.start()
        logger.info(f"[{self.SCRAPER_NAME}] Scraper initialized")

    async def teardown(self):
        """Cleanup resources"""
        await self.engine.stop()
        if self.browser:
            await self.browser.stop()
        logger.info(f"[{self.SCRAPER_NAME}] Scraper stopped")

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.teardown()

    @abstractmethod
    async def scrape(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Main scraping method. Must be implemented by subclasses.

        Args:
            target_url: The URL to scrape
            **kwargs: Additional scraper-specific parameters

        Returns:
            List of scraped data dictionaries
        """
        pass

    @abstractmethod
    def parse_item(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """
        Parse a single item from raw data.
        Must be implemented by subclasses.

        Args:
            raw_data: Raw data (BeautifulSoup element, dict, etc.)

        Returns:
            Parsed data dictionary or None if invalid
        """
        pass

    async def run(
        self,
        target_url: str,
        job_name: Optional[str] = None,
        save_to_db: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute the full scraping pipeline.

        Args:
            target_url: Target URL to scrape
            job_name: Name for the scraping job
            save_to_db: Whether to save results to database
            **kwargs: Additional parameters

        Returns:
            Summary of the scraping run
        """
        self._start_time = datetime.utcnow()
        self._results = []
        self._errors = []

        job_name = job_name or f"{self.SCRAPER_NAME}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create job in database
        if save_to_db:
            db = get_db()
            with db.get_session() as session:
                job_repo = JobRepository(session)
                job = job_repo.create(
                    name=job_name,
                    target_url=target_url,
                    category=self.CATEGORY,
                    config=self.config,
                )
                self._job_id = job.id
                job_repo.mark_started(self._job_id)
                session.commit()

        try:
            # Run the scraper
            async with self:
                results = await self.scrape(target_url, **kwargs)
                self._results = results

            # Save results to database
            if save_to_db and self._results:
                db = get_db()
                with db.get_session() as session:
                    data_repo = DataRepository(session)
                    saved_count = data_repo.save_batch(
                        job_id=self._job_id,
                        items=self._results,
                        source_url=target_url,
                        category=self.CATEGORY,
                    )

                    # Update job status
                    job_repo = JobRepository(session)
                    job_repo.mark_completed(self._job_id, items_scraped=saved_count)
                    session.commit()

        except Exception as e:
            error_msg = str(e)
            self._errors.append(error_msg)
            logger.error(f"[{self.SCRAPER_NAME}] Scraping failed: {error_msg}")

            if save_to_db and self._job_id:
                db = get_db()
                with db.get_session() as session:
                    job_repo = JobRepository(session)
                    job_repo.mark_failed(self._job_id, error_msg)
                    session.commit()

        # Return summary
        duration = (datetime.utcnow() - self._start_time).total_seconds()
        summary = {
            "scraper": self.SCRAPER_NAME,
            "job_id": self._job_id,
            "target_url": target_url,
            "items_scraped": len(self._results),
            "errors": len(self._errors),
            "duration_seconds": round(duration, 2),
            "status": "completed" if not self._errors else "failed",
            "engine_stats": self.engine.stats,
        }

        logger.info(
            f"[{self.SCRAPER_NAME}] Completed: "
            f"{summary['items_scraped']} items in {summary['duration_seconds']}s"
        )
        return summary

    def validate_item(self, item: Dict[str, Any], required_fields: List[str]) -> bool:
        """Validate that an item has all required fields"""
        for field in required_fields:
            if field not in item or item[field] is None:
                return False
        return True

    @property
    def results(self) -> List[Dict[str, Any]]:
        """Get the scraped results"""
        return self._results

    @property
    def errors(self) -> List[str]:
        """Get any errors that occurred"""
        return self._errors
