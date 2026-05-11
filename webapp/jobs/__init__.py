"""Scraping job runners for each marketplace."""
from webapp.jobs.blibli import run_blibli_job
from webapp.jobs.shopee import run_shopee_job

__all__ = ["run_blibli_job", "run_shopee_job"]
