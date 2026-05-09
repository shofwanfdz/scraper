"""
Data Repository - CRUD operations for scraped data
"""
import hashlib
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from loguru import logger

from .models import ScrapingJob, ScrapedData, ExportHistory, JobStatus, DataCategory


class JobRepository:
    """CRUD operations for scraping jobs"""

    def __init__(self, session: Session):
        self.session = session

    def create(self, name: str, target_url: str, category: str = "custom", **kwargs) -> ScrapingJob:
        """Create a new scraping job"""
        from urllib.parse import urlparse
        domain = urlparse(target_url).netloc

        job = ScrapingJob(
            name=name,
            target_url=target_url,
            target_domain=domain,
            category=DataCategory(category),
            **kwargs,
        )
        self.session.add(job)
        self.session.flush()
        logger.info(f"Created job: {job.name} (ID: {job.id})")
        return job

    def get_by_id(self, job_id: int) -> Optional[ScrapingJob]:
        """Get a job by ID"""
        return self.session.query(ScrapingJob).filter(ScrapingJob.id == job_id).first()

    def get_all(self, status: Optional[str] = None, limit: int = 50) -> List[ScrapingJob]:
        """Get all jobs, optionally filtered by status"""
        query = self.session.query(ScrapingJob)
        if status:
            query = query.filter(ScrapingJob.status == JobStatus(status))
        return query.order_by(desc(ScrapingJob.created_at)).limit(limit).all()

    def update_status(self, job_id: int, status: str, **kwargs):
        """Update job status and optional fields"""
        job = self.get_by_id(job_id)
        if job:
            job.status = JobStatus(status)
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            self.session.flush()

    def mark_started(self, job_id: int):
        """Mark a job as started"""
        self.update_status(job_id, "running", started_at=datetime.utcnow())

    def mark_completed(self, job_id: int, items_scraped: int = 0):
        """Mark a job as completed"""
        job = self.get_by_id(job_id)
        if job:
            now = datetime.utcnow()
            duration = (now - job.started_at).total_seconds() if job.started_at else 0
            self.update_status(
                job_id, "completed",
                completed_at=now,
                items_scraped=items_scraped,
                duration_seconds=duration,
                success_rate=100.0 if job.errors_count == 0 else
                    round((items_scraped / (items_scraped + job.errors_count)) * 100, 2),
            )

    def mark_failed(self, job_id: int, error_msg: str = ""):
        """Mark a job as failed"""
        self.update_status(job_id, "failed", completed_at=datetime.utcnow())

    def delete(self, job_id: int) -> bool:
        """Delete a job and its data"""
        job = self.get_by_id(job_id)
        if job:
            self.session.delete(job)
            self.session.flush()
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get overall job statistics"""
        total = self.session.query(func.count(ScrapingJob.id)).scalar()
        completed = self.session.query(func.count(ScrapingJob.id)).filter(
            ScrapingJob.status == JobStatus.COMPLETED
        ).scalar()
        failed = self.session.query(func.count(ScrapingJob.id)).filter(
            ScrapingJob.status == JobStatus.FAILED
        ).scalar()
        total_items = self.session.query(func.sum(ScrapingJob.items_scraped)).scalar() or 0

        return {
            "total_jobs": total,
            "completed": completed,
            "failed": failed,
            "running": total - completed - failed,
            "total_items_scraped": total_items,
        }


class DataRepository:
    """CRUD operations for scraped data"""

    def __init__(self, session: Session):
        self.session = session

    def _generate_checksum(self, data: Dict) -> str:
        """Generate a checksum for deduplication"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()

    def save(
        self,
        job_id: int,
        source_url: str,
        data: Dict[str, Any],
        title: Optional[str] = None,
        category: str = "custom",
        raw_html: Optional[str] = None,
    ) -> Optional[ScrapedData]:
        """Save a scraped data item (with deduplication)"""
        from urllib.parse import urlparse

        checksum = self._generate_checksum(data)

        # Check for duplicates
        existing = self.session.query(ScrapedData).filter(
            ScrapedData.checksum == checksum
        ).first()
        if existing:
            logger.debug(f"Duplicate data skipped: {title}")
            return None

        record = ScrapedData(
            job_id=job_id,
            source_url=source_url,
            source_domain=urlparse(source_url).netloc,
            title=title,
            data=data,
            category=DataCategory(category),
            raw_html=raw_html,
            checksum=checksum,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def save_batch(
        self,
        job_id: int,
        items: List[Dict[str, Any]],
        source_url: str,
        category: str = "custom",
    ) -> int:
        """Save multiple items at once. Returns count of saved items."""
        saved = 0
        for item in items:
            title = item.get("title") or item.get("name") or str(item.get("id", ""))
            result = self.save(
                job_id=job_id,
                source_url=source_url,
                data=item,
                title=title,
                category=category,
            )
            if result:
                saved += 1
        logger.info(f"Batch save: {saved}/{len(items)} items saved (duplicates skipped)")
        return saved

    def get_by_job(self, job_id: int, limit: int = 100, offset: int = 0) -> List[ScrapedData]:
        """Get all data for a specific job"""
        return (
            self.session.query(ScrapedData)
            .filter(ScrapedData.job_id == job_id)
            .order_by(desc(ScrapedData.scraped_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_by_category(self, category: str, limit: int = 100) -> List[ScrapedData]:
        """Get data by category"""
        return (
            self.session.query(ScrapedData)
            .filter(ScrapedData.category == DataCategory(category))
            .order_by(desc(ScrapedData.scraped_at))
            .limit(limit)
            .all()
        )

    def search(self, query: str, limit: int = 50) -> List[ScrapedData]:
        """Search scraped data by title"""
        return (
            self.session.query(ScrapedData)
            .filter(ScrapedData.title.ilike(f"%{query}%"))
            .limit(limit)
            .all()
        )

    def count_by_job(self, job_id: int) -> int:
        """Count items for a job"""
        return self.session.query(func.count(ScrapedData.id)).filter(
            ScrapedData.job_id == job_id
        ).scalar()

    def delete_by_job(self, job_id: int) -> int:
        """Delete all data for a job"""
        count = self.session.query(ScrapedData).filter(
            ScrapedData.job_id == job_id
        ).delete()
        self.session.flush()
        return count
