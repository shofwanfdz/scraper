"""
Shopee product parsers.
Handles API JSON responses, JS DOM extraction, and HTML fallback parsing.
"""
import re
from typing import Optional


def parse_api_items(data: dict) -> list:
    """Parse Shopee search API response into product list.

    Shopee API stores prices in units of 100000 (e.g., 1500000000 = Rp15.000.000).

    Args:
        data: Raw JSON response from Shopee search_items API

    Returns:
        List of product dicts
    """
    products = []

    # Navigate to items array
    items = []
    if isinstance(data, dict):
        items = data.get("items", [])
        if not items:
            items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []
        if not items:
            # Try nested structure
            items = data.get("item", []) if isinstance(data.get("item"), list) else []

    if not items:
        return []

    for item in items:
        product = {}
        item_data = item.get("item_basic", item)

        # Name
        name = item_data.get("name", "") or item_data.get("item_name", "")
        if not name:
            continue
        product["nama_produk"] = name[:150]

        # Price (Shopee stores in units of 100000)
        price = item_data.get("price", 0)
        price_min = item_data.get("price_min", 0)
        actual_price = price // 100000 if price > 100000 else price
        if actual_price == 0 and price_min > 0:
            actual_price = price_min // 100000 if price_min > 100000 else price_min

        if actual_price > 0:
            product["harga_angka"] = actual_price
            product["harga"] = "Rp{:,.0f}".format(actual_price).replace(",", ".")

        # Original price (before discount)
        price_before = item_data.get("price_before_discount", 0)
        if price_before > 0:
            actual_before = price_before // 100000 if price_before > 100000 else price_before
            if actual_before > actual_price:
                product["harga_sebelum_diskon"] = "Rp{:,.0f}".format(actual_before).replace(",", ".")

        # Sold count
        sold = item_data.get("sold", 0) or item_data.get("historical_sold", 0)
        if sold > 0:
            product["terjual"] = sold

        # Rating
        rating = item_data.get("item_rating", {})
        if isinstance(rating, dict):
            avg = rating.get("rating_star", 0)
            if avg > 0:
                product["rating"] = round(avg, 1)

        # Location
        location = item_data.get("shop_location", "") or item_data.get("item_location", "")
        if location:
            product["kota"] = location

        # Seller
        shop_name = item_data.get("shop_name", "")
        if not shop_name:
            if item_data.get("is_official_shop"):
                shop_name = "Official Shop"
            elif item_data.get("shopee_verified"):
                shop_name = "Shopee Mall"
        if shop_name:
            product["penjual"] = shop_name

        # Image
        image = item_data.get("image", "")
        if image and not image.startswith("http"):
            image = "https://cf.shopee.co.id/file/" + image
        product["gambar"] = image

        # Item ID
        item_id = item_data.get("itemid", "") or item_data.get("item_id", "")
        if item_id:
            product["item_id"] = str(item_id)

        # Stock
        stock = item_data.get("stock", 0)
        if stock is None:
            stock = 0
        if stock > 0:
            product["stock"] = int(stock)

        # Liked count
        liked = item_data.get("liked_count", 0) or item_data.get("n_like", 0)
        if liked and liked > 0:
            product["liked_count"] = int(liked)

        # Comment count
        cmt = item_data.get("cmt_count", 0) or item_data.get("comment_count", 0)
        if cmt and cmt > 0:
            product["comment_count"] = int(cmt)

        # Free shipping
        if item_data.get("is_free_shipping", False):
            product["free_shipping"] = "Ya"

        # Seller type
        if item_data.get("is_official_shop", False):
            product["seller_type"] = "Official"
        elif item_data.get("shopee_verified", False):
            product["seller_type"] = "Verified"
        elif item_data.get("is_shopee_verified", False):
            product["seller_type"] = "Verified"
        else:
            if item_data.get("is_preferred_plus_seller", False):
                product["seller_type"] = "Preferred"
            elif item_data.get("is_mall", 0) or item_data.get("is_official", 0):
                product["seller_type"] = "Mall"

        # Flash sale
        if item_data.get("flash_sale", False) or item_data.get("is_flash_sale", False):
            product["flash_sale"] = "Ya"
        elif item_data.get("badge_interaction", {}).get("flash_sale", False):
            product["flash_sale"] = "Ya"

        # Link
        shop_id = item_data.get("shopid", "") or item_data.get("shop_id", "")
        if item_id and shop_id:
            slug = name.replace(" ", "-").replace("/", "-")[:80]
            product["link"] = "https://shopee.co.id/{}-i.{}.{}".format(slug, shop_id, item_id)

        products.append(product)

    return products


def extract_via_js_script() -> str:
    """Return the JavaScript snippet for DOM-based product extraction.

    This JS runs in the browser context and extracts products from
    Shopee's rendered DOM when API intercept fails.

    Returns:
        JavaScript code string to be executed via page.evaluate() or driver.execute_script()
    """
    return """
        var products = [];
        var links = document.querySelectorAll('a[href*="-i."]');
        var seen = new Set();
        for (var i = 0; i < links.length; i++) {
            var link = links[i];
            var href = link.getAttribute('href') || '';
            if (seen.has(href) || !href.match(/-i\\.\\d+\\.\\d+/)) continue;
            seen.add(href);
            var card = link;
            for (var j = 0; j < 8; j++) {
                if (card.parentElement && card.parentElement.innerText &&
                    card.parentElement.innerText.length > 30 &&
                    card.parentElement.innerText.length < 3000) {
                    card = card.parentElement; break;
                }
                if (card.parentElement) card = card.parentElement;
            }
            var text = card.innerText || '';
            var lines = text.split('\\n').map(l => l.trim()).filter(l => l);
            var product = {};
            for (var k = 0; k < lines.length; k++) {
                if (lines[k].length > 10 && !/^[\\d\u20abRp$]/.test(lines[k]) &&
                    !lines[k].toLowerCase().includes('terjual') && !/%/.test(lines[k])) {
                    product.nama_produk = lines[k].substring(0, 150); break;
                }
            }
            if (!product.nama_produk) continue;
            var allElements = card.querySelectorAll('*');
            for (var k = 0; k < allElements.length; k++) {
                var el = allElements[k];
                var ariaLabel = el.getAttribute('aria-label') || '';
                if (ariaLabel && ariaLabel.match(/\\d/) && ariaLabel.length < 30) {
                    var priceMatch = ariaLabel.replace(/[^\\d]/g, '');
                    if (priceMatch && parseInt(priceMatch) > 1000) {
                        product.harga_angka = parseInt(priceMatch);
                        product.harga = 'Rp' + parseInt(priceMatch).toLocaleString('id-ID');
                        break;
                    }
                }
            }
            for (var k = 0; k < lines.length; k++) {
                if (lines[k].toLowerCase().includes('terjual')) {
                    var soldText = lines[k].toLowerCase().replace('terjual', '').replace('+', '').trim();
                    var mult = soldText.includes('rb') ? 1000 : 1;
                    soldText = soldText.replace('rb', '').replace(',', '.').trim();
                    var soldNum = parseFloat(soldText);
                    if (!isNaN(soldNum)) product.terjual = Math.round(soldNum * mult);
                    break;
                }
            }
            var locKw = ['Jakarta', 'Bandung', 'Surabaya', 'Bekasi', 'Tangerang', 'Bogor'];
            for (var k = lines.length - 1; k >= 0; k--) {
                if (lines[k].length < 40 && locKw.some(l => lines[k].includes(l))) {
                    product.kota = lines[k]; break;
                }
            }
            product.link = href.startsWith('http') ? href : 'https://shopee.co.id' + href;
            var img = link.querySelector('img');
            if (img) product.gambar = img.src || '';
            products.push(product);
        }
        return products;
    """


def parse_product_from_html(link_el) -> Optional[dict]:
    """Parse a Shopee product from a BeautifulSoup link element (legacy fallback).

    Used when both API intercept and JS extraction fail.

    Args:
        link_el: BeautifulSoup <a> element with href matching /-i.\\d+.\\d+/

    Returns:
        Product dict or None
    """
    card = link_el
    for _ in range(6):
        if card.parent:
            text = card.parent.get_text(separator="|", strip=True)
            if "Rp" in text and len(text) > 30 and len(text) < 2000:
                card = card.parent
                break
            card = card.parent

    all_text = card.get_text(separator="|", strip=True)
    segments = [s.strip() for s in all_text.split("|") if s.strip()]
    product = {}

    # Name
    for seg in segments:
        if (len(seg) > 10 and not seg.startswith("Rp") and
            "terjual" not in seg.lower() and "%" not in seg and
            not re.match(r"^\d+[.,]?\d*$", seg) and len(seg) < 200):
            product["nama_produk"] = seg[:150]
            break
    if not product.get("nama_produk"):
        return None

    # Price
    for seg in segments:
        if seg.startswith("Rp"):
            cleaned = re.sub(r"[^\d]", "", seg)
            try:
                val = int(cleaned)
                if val > 1000:
                    product["harga_angka"] = val
                    product["harga"] = "Rp{:,.0f}".format(val).replace(",", ".")
                    break
            except ValueError:
                pass

    # Sold
    for seg in segments:
        if "terjual" in seg.lower():
            sold_text = seg.lower().replace("terjual", "").replace("+", "").strip()
            multiplier = 1000 if "rb" in sold_text else 1
            sold_text = sold_text.replace("rb", "").replace(",", ".").strip()
            try:
                product["terjual"] = int(float(sold_text) * multiplier)
            except (ValueError, TypeError):
                pass
            break

    # Rating
    for seg in segments:
        if re.match(r"^\d\.\d$", seg):
            try:
                val = float(seg)
                if 0 < val <= 5:
                    product["rating"] = val
                    break
            except ValueError:
                pass

    # Location
    loc_kw = ["Jakarta", "Bandung", "Surabaya", "Bekasi", "Tangerang",
              "Semarang", "Depok", "Bogor"]
    for seg in segments:
        if any(loc in seg for loc in loc_kw) and len(seg) < 40:
            product["kota"] = seg
            break

    # Link
    href = link_el.get("href", "")
    if not href.startswith("http"):
        href = "https://shopee.co.id" + href
    product["link"] = href

    return product
