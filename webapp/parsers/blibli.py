"""
Blibli product card parser.
Extracts product data from BeautifulSoup elements.
"""
import re
from typing import Optional


def parse_product_card(box) -> Optional[dict]:
    """Parse a single Blibli product card from BeautifulSoup element.

    Tries the thorough extractor from test_full_scrape first,
    falls back to local parsing if not available.

    Args:
        box: BeautifulSoup element (typically <a class="elf-product-card">)

    Returns:
        Product dict or None if parsing fails
    """
    try:
        # Try using the thorough extractor from test module
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tests" / "blibli"))
        from test_full_scrape import extract_product_thorough
        result = extract_product_thorough(box)
        if result:
            return result
    except (ImportError, Exception):
        pass

    # Fallback: local parsing
    return _parse_local(box)


def _parse_local(box) -> Optional[dict]:
    """Local fallback parser for Blibli product cards.

    Args:
        box: BeautifulSoup element

    Returns:
        Product dict or None
    """
    product = {}

    # Name
    name_el = box.find("span", class_=re.compile(r"product.*title|els-product__title"))
    if not name_el:
        name_el = box.find("p", class_=re.compile(r"product.*name|title"))
    if name_el:
        product["nama_produk"] = name_el.get_text(strip=True)[:150]
    else:
        title = box.get("title") or box.get("aria-label") or ""
        if title:
            product["nama_produk"] = title[:150]

    if not product.get("nama_produk"):
        return None

    # Price
    price_el = box.find("div", class_=re.compile(r"fixed.*price|els-product__fixed-price"))
    if not price_el:
        price_el = box.find("span", class_=re.compile(r"price|harga"))
    if price_el:
        price_text = price_el.get_text(strip=True)
        product["harga"] = price_text
        digits = re.sub(r"[^\d]", "", price_text)
        if digits:
            product["harga_angka"] = int(digits)

    # Original price (before discount)
    orig_el = box.find("span", class_=re.compile(r"slash.*price|original.*price|strikethrough"))
    if orig_el:
        product["harga_sebelum_diskon"] = orig_el.get_text(strip=True)

    # Rating
    rating_el = box.find("span", class_=re.compile(r"rating"))
    if rating_el:
        try:
            product["rating"] = float(rating_el.get_text(strip=True))
        except (ValueError, TypeError):
            pass

    # Sold count
    sold_el = box.find("span", class_=re.compile(r"sold|terjual"))
    if sold_el:
        sold_text = sold_el.get_text(strip=True)
        sold_digits = re.sub(r"[^\d]", "", sold_text)
        if sold_digits:
            product["terjual"] = int(sold_digits)

    # Seller
    seller_el = box.find("span", class_=re.compile(r"merchant|seller|store"))
    if seller_el:
        product["penjual"] = seller_el.get_text(strip=True)

    # Location
    loc_el = box.find("span", class_=re.compile(r"location|kota"))
    if loc_el:
        product["kota"] = loc_el.get_text(strip=True)

    # Link
    href = box.get("href", "")
    if href:
        if not href.startswith("http"):
            href = "https://www.blibli.com" + href
        product["link"] = href

    # Image
    img_el = box.find("img")
    if img_el:
        product["gambar"] = img_el.get("src") or img_el.get("data-src") or ""

    # Badge (official store, etc.)
    badge_el = box.find("span", class_=re.compile(r"badge"))
    if badge_el:
        product["badge"] = badge_el.get_text(strip=True)

    return product
