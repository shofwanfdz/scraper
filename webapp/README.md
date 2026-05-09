# 🕷️ Scraping Tools - Web UI

## Cara Menjalankan

```bash
cd c:\xampp\htdocs\scraping
.\venv\Scripts\activate
python webapp/server.py
```

Buka browser: **http://localhost:8000**

## Halaman

| URL | Fungsi |
|-----|--------|
| `/` | Home - Pilih marketplace |
| `/scrape/blibli` | Form scraping Blibli |
| `/scrape/shopee` | Form scraping Shopee |
| `/results` | Daftar hasil & download |

## Flow Penggunaan

### Blibli (Full Otomatis):
1. Buka http://localhost:8000
2. Klik "Blibli"
3. Isi keyword, filter, pilih mode (cepat/lengkap)
4. Klik "Mulai Scraping"
5. Tunggu progress selesai
6. Download Excel

### Shopee (Semi-Otomatis):
1. **Setup (1x saja)**: Jalankan di terminal:
   ```bash
   python tests/shopee/test_shopee_v2.py setup
   ```
   Login Google + Shopee di browser yang terbuka.

2. Buka http://localhost:8000
3. Klik "Shopee"
4. Isi keyword & filter
5. Klik "Mulai Scraping"
6. Jika CAPTCHA muncul → selesaikan di browser scraper → klik "Konfirmasi" di web
7. Download Excel

## Mode Scraping

| Mode | Deskripsi | Kecepatan |
|------|-----------|-----------|
| ⚡ Cepat | Seller individu = "Seller Individu" | ~1 menit/halaman |
| 🔍 Lengkap | Buka detail page untuk nama seller asli | +5-7 detik/seller |

## Filter yang Tersedia

### Blibli:
- Keyword, Halaman, Mode
- Harga min/max
- Rating minimum
- Lokasi (provinsi)
- Sort (relevan/terbaru/termurah/termahal/terlaris)

### Shopee:
- Keyword, Halaman
- Harga min/max
- Rating minimum
- Sort (relevancy/ctime/sales/price)

## Output

Hasil disimpan di:
- `hasil/blibli/*.xlsx` — dengan 9 sheet analytics + 21 charts
- `hasil/shopee/*.xlsx` — data produk

## Arsitektur

```
Browser User (localhost:8000)
    ↕ WebSocket (real-time)
FastAPI Backend
    ↕ Control
Chrome Scraper (undetected-chromedriver)
    ↕ HTTP
Target Website (Blibli/Shopee)
```
