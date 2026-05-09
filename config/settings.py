"""
Global Settings for Scraping Tools
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database
DATABASE = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "name": os.getenv("DB_NAME", "scraping_db"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
}

DATABASE_URL = (
    f"mysql+mysqlconnector://{DATABASE['user']}:{DATABASE['password']}"
    f"@{DATABASE['host']}:{DATABASE['port']}/{DATABASE['name']}"
)

# Scraping Defaults
SCRAPING = {
    "delay_min": float(os.getenv("DEFAULT_DELAY_MIN", 1)),
    "delay_max": float(os.getenv("DEFAULT_DELAY_MAX", 3)),
    "max_concurrent": int(os.getenv("MAX_CONCURRENT_REQUESTS", 5)),
    "max_retries": int(os.getenv("MAX_RETRIES", 3)),
    "timeout": 30,
    "respect_robots_txt": True,
}

# Proxy Settings
PROXY = {
    "enabled": bool(os.getenv("PROXY_LIST_URL")),
    "list_url": os.getenv("PROXY_LIST_URL", ""),
    "api_key": os.getenv("PROXY_API_KEY", ""),
    "rotation_interval": 10,  # requests before rotating
}

# CAPTCHA Settings
CAPTCHA = {
    "enabled": bool(os.getenv("CAPTCHA_API_KEY")),
    "api_key": os.getenv("CAPTCHA_API_KEY", ""),
    "service": os.getenv("CAPTCHA_SERVICE", "2captcha"),
}

# Application
APP = {
    "host": os.getenv("APP_HOST", "0.0.0.0"),
    "port": int(os.getenv("APP_PORT", 8000)),
    "debug": os.getenv("APP_DEBUG", "true").lower() == "true",
}

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Export
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", str(BASE_DIR / "exports")))
EXPORT_DIR.mkdir(exist_ok=True)

# User Agents Pool (fallback)
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]
