# 🕷️ Scraping Tools 

Automated web scraping tools with anti-detection capabilities, built with Python.

## ✨ Features

- **Multi-category scrapers**: E-commerce, Jobs, News, Property
- **Anti-detection system**: User-Agent rotation, header randomization, honeypot detection
- **Proxy management**: Rotation, health checking, failover
- **Rate limiting**: Intelligent throttling with human-like patterns
- **Browser engine**: Playwright-based for JavaScript-heavy sites
- **robots.txt compliance**: Automatic respect for crawling rules
- **Database storage**: MySQL with SQLAlchemy ORM
- **REST API**: FastAPI with auto-generated docs
- **Multiple export formats**: CSV, JSON, Excel
- **CLI interface**: Rich terminal UI with progress tracking

## 📁 Project Structure

```
scraping/
├── main.py                 # CLI entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── setup_database.sql     # MySQL setup script
├── config/
│   ├── __init__.py
│   └── settings.py        # Global configuration
├── core/
│   ├── __init__.py
│   ├── engine.py          # Main scraping engine (HTTP)
│   ├── browser.py         # Playwright browser engine
│   ├── anti_detection.py  # Anti-bot evasion
│   ├── proxy_manager.py   # Proxy rotation
│   ├── rate_limiter.py    # Request throttling
│   └── robots_parser.py   # robots.txt compliance
├── scrapers/
│   ├── __init__.py
│   ├── base.py            # Abstract base scraper
│   ├── ecommerce.py       # E-commerce product scraper
│   ├── jobs_scraper.py    # Job listing scraper
│   ├── news_scraper.py    # News article scraper
│   └── property_scraper.py # Real estate scraper
├── database/
│   ├── __init__.py
│   ├── connection.py      # DB connection manager
│   ├── models.py          # SQLAlchemy models
│   └── repository.py      # Data access layer
├── exporters/
│   ├── __init__.py
│   ├── csv_exporter.py
│   ├── json_exporter.py
│   └── excel_exporter.py
├── api/
│   ├── __init__.py
│   └── main.py            # FastAPI REST API
├── exports/               # Exported files
└── logs/                  # Log files
```

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- MySQL (via XAMPP)
- Git

### 2. Setup

```bash
# Navigate to project
cd c:\xampp\htdocs\scraping

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for JS-heavy sites)
playwright install chromium

# Copy environment file
copy .env.example .env

# Create database (via phpMyAdmin or MySQL CLI)
mysql -u root < setup_database.sql

# Initialize database tables
python main.py init-db
```

### 3. Usage

#### CLI Commands

```bash
# Scrape e-commerce products
python main.py scrape --type ecommerce --url "https://example.com/products" --pages 3

# Scrape job listings
python main.py scrape --type jobs --url "https://example.com/jobs" --pages 2

# Scrape news articles
python main.py scrape --type news --url "https://example.com/news" --pages 5

# Scrape property listings
python main.py scrape --type property --url "https://example.com/properties"

# Scrape with browser (for JavaScript sites)
python main.py scrape --type ecommerce --url "https://example.com" --browser

# Scrape and export directly
python main.py scrape --type ecommerce --url "https://example.com" --export csv

# Export existing job data
python main.py export --job-id 1 --format excel

# View statistics
python main.py stats

# Start API server
python main.py server
```

#### REST API

```bash
# Start server
python main.py server

# API docs available at:
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/stats` | Overall statistics |
| POST | `/jobs` | Create scraping job |
| GET | `/jobs` | List all jobs |
| GET | `/jobs/{id}` | Get job details |
| DELETE | `/jobs/{id}` | Delete a job |
| GET | `/data/{job_id}` | Get scraped data |
| GET | `/data/search/{query}` | Search data |
| POST | `/export` | Export data to file |

## 🛡️ Anti-Detection Features

| Feature | Description |
|---------|-------------|
| User-Agent Rotation | Randomizes browser identity per request |
| Header Randomization | Realistic browser headers with Client Hints |
| Rate Limiting | Human-like delays with burst protection |
| Proxy Rotation | IP rotation with health monitoring |
| Honeypot Detection | Filters hidden trap elements |
| robots.txt Compliance | Respects website crawling rules |
| Stealth Browser | Playwright with anti-detection scripts |
| Fingerprint Evasion | Overrides WebDriver detection |

## ⚙️ Configuration

Edit `.env` file to customize:

```env
# Database
DB_HOST=localhost
DB_NAME=scraping_db
DB_USER=root
DB_PASSWORD=

# Rate Limiting
DEFAULT_DELAY_MIN=1
DEFAULT_DELAY_MAX=3
MAX_CONCURRENT_REQUESTS=5

# Proxy (optional)
PROXY_LIST_URL=https://your-proxy-provider.com/list
```

## 📊 Supported Data Categories

| Category | Data Points |
|----------|-------------|
| **E-Commerce** | Product name, price, rating, seller, image, discount |
| **Jobs** | Title, company, salary, location, type, requirements |
| **News** | Headline, author, date, content, category, image |
| **Property** | Title, price, location, bedrooms, area, features |

## ⚠️ Legal & Ethical Guidelines

1. ✅ Only scrape **publicly available** data
2. ✅ Respect `robots.txt` rules
3. ✅ Implement reasonable rate limits
4. ✅ Don't overload target servers
5. ❌ Don't scrape personal/private data
6. ❌ Don't bypass authentication without permission
7. ❌ Don't violate website Terms of Service

## 📝 License

MIT License - Use responsibly and ethically.