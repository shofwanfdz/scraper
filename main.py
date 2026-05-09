"""
Main CLI Entry Point for Scraping Tools
Usage:
    python main.py scrape --type ecommerce --url "https://example.com/products" --pages 3
    python main.py server
    python main.py init-db
"""
import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import LOG_LEVEL, LOG_DIR

# Configure logging
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>")
logger.add(str(LOG_DIR / "scraping_{time}.log"), rotation="10 MB", retention="7 days", level="DEBUG")

console = Console()


@click.group()
@click.version_option(version="1.0.0", prog_name="Scraping Tools")
def cli():
    """🕷️ Scraping Tools - Automated Web Data Extraction"""
    pass


@cli.command()
def init_db():
    """Initialize the database (create tables)"""
    from database.connection import get_db

    console.print("[bold blue]Initializing database...[/bold blue]")
    try:
        db = get_db()
        db.create_tables()
        console.print("[bold green]✓ Database tables created successfully![/bold green]")
    except Exception as e:
        console.print(f"[bold red]✗ Database error: {e}[/bold red]")
        console.print("[yellow]Make sure MySQL is running and the database exists.[/yellow]")
        console.print("[yellow]Create the database with: CREATE DATABASE scraping_db;[/yellow]")


@cli.command()
@click.option("--type", "scraper_type", required=True,
              type=click.Choice(["ecommerce", "jobs", "news", "property"]),
              help="Type of scraper to use")
@click.option("--url", "target_url", required=True, help="Target URL to scrape")
@click.option("--pages", default=1, help="Number of pages to scrape")
@click.option("--name", default=None, help="Job name")
@click.option("--export", "export_format", default=None,
              type=click.Choice(["csv", "json", "excel"]),
              help="Export format")
@click.option("--no-db", is_flag=True, help="Don't save to database")
@click.option("--browser", is_flag=True, help="Use headless browser (for JS sites)")
def scrape(scraper_type, target_url, pages, name, export_format, no_db, browser):
    """Run a scraping job"""
    from scrapers import EcommerceScraper, JobsScraper, NewsScraper, PropertyScraper
    from exporters import CSVExporter, JSONExporter, ExcelExporter

    scrapers = {
        "ecommerce": EcommerceScraper,
        "jobs": JobsScraper,
        "news": NewsScraper,
        "property": PropertyScraper,
    }

    console.print(Panel(
        f"[bold]Scraper:[/bold] {scraper_type}\n"
        f"[bold]Target:[/bold] {target_url}\n"
        f"[bold]Pages:[/bold] {pages}",
        title="🕷️ Starting Scraping Job",
        border_style="blue",
    ))

    scraper_class = scrapers[scraper_type]
    scraper = scraper_class()

    if browser:
        scraper.REQUIRES_BROWSER = True

    async def _run():
        result = await scraper.run(
            target_url=target_url,
            job_name=name,
            save_to_db=not no_db,
            max_pages=pages,
        )
        return result

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Scraping in progress...", total=None)
        result = asyncio.run(_run())

    # Display results
    table = Table(title="📊 Scraping Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Status", result["status"])
    table.add_row("Items Scraped", str(result["items_scraped"]))
    table.add_row("Errors", str(result["errors"]))
    table.add_row("Duration", f"{result['duration_seconds']}s")
    table.add_row("Success Rate", f"{result['engine_stats']['success_rate']}%")

    console.print(table)

    # Export if requested
    if export_format and scraper.results:
        exporters = {
            "csv": CSVExporter(),
            "json": JSONExporter(),
            "excel": ExcelExporter(),
        }
        exporter = exporters[export_format]
        filepath = exporter.export(scraper.results)
        if filepath:
            console.print(f"\n[bold green]✓ Exported to: {filepath}[/bold green]")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Server host")
@click.option("--port", default=8000, help="Server port")
def server(host, port):
    """Start the API server"""
    console.print(Panel(
        f"[bold]Host:[/bold] {host}\n"
        f"[bold]Port:[/bold] {port}\n"
        f"[bold]Docs:[/bold] http://{host}:{port}/docs",
        title="🚀 Starting API Server",
        border_style="green",
    ))

    import uvicorn
    uvicorn.run("api.main:app", host=host, port=port, reload=True)


@cli.command()
def stats():
    """Show scraping statistics"""
    from database.connection import get_db
    from database.repository import JobRepository

    db = get_db()
    with db.get_session() as session:
        job_repo = JobRepository(session)
        stats = job_repo.get_stats()

    table = Table(title="📈 Scraping Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Jobs", str(stats["total_jobs"]))
    table.add_row("Completed", str(stats["completed"]))
    table.add_row("Failed", str(stats["failed"]))
    table.add_row("Running", str(stats["running"]))
    table.add_row("Total Items Scraped", str(stats["total_items_scraped"]))

    console.print(table)


@cli.command()
@click.option("--job-id", required=True, type=int, help="Job ID to export")
@click.option("--format", "export_format", default="csv",
              type=click.Choice(["csv", "json", "excel"]))
def export(job_id, export_format):
    """Export scraped data to file"""
    from database.connection import get_db
    from database.repository import DataRepository
    from exporters import CSVExporter, JSONExporter, ExcelExporter

    db = get_db()
    with db.get_session() as session:
        data_repo = DataRepository(session)
        items = data_repo.get_by_job(job_id, limit=10000)

        if not items:
            console.print("[red]No data found for this job[/red]")
            return

        data = [item.data for item in items]

    exporters = {
        "csv": CSVExporter(),
        "json": JSONExporter(),
        "excel": ExcelExporter(),
    }

    exporter = exporters[export_format]
    filepath = exporter.export(data)

    if filepath:
        console.print(f"[bold green]✓ Exported {len(data)} records to: {filepath}[/bold green]")
    else:
        console.print("[red]Export failed[/red]")


if __name__ == "__main__":
    cli()
