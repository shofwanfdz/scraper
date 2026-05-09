"""
Jobs Scraper
Scrapes job listings: titles, companies, salaries, requirements
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base import BaseScraper


class JobsScraper(BaseScraper):
    """
    Scraper for job listing websites.
    Extracts job titles, companies, salaries, locations, and requirements.
    """

    SCRAPER_NAME = "jobs"
    CATEGORY = "jobs"
    REQUIRES_BROWSER = False

    DEFAULT_SELECTORS = {
        "job_container": ".job-card, .job-item, .vacancy, .job-listing, [data-job-id]",
        "title": "h2, h3, .job-title, .position-title, [data-job-title]",
        "company": ".company, .company-name, .employer, [data-company]",
        "salary": ".salary, .compensation, .gaji, [data-salary]",
        "location": ".location, .job-location, .city, [data-location]",
        "job_type": ".job-type, .employment-type, .type",
        "posted_date": ".date, .posted, time, [data-posted]",
        "description": ".description, .job-desc, .summary",
        "requirements": ".requirements, .qualifications, ul",
        "link": "a",
        "experience": ".experience, .exp-level",
    }

    def __init__(self, selectors: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.selectors = selectors or self.DEFAULT_SELECTORS

    async def scrape(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape job listings from a job board.

        Args:
            target_url: URL of the job listing page
            max_pages: Maximum pages to scrape
            keyword: Search keyword filter

        Returns:
            List of job data dictionaries
        """
        max_pages = kwargs.get("max_pages", 1)
        all_jobs = []
        current_url = target_url

        for page_num in range(1, max_pages + 1):
            logger.info(f"[{self.SCRAPER_NAME}] Scraping page {page_num}: {current_url}")

            html = await self.engine.fetch_html(current_url)
            if not html:
                break

            soup = self.engine.parse_html(html)
            jobs = self._extract_jobs(soup, current_url)
            all_jobs.extend(jobs)

            logger.info(f"Page {page_num}: Found {len(jobs)} jobs")

            # Find next page
            if page_num < max_pages:
                next_url = self._find_next_page(soup, current_url)
                if next_url:
                    current_url = next_url
                else:
                    break

        return all_jobs

    def _extract_jobs(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract all jobs from a page"""
        jobs = []
        containers = soup.select(self.selectors["job_container"])

        from core.anti_detection import AntiDetection
        containers = AntiDetection.filter_honeypots(containers)

        for container in containers:
            job = self.parse_item(container)
            if job:
                if job.get("link") and not job["link"].startswith("http"):
                    job["link"] = urljoin(base_url, job["link"])
                jobs.append(job)

        return jobs

    def parse_item(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """Parse a single job listing"""
        if not isinstance(raw_data, Tag):
            return None

        container = raw_data
        job = {}

        # Title (required)
        title_el = container.select_one(self.selectors["title"])
        if title_el:
            job["title"] = title_el.get_text(strip=True)
        else:
            return None

        # Company
        company_el = container.select_one(self.selectors["company"])
        if company_el:
            job["company"] = company_el.get_text(strip=True)

        # Salary
        salary_el = container.select_one(self.selectors["salary"])
        if salary_el:
            salary_text = salary_el.get_text(strip=True)
            job["salary_text"] = salary_text
            parsed = self._parse_salary(salary_text)
            if parsed:
                job.update(parsed)

        # Location
        location_el = container.select_one(self.selectors["location"])
        if location_el:
            job["location"] = location_el.get_text(strip=True)

        # Job type
        type_el = container.select_one(self.selectors["job_type"])
        if type_el:
            job["job_type"] = type_el.get_text(strip=True)

        # Posted date
        date_el = container.select_one(self.selectors["posted_date"])
        if date_el:
            job["posted_date"] = date_el.get("datetime") or date_el.get_text(strip=True)

        # Description
        desc_el = container.select_one(self.selectors["description"])
        if desc_el:
            job["description"] = desc_el.get_text(strip=True)[:500]

        # Experience
        exp_el = container.select_one(self.selectors["experience"])
        if exp_el:
            job["experience"] = exp_el.get_text(strip=True)

        # Link
        link_el = container.select_one(self.selectors["link"])
        if link_el:
            job["link"] = link_el.get("href", "")

        if not self.validate_item(job, ["title"]):
            return None

        return job

    def _parse_salary(self, salary_text: str) -> Optional[Dict[str, Any]]:
        """Parse salary range from text"""
        if not salary_text:
            return None

        result = {}

        # Try to find salary range (e.g., "5.000.000 - 10.000.000")
        range_match = re.search(
            r"(\d[\d.,]*)\s*[-–]\s*(\d[\d.,]*)", salary_text
        )
        if range_match:
            result["salary_min"] = self._clean_number(range_match.group(1))
            result["salary_max"] = self._clean_number(range_match.group(2))
        else:
            # Single value
            single_match = re.search(r"(\d[\d.,]+)", salary_text)
            if single_match:
                result["salary_min"] = self._clean_number(single_match.group(1))
                result["salary_max"] = result["salary_min"]

        # Detect currency
        if "rp" in salary_text.lower() or "idr" in salary_text.lower():
            result["currency"] = "IDR"
        elif "$" in salary_text or "usd" in salary_text.lower():
            result["currency"] = "USD"

        return result if result else None

    def _clean_number(self, text: str) -> Optional[float]:
        """Clean and parse a number"""
        cleaned = text.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Find next page URL"""
        next_selectors = [
            "a.next", "a[rel='next']", ".pagination .next a",
            "a[aria-label='Next']", "li.next a",
        ]
        for selector in next_selectors:
            try:
                el = soup.select_one(selector)
                if el and el.get("href"):
                    return urljoin(current_url, el["href"])
            except Exception:
                continue
        return None
