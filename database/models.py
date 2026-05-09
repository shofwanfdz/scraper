"""
Database Models (SQLAlchemy ORM)
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float,
    Boolean, JSON, Enum, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class JobStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class DataCategory(enum.Enum):
    ECOMMERCE = "ecommerce"
    PROPERTY = "property"
    JOBS = "jobs"
    NEWS = "news"
    LEADS = "leads"
    FINANCE = "finance"
    SOCIAL_MEDIA = "social_media"
    SERP = "serp"
    CUSTOM = "custom"


class ScrapingJob(Base):
    """Represents a scraping job/task"""
    __tablename__ = "scraping_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(Enum(DataCategory), default=DataCategory.CUSTOM)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING)

    # Target configuration
    target_url = Column(Text, nullable=False)
    target_domain = Column(String(255), nullable=True)
    config = Column(JSON, nullable=True)  # Scraper-specific config

    # Scheduling
    schedule_cron = Column(String(100), nullable=True)  # Cron expression
    is_recurring = Column(Boolean, default=False)

    # Statistics
    total_pages = Column(Integer, default=0)
    pages_scraped = Column(Integer, default=0)
    items_scraped = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scraped_data = relationship("ScrapedData", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_status", "status"),
        Index("idx_category", "category"),
        Index("idx_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<ScrapingJob(id={self.id}, name='{self.name}', status={self.status.value})>"


class ScrapedData(Base):
    """Stores individual scraped data items"""
    __tablename__ = "scraped_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("scraping_jobs.id"), nullable=False)
    category = Column(Enum(DataCategory), default=DataCategory.CUSTOM)

    # Source
    source_url = Column(Text, nullable=False)
    source_domain = Column(String(255), nullable=True)

    # Data
    title = Column(String(500), nullable=True)
    data = Column(JSON, nullable=False)  # The actual scraped data
    raw_html = Column(Text, nullable=True)  # Optional: store raw HTML

    # Metadata
    scraped_at = Column(DateTime, default=datetime.utcnow)
    is_valid = Column(Boolean, default=True)
    checksum = Column(String(64), nullable=True)  # For deduplication

    # Relationships
    job = relationship("ScrapingJob", back_populates="scraped_data")

    __table_args__ = (
        Index("idx_job_id", "job_id"),
        Index("idx_category_data", "category"),
        Index("idx_source_domain", "source_domain"),
        Index("idx_scraped_at", "scraped_at"),
        Index("idx_checksum", "checksum"),
    )

    def __repr__(self):
        return f"<ScrapedData(id={self.id}, title='{self.title}', job_id={self.job_id})>"


class ProxyRecord(Base):
    """Tracks proxy usage and health"""
    __tablename__ = "proxy_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    proxy_url = Column(String(500), nullable=False, unique=True)
    protocol = Column(String(10), default="http")
    country = Column(String(5), nullable=True)

    # Health metrics
    is_active = Column(Boolean, default=True)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    avg_response_time = Column(Float, nullable=True)
    last_checked = Column(DateTime, nullable=True)
    last_used = Column(DateTime, nullable=True)

    # Metadata
    added_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_proxy_active", "is_active"),
    )

    def __repr__(self):
        return f"<ProxyRecord(url='{self.proxy_url}', active={self.is_active})>"


class ExportHistory(Base):
    """Tracks data exports"""
    __tablename__ = "export_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("scraping_jobs.id"), nullable=True)
    filename = Column(String(500), nullable=False)
    format = Column(String(20), nullable=False)  # csv, json, excel
    records_count = Column(Integer, default=0)
    file_size_bytes = Column(Integer, nullable=True)
    exported_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ExportHistory(filename='{self.filename}', format='{self.format}')>"


class Brand(Base):
    """Stores brand names scraped from marketplace filters"""
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    source = Column(String(50), default="blibli")  # marketplace source
    category = Column(String(100), nullable=True)  # keyword/category where found
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_brand_name", "name"),
        Index("idx_brand_source", "source"),
    )

    def __repr__(self):
        return f"<Brand(name='{self.name}', source='{self.source}')>"
