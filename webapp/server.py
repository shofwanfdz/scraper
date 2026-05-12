"""
Web Application Server - Main entry point
FastAPI + WebSocket for real-time scraping control

Run: python webapp/server.py
Access: http://localhost:9000
"""
import asyncio
import json
import os
import sys
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent))

app = FastAPI(title="Scraping Tools", version="2.0")

# Static files & templates
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Global state for scraping jobs
active_jobs = {}
message_queues = {}  # job_id -> Queue (for thread-safe messaging)

# Initialize shared state in jobs module
from webapp.jobs.base import init_globals
init_globals(active_jobs, message_queues)

# Import job runners
from webapp.jobs.blibli import run_blibli_job as _run_blibli
from webapp.jobs.shopee import run_shopee_job as _run_shopee
from webapp.jobs.base import BrowserEngine


# ============================================================
# PAGES
# ============================================================

@app.get("/")
async def home(request: Request):
    """Home page - marketplace selection"""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/scrape/{marketplace}")
async def scrape_page(request: Request, marketplace: str):
    """Scraping form page"""
    return templates.TemplateResponse(request=request, name="scrape.html", context={"marketplace": marketplace})


@app.get("/results")
async def results_page(request: Request):
    """Results/history page"""
    return templates.TemplateResponse(request=request, name="results.html")


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Interactive analytics dashboard"""
    return templates.TemplateResponse(request=request, name="dashboard.html")


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/api/results")
async def get_results():
    """Get list of all scraping result files"""
    hasil_dir = Path(__file__).parent.parent / "hasil"
    files = []
    for marketplace in ["blibli", "shopee"]:
        mp_dir = hasil_dir / marketplace
        if mp_dir.exists():
            for f in sorted(mp_dir.glob("*.xlsx"), key=os.path.getmtime, reverse=True):
                if not f.name.startswith("~$"):
                    files.append({
                        "name": f.name,
                        "marketplace": marketplace,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "path": str(f),
                    })
    return {"files": files}


@app.get("/api/download/{marketplace}/{filename}")
async def download_file(marketplace: str, filename: str):
    """Download a result file"""
    filepath = Path(__file__).parent.parent / "hasil" / marketplace / filename
    if filepath.exists():
        return FileResponse(filepath, filename=filename)
    return JSONResponse({"error": "File not found"}, status_code=404)


@app.get("/api/dashboard-data/{marketplace}/{filename}")
async def get_dashboard_data(marketplace: str, filename: str):
    """Get product data as JSON for dashboard charts - complete analytics"""
    import pandas as pd
    import numpy as np
    import re as re_mod
    import math

    filepath = Path(__file__).parent.parent / "hasil" / marketplace / filename
    if not filepath.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)

    try:
        df = pd.read_excel(str(filepath), sheet_name="Products")

        # Rename columns that were renamed in the Products sheet export
        # File baru: SKU→item_id, Total Favorit→liked_count, Jumlah Ulasan→comment_count
        col_rename = {
            "SKU": "item_id",
            "Total Favorit": "liked_count",
            "Jumlah Ulasan": "comment_count",
        }
        # Normalize: API mode uses "nama", stealth mode uses "nama_produk"
        if "nama" in df.columns and "nama_produk" not in df.columns:
            col_rename["nama"] = "nama_produk"
        df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns}, inplace=True)

        # Ensure harga_angka exists
        if "harga_angka" not in df.columns and "harga" in df.columns:
            df["harga_angka"] = df["harga"].apply(
                lambda x: int(re_mod.sub(r"[^\d]", "", str(x))) if pd.notna(x) and re_mod.search(r"\d", str(x)) else None)
        df["harga_angka"] = pd.to_numeric(df.get("harga_angka"), errors="coerce")

        # Ensure terjual & rating numeric
        if "terjual" in df.columns:
            df["terjual"] = pd.to_numeric(df["terjual"], errors="coerce")
        if "rating" in df.columns:
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

        # Extract brand if not present
        if "brand" not in df.columns and "nama_produk" in df.columns:
            known_brands = ["ASUS", "HP", "Lenovo", "Acer", "Dell", "MSI", "Apple", "MacBook",
                           "Samsung", "Toshiba", "Axioo", "Polytron", "Infinix", "Realme",
                           "Xiaomi", "OPPO", "Vivo", "Huawei", "Sony", "LG",
                           "Adidas", "Nike", "Puma", "New Balance", "Asics", "Converse",
                           "Logitech", "Razer", "SteelSeries", "Corsair",
                           "Canon", "Nikon", "Fujifilm", "Philips", "Panasonic", "Sharp"]
            def get_brand(name):
                if not name or not isinstance(name, str):
                    return "Lainnya"
                for b in known_brands:
                    if b.upper() in name.upper():
                        if b.upper() == "MACBOOK":
                            return "Apple"
                        return b.upper() if len(b) <= 4 else b
                return "Lainnya"
            df["brand"] = df["nama_produk"].apply(get_brand)

        # Compute diskon_persen
        if "harga_sebelum_diskon" in df.columns:
            df["harga_asli_angka"] = df["harga_sebelum_diskon"].apply(
                lambda x: int(re_mod.sub(r"[^\d]", "", str(x))) if pd.notna(x) and re_mod.search(r"\d", str(x)) else None)
            df["harga_asli_angka"] = pd.to_numeric(df["harga_asli_angka"], errors="coerce")
            mask = df["harga_angka"].notna() & df["harga_asli_angka"].notna() & (df["harga_asli_angka"] > 0)
            df["diskon_persen"] = None
            df.loc[mask, "diskon_persen"] = round(
                (1 - df.loc[mask, "harga_angka"] / df.loc[mask, "harga_asli_angka"]) * 100, 1)
        else:
            df["diskon_persen"] = None

        # Compute value_score (legacy, kept for compatibility)
        terjual_safe = pd.to_numeric(df.get("terjual"), errors="coerce").fillna(0)
        rating_safe = pd.to_numeric(df.get("rating"), errors="coerce").fillna(0)
        harga_safe = df["harga_angka"].fillna(1)
        df["value_score"] = round((rating_safe * (terjual_safe + 1)) / (harga_safe / 1e6), 2)
        df.loc[harga_safe <= 0, "value_score"] = 0

        # =====================================================
        # DYNAMIC RECOMMENDATION SCORE (normalized 0-100)
        # =====================================================
        def norm(series, higher=True):
            if not isinstance(series, pd.Series):
                series = pd.Series(series, index=df.index)
            mn, mx = series.min(), series.max()
            if mx == mn or pd.isna(mx) or pd.isna(mn):
                return pd.Series(50, index=series.index)
            normed = (series - mn) / (mx - mn) * 100
            return normed if higher else (100 - normed)

        terjual_s = pd.to_numeric(df.get("terjual", pd.Series(dtype=float)), errors="coerce").fillna(0)
        rating_s = pd.to_numeric(df.get("rating", pd.Series(dtype=float)), errors="coerce").fillna(0)
        harga_s = pd.to_numeric(df["harga_angka"], errors="coerce").fillna(1)
        harga_s = harga_s.where(harga_s != 0, 1)  # avoid div by zero — stays Series
        liked_s = pd.to_numeric(df.get("liked_count", pd.Series(dtype=float)), errors="coerce").fillna(0)
        comment_s = pd.to_numeric(df.get("comment_count", pd.Series(dtype=float)), errors="coerce").fillna(0)
        diskon_s = pd.to_numeric(df.get("diskon_persen", pd.Series(dtype=float)), errors="coerce").fillna(0)
        stock_s = pd.to_numeric(df.get("stock", pd.Series(dtype=float)), errors="coerce").fillna(0)

        df["r_terjual"] = norm(terjual_s)
        df["r_rating"] = norm(rating_s)
        df["r_harga"] = norm(harga_s, higher=False)  # cheaper = higher score
        df["r_liked"] = norm(liked_s)
        df["r_comment"] = norm(comment_s)
        df["r_diskon"] = norm(diskon_s)
        df["r_stock"] = norm(stock_s)

        df["rekomendasi_score"] = round(
            df["r_terjual"] * 0.30
            + df["r_rating"] * 0.15
            + df["r_harga"] * 0.15
            + df["r_liked"] * 0.15
            + df["r_diskon"] * 0.10
            + df["r_comment"] * 0.10
            + df["r_stock"] * 0.05,
            2
        )

        # Engagement score (liked + comment combined)
        df["engagement_score"] = (liked_s + comment_s).round(0).astype("Int64")

        # Dynamic price segment based on percentiles
        harga_clean = harga_s[harga_s > 0]
        if len(harga_clean) >= 4:
            p25 = float(harga_clean.quantile(0.25))
            p75 = float(harga_clean.quantile(0.75))
        else:
            p25 = float(harga_clean.median()) if len(harga_clean) else 5000000.0
            p75 = p25 * 3

        def price_segment(h):
            if pd.isna(h) or h <= 0:
                return "Lainnya"
            if h < p25:
                return "Budget"
            elif h <= p75:
                return "Mid-Range"
            else:
                return "Premium"

        df["price_segment"] = df["harga_angka"].apply(price_segment)

        # Convert to JSON-safe format (handle NaN, inf, -inf)
        df = df.replace([np.inf, -np.inf], None)
        df = df.where(pd.notnull(df), None)
        products = df.to_dict(orient="records")

        # Extra safety: replace any remaining float NaN in nested values
        def sanitize(obj):
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            return obj

        products = [{k: sanitize(v) for k, v in row.items()} for row in products]

        return {"products": products, "total": len(products), "marketplace": marketplace}

    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/scrape/confirm/{job_id}")
async def confirm_action(job_id: str):
    """User confirms action (CAPTCHA solved, login done, etc.)"""
    if job_id in active_jobs:
        active_jobs[job_id]["confirmed"] = True
        return {"status": "confirmed"}
    return JSONResponse({"error": "Job not found"}, status_code=404)


# ============================================================
# WEBSOCKET - Real-time scraping
# ============================================================

@app.websocket("/ws/scrape")
async def websocket_scrape(websocket: WebSocket):
    """WebSocket endpoint for real-time scraping control"""
    await websocket.accept()
    job_id = datetime.now().strftime("%Y%m%d%H%M%S")
    msg_queue = queue.Queue()
    message_queues[job_id] = msg_queue
    active_jobs[job_id] = {"confirmed": False, "status": "idle"}

    try:
        # Start a task to forward messages from queue to websocket
        async def forward_messages():
            while True:
                try:
                    msg = msg_queue.get_nowait()
                    await websocket.send_text(msg)
                except queue.Empty:
                    pass
                await asyncio.sleep(0.3)

        forward_task = asyncio.create_task(forward_messages())

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                msg = json.loads(data)
                action = msg.get("action")

                if action == "start_scrape":
                    marketplace = msg.get("marketplace", "blibli")
                    keyword = msg.get("keyword", "laptop")
                    pages = msg.get("pages", 1)
                    mode = msg.get("mode", "cepat")
                    filters = msg.get("filters", {})
                    engine = msg.get("engine", "api")

                    thread = threading.Thread(
                        target=run_scraping_job,
                        args=(job_id, marketplace, keyword, pages, mode, filters, engine),
                        daemon=True,
                    )
                    thread.start()

                elif action == "confirm":
                    active_jobs[job_id]["confirmed"] = True

            except asyncio.TimeoutError:
                # Normal - just continue to forward messages
                pass

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        forward_task.cancel()
        message_queues.pop(job_id, None)
        active_jobs.pop(job_id, None)


def send_ws_message(job_id: str, msg_type: str, data: dict):
    """Send message to WebSocket client (thread-safe via queue)"""
    q = message_queues.get(job_id)
    if q:
        message = json.dumps({"type": msg_type, **data})
        q.put(message)


def wait_for_confirmation(job_id: str, timeout: int = 300) -> bool:
    """Wait for user confirmation via WebSocket (blocking, called from thread)"""
    active_jobs[job_id]["confirmed"] = False
    import time
    elapsed = 0
    while elapsed < timeout:
        if active_jobs.get(job_id, {}).get("confirmed"):
            active_jobs[job_id]["confirmed"] = False
            return True
        time.sleep(1)
        elapsed += 1
    return False


# ============================================================
# SCRAPING JOB RUNNER
# ============================================================

def run_scraping_job(job_id, marketplace, keyword, pages, mode, filters, engine="api"):
    """Run scraping job in background thread"""
    import time

    # Map engine string to BrowserEngine enum
    engine_map = {
        "api": BrowserEngine.API,
        "cloak": BrowserEngine.CLOAKBROWSER,
        "uc": BrowserEngine.UNDETECTED_CHROME,
    }
    browser_engine = engine_map.get(engine, BrowserEngine.API)

    try:
        engine_label = {"api": "API Direct", "cloak": "CloakBrowser Stealth", "uc": "Undetected Chrome"}.get(engine, engine)
        send_ws_message(job_id, "status", {"message": "[{}] Memulai proses scraping (engine: {})...".format(marketplace.upper(), engine_label)})

        if marketplace == "blibli":
            result = _run_blibli(job_id, keyword, pages, mode, filters, engine=browser_engine)
        elif marketplace == "shopee":
            result = _run_shopee(job_id, keyword, pages, mode, filters)
        else:
            send_ws_message(job_id, "error", {"message": "Marketplace tidak dikenal"})
            return

        if result:
            send_ws_message(job_id, "complete", {
                "message": "Selesai! {} produk".format(result.get("total", 0)),
                "file": result.get("file", ""),
                "total": result.get("total", 0),
            })
        else:
            send_ws_message(job_id, "error", {"message": "Scraping gagal"})

    except Exception as e:
        send_ws_message(job_id, "error", {"message": str(e)[:100]})


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  Scraping Tools Web UI")
    print("  http://localhost:9000")
    print("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=9000)
