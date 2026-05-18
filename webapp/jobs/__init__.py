"""Scraping job runners for each marketplace."""
from webapp.jobs.blibli import run_blibli_job
from webapp.jobs.shopee import run_shopee_job
from webapp.jobs.lazada import run_lazada_job
from webapp.jobs.tokopedia import run_tokopedia_job
from webapp.jobs.tiktokshop import run_tiktokshop_job

__all__ = ["run_blibli_job", "run_shopee_job", "run_lazada_job", "run_tokopedia_job", "run_tiktokshop_job"]
