"""
News Scraper
Scrapes news articles: titles, content, authors, dates
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from datetime import datetime

from bs4 import BeautifulSoup, Tag
from loguru import logger

from .base import BaseScraper


class NewsScraper(BaseScraper):
    """
    Scraper for news websites.
    Extracts articles, headlines, authors, and publication dates.
    """

    SCRAPER_NAME = "news"
    CATEGORY = "news"
    REQUIRES_BROWSER = False

    DEFAULT_SELECTORS = {
        "article_container": "article, .article, .news-item, .post, .story",
        "title": "h1, h2, h3, .title, .headline, .entry-title",
        "content": ".content, .article-body, .entry-content, .post-content, p",
        "author": ".author, .byline, [rel='author'], .writer",
        "date": "time, .date, .published, .post-date, [datetime]",
        "category": ".category, .tag, .section-name",
        "image": "img, .featured-image img, .thumbnail img",
        "link": "a",
        "summary": ".summary, .excerpt, .lead, .description",
    }

    def __init__(self, selectors: Optional[Dict[str, str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.selectors = selectors or self.DEFAULT_SELECTORS

    async def scrape(self, target_url: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape news articles from a news website.

        Args:
            target_url: URL of the news page
            max_pages: Maximum pages to scrape
            scrape_content: Whether to scrape full article content

        Returns:
            List of article data dictionaries
        """
        max_pages = kwargs.get("max_pages", 1)
        scrape_content = kwargs.get("scrape_content", False)
        all_articles = []
        current_url = target_url

        for page_num in range(1, max_pages + 1):
            logger.info(f"[{self.SCRAPER_NAME}] Scraping page {page_num}: {current_url}")

            html = await self.engine.fetch_html(current_url)
            if not html:
                break

            soup = self.engine.parse_html(html)
            articles = self._extract_articles(soup, current_url)

            # Optionally scrape full content for each article
            if scrape_content:
                for article in articles:
                    if article.get("link"):
                        content = await self._scrape_article_content(article["link"])
                        if content:
                            article["full_content"] = content

            all_articles.extend(articles)
            logger.info(f"Page {page_num}: Found {len(articles)} articles")

            # Find next page
            if page_num < max_pages:
                next_url = self._find_next_page(soup, current_url)
                if next_url:
                    current_url = next_url
                else:
                    break

        return all_articles

    def _extract_articles(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract all articles from a page"""
        articles = []
        containers = soup.select(self.selectors["article_container"])

        from core.anti_detection import AntiDetection
        containers = AntiDetection.filter_honeypots(containers)

        for container in containers:
            article = self.parse_item(container)
            if article:
                if article.get("link") and not article["link"].startswith("http"):
                    article["link"] = urljoin(base_url, article["link"])
                if article.get("image") and not article["image"].startswith("http"):
                    article["image"] = urljoin(base_url, article["image"])
                articles.append(article)

        return articles

    def parse_item(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """Parse a single article"""
        if not isinstance(raw_data, Tag):
            return None

        container = raw_data
        article = {}

        # Title (required)
        title_el = container.select_one(self.selectors["title"])
        if title_el:
            article["title"] = title_el.get_text(strip=True)
        else:
            return None

        # Author
        author_el = container.select_one(self.selectors["author"])
        if author_el:
            article["author"] = author_el.get_text(strip=True)

        # Date
        date_el = container.select_one(self.selectors["date"])
        if date_el:
            article["published_date"] = (
                date_el.get("datetime") or date_el.get_text(strip=True)
            )

        # Summary/excerpt
        summary_el = container.select_one(self.selectors["summary"])
        if summary_el:
            article["summary"] = summary_el.get_text(strip=True)[:300]

        # Category
        cat_el = container.select_one(self.selectors["category"])
        if cat_el:
            article["category"] = cat_el.get_text(strip=True)

        # Image
        img_el = container.select_one(self.selectors["image"])
        if img_el:
            article["image"] = (
                img_el.get("data-src") or img_el.get("src") or ""
            )

        # Link
        link_el = container.select_one(self.selectors["link"])
        if link_el:
            article["link"] = link_el.get("href", "")

        if not self.validate_item(article, ["title"]):
            return None

        return article

    async def _scrape_article_content(self, url: str) -> Optional[str]:
        """Scrape the full content of an article"""
        try:
            html = await self.engine.fetch_html(url)
            if not html:
                return None

            soup = self.engine.parse_html(html)

            # Try common content selectors
            content_selectors = [
                "article .content", ".article-body", ".entry-content",
                ".post-content", ".story-body", "article p",
            ]

            for selector in content_selectors:
                content_el = soup.select(selector)
                if content_el:
                    paragraphs = []
                    for el in content_el:
                        text = el.get_text(strip=True)
                        if text and len(text) > 20:
                            paragraphs.append(text)
                    if paragraphs:
                        return "\n\n".join(paragraphs)

            return None
        except Exception as e:
            logger.debug(f"Failed to scrape article content: {url} - {e}")
            return None

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Find next page URL"""
        next_selectors = [
            "a.next", "a[rel='next']", ".pagination .next a",
            "a[aria-label='Next']", ".nav-next a",
        ]
        for selector in next_selectors:
            try:
                el = soup.select_one(selector)
                if el and el.get("href"):
                    return urljoin(current_url, el["href"])
            except Exception:
                continue
        return None
