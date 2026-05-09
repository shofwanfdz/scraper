"""
FastAPI Application - REST API for Scraping Tools
Provides endpoints for managing scraping jobs, viewing data, and exporting
"""
import asyncio
from typing import Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from loguru import logger

from config.settings import APP
from database.connection import get_db
from database.repository import JobRepository, DataRepository
from database.models import JobStatus, DataCategory
from scrapers import EcommerceScraper, JobsScraper, NewsScraper, PropertyScraper
from exporters import CSVExporter, JSONExporter, ExcelExporter

# Initialize FastAPI app
app = FastAPI(
    title="🕷️ Scraping Tools API",
    description="Automated web scraping tools with anti-detection capabilities",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Pydantic Models ============

class JobCreate(BaseModel):
    name: str
    target_url: str
    category: str = "custom"
    scraper_type: str = "ecommerce"  # ecommerce, jobs, news, property
    max_pages: int = 1
    use_proxy: bool = False
    config: dict = {}


class JobResponse(BaseModel):
    id: int
    name: str
    status: str
    category: str
    target_url: str
    items_scraped: int
    errors_count: int
    success_rate: float
    created_at: str
    duration_seconds: Optional[float] = None


class ExportRequest(BaseModel):
    job_id: int
    format: str = "csv"  # csv, json, excel
    fields: Optional[List[str]] = None


class StatsResponse(BaseModel):
    total_jobs: int
    completed: int
    failed: int
    running: int
    total_items_scraped: int


# ============ Helper Functions ============

def get_scraper(scraper_type: str):
    """Get the appropriate scraper instance"""
    scrapers = {
        "ecommerce": EcommerceScraper,
        "jobs": JobsScraper,
        "news": NewsScraper,
        "property": PropertyScraper,
    }
    scraper_class = scrapers.get(scraper_type)
    if not scraper_class:
        raise HTTPException(status_code=400, detail=f"Unknown scraper type: {scraper_type}")
    return scraper_class


async def run_scraping_job(job_data: JobCreate):
    """Background task to run a scraping job"""
    scraper_class = get_scraper(job_data.scraper_type)
    scraper = scraper_class(config=job_data.config)

    await scraper.run(
        target_url=job_data.target_url,
        job_name=job_data.name,
        save_to_db=True,
        max_pages=job_data.max_pages,
    )


# ============ API Endpoints ============

@app.get("/")
async def root():
    """API root - health check"""
    return {
        "status": "running",
        "name": "Scraping Tools API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get overall scraping statistics"""
    db = get_db()
    with db.get_session() as session:
        job_repo = JobRepository(session)
        return job_repo.get_stats()


# --- Jobs Endpoints ---

@app.post("/jobs", response_model=dict)
async def create_job(job_data: JobCreate, background_tasks: BackgroundTasks):
    """Create and start a new scraping job"""
    background_tasks.add_task(run_scraping_job, job_data)
    return {
        "message": f"Scraping job '{job_data.name}' started",
        "scraper_type": job_data.scraper_type,
        "target_url": job_data.target_url,
    }


@app.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """List all scraping jobs"""
    db = get_db()
    with db.get_session() as session:
        job_repo = JobRepository(session)
        jobs = job_repo.get_all(status=status, limit=limit)
        return [
            {
                "id": job.id,
                "name": job.name,
                "status": job.status.value,
                "category": job.category.value,
                "target_url": job.target_url,
                "items_scraped": job.items_scraped,
                "errors_count": job.errors_count,
                "success_rate": job.success_rate,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "duration_seconds": job.duration_seconds,
            }
            for job in jobs
        ]


@app.get("/jobs/{job_id}")
async def get_job(job_id: int):
    """Get details of a specific job"""
    db = get_db()
    with db.get_session() as session:
        job_repo = JobRepository(session)
        job = job_repo.get_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "id": job.id,
            "name": job.name,
            "status": job.status.value,
            "category": job.category.value,
            "target_url": job.target_url,
            "target_domain": job.target_domain,
            "items_scraped": job.items_scraped,
            "errors_count": job.errors_count,
            "success_rate": job.success_rate,
            "config": job.config,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duration_seconds": job.duration_seconds,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: int):
    """Delete a job and its data"""
    db = get_db()
    with db.get_session() as session:
        job_repo = JobRepository(session)
        success = job_repo.delete(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        session.commit()
        return {"message": f"Job {job_id} deleted"}


# --- Data Endpoints ---

@app.get("/data/{job_id}")
async def get_job_data(
    job_id: int,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
):
    """Get scraped data for a specific job"""
    db = get_db()
    with db.get_session() as session:
        data_repo = DataRepository(session)
        items = data_repo.get_by_job(job_id, limit=limit, offset=offset)
        total = data_repo.count_by_job(job_id)
        return {
            "job_id": job_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "data": [
                {
                    "id": item.id,
                    "title": item.title,
                    "data": item.data,
                    "source_url": item.source_url,
                    "scraped_at": item.scraped_at.isoformat() if item.scraped_at else None,
                }
                for item in items
            ],
        }


@app.get("/data/search/{query}")
async def search_data(query: str, limit: int = 50):
    """Search scraped data by title"""
    db = get_db()
    with db.get_session() as session:
        data_repo = DataRepository(session)
        items = data_repo.search(query, limit=limit)
        return {
            "query": query,
            "results": len(items),
            "data": [
                {
                    "id": item.id,
                    "title": item.title,
                    "data": item.data,
                    "source_url": item.source_url,
                    "category": item.category.value,
                }
                for item in items
            ],
        }


# --- Export Endpoints ---

@app.post("/export")
async def export_data(request: ExportRequest):
    """Export scraped data to file"""
    db = get_db()
    with db.get_session() as session:
        data_repo = DataRepository(session)
        items = data_repo.get_by_job(request.job_id, limit=10000)

        if not items:
            raise HTTPException(status_code=404, detail="No data found for this job")

        # Convert to list of dicts
        data = [item.data for item in items]

        # Export based on format
        if request.format == "csv":
            exporter = CSVExporter()
        elif request.format == "json":
            exporter = JSONExporter()
        elif request.format == "excel":
            exporter = ExcelExporter()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown format: {request.format}")

        filepath = exporter.export(data, fields=request.fields)

        if not filepath:
            raise HTTPException(status_code=500, detail="Export failed")

        return {"message": "Export successful", "filepath": filepath, "records": len(data)}


# ============ Run Server ============

def start_server():
    """Start the API server"""
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=APP["host"],
        port=APP["port"],
        reload=APP["debug"],
    )


if __name__ == "__main__":
    start_server()
