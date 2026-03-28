"""Amazon price scraping via Playwright (sync API)."""

import re
import time


def _check_session_expired(page):
    """Check if the current page indicates a session expiry."""
    url = page.url.lower()
    return any(keyword in url for keyword in ("signin", "login", "auth"))


def set_location(page, pincode):
    """Navigate to amazon.in and ensure delivery location is set to pincode.

    Returns True on success. Raises RuntimeError on failure.
    Raises ValueError if pincode is not a 6-digit string.
    """
    if not (isinstance(pincode, str) and pincode.isdigit() and len(pincode) == 6):
        raise ValueError(f"pincode must be a 6-digit string, got: {pincode!r}")

    page.goto("https://www.amazon.in", wait_until="domcontentloaded", timeout=30000)

    if _check_session_expired(page):
        raise RuntimeError("Amazon session expired — please re-login in the browser profile.")

    # Check if location already set
    try:
        location_text = page.locator("#glow-ingress-line2").text_content(timeout=5000) or ""
        if pincode in location_text:
            return True
    except Exception:
        pass

    # Click location widget to open the popup
    try:
        page.locator("#nav-global-location-popover-link").click(timeout=5000)
        time.sleep(1)
    except Exception:
        raise RuntimeError("Could not open Amazon location widget")

    # Enter pincode
    try:
        pincode_input = page.locator("#GLUXZipUpdateInput")
        pincode_input.fill("", timeout=5000)
        pincode_input.fill(pincode)
        page.locator(
            "#GLUXZipUpdate input[type='submit'], #GLUXZipUpdate .a-button-input"
        ).first.click(timeout=5000)
        time.sleep(2)
    except Exception:
        raise RuntimeError(f"Could not enter pincode {pincode} on Amazon")

    # Try to confirm / close the popup
    try:
        done_button = page.locator(
            "#GLUXConfirmClose, .a-popover-footer .a-button-input"
        )
        if done_button.count() > 0:
            done_button.first.click(timeout=3000)
            time.sleep(1)
    except Exception:
        pass

    # Verify location was set
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
        location_text = page.locator("#glow-ingress-line2").text_content(timeout=5000) or ""
        if pincode in location_text or "gurugram" in location_text.lower() or "gurgaon" in location_text.lower():
            return True
    except Exception:
        pass

    raise RuntimeError(
        f"Could not verify pincode {pincode} was set on Amazon — "
        "location widget may have changed structure"
    )


def search_items(page, query):
    """Search for items on Amazon.in.

    Types query in search bar, submits, waits for results page to load.
    Raises RuntimeError if session has expired.
    """
    if _check_session_expired(page):
        raise RuntimeError("Amazon session expired — please re-login in the browser profile.")

    search_box = page.locator("#twotabsearchtextbox")
    search_box.fill("", timeout=5000)
    search_box.fill(query)
    search_box.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=30000)
    time.sleep(2)

    if _check_session_expired(page):
        raise RuntimeError("Amazon session expired — please re-login in the browser profile.")


def extract_results(page):
    """Extract product candidates from Amazon search results page.

    Returns list of dicts: {"name": str, "price": float, "brand": str, "unit": str, "url": str}.
    Skips sponsored results and results with no visible price.
    """
    results = []
    result_cards = page.locator("div[data-component-type='s-search-result']")
    count = result_cards.count()

    for i in range(min(count, 20)):
        try:
            card = result_cards.nth(i)

            # Skip sponsored results
            sponsored = card.locator("span.puis-label-popover-default, span.a-color-secondary:has-text('Sponsored')")
            if sponsored.count() > 0:
                try:
                    label_text = sponsored.first.text_content(timeout=500) or ""
                    if "sponsored" in label_text.lower():
                        continue
                except Exception:
                    pass

            # Extract product name from product link text
            name_elem = card.locator("a.a-link-normal.s-line-clamp-3")
            if name_elem.count() == 0:
                name_elem = card.locator("h2 span")
            if name_elem.count() == 0:
                continue
            name = (name_elem.first.text_content(timeout=1000) or "").strip()
            if not name:
                continue

            # Extract price (whole part)
            price_whole = card.locator(".a-price:not(.a-text-price) .a-price-whole")
            if price_whole.count() == 0:
                continue
            price_text = (price_whole.first.text_content(timeout=1000) or "").replace(",", "").replace(".", "").strip()
            if not price_text:
                continue
            try:
                price = float(price_text)
            except ValueError:
                continue

            # Extract URL
            url = ""
            url_elem = card.locator("a.a-link-normal.s-line-clamp-3, a[href*='/dp/']")
            if url_elem.count() > 0:
                url = url_elem.first.get_attribute("href", timeout=1000) or ""
                if url and not url.startswith("http"):
                    url = "https://www.amazon.in" + url

            # Extract brand from secondary text below the title
            brand = _extract_brand(card)

            # Extract unit from the product name
            unit = ""
            unit_match = re.search(
                r'(\d+\s*(?:kg|g|ml|l|lb|oz|ltr|litre|liter|pack|pcs|pieces?))\b',
                name, re.IGNORECASE,
            )
            if unit_match:
                unit = unit_match.group(1).strip()

            results.append({
                "name": name,
                "price": price,
                "brand": brand,
                "unit": unit,
                "url": url,
            })
        except Exception:
            continue

    return results


def _extract_brand(card):
    """Try to extract brand name from a search result card.

    Checks for a dedicated brand h2 (new Amazon layout), then falls back
    to the legacy "by BrandName" / "Visit the BrandName Store" patterns.
    """
    # Primary: dedicated brand h2 (new Amazon layout for brand-filtered searches)
    brand_h2 = card.locator("h2.a-size-mini span")
    if brand_h2.count() > 0:
        try:
            text = (brand_h2.first.text_content(timeout=500) or "").strip()
            if text:
                return text
        except Exception:
            pass

    # Fallback: legacy secondary text patterns
    by_elem = card.locator("span.a-size-base.a-color-secondary")
    for j in range(min(by_elem.count(), 5)):
        try:
            text = (by_elem.nth(j).text_content(timeout=500) or "").strip()
            tl = text.lower()
            if tl.startswith("by "):
                return text[3:].strip()
            if tl.startswith("visit the ") and tl.endswith(" store"):
                return text[10:-6].strip()
            if tl.startswith("brand:"):
                return text[6:].strip()
        except Exception:
            continue
    return ""


def discover_fees_amazon(page):
    """Read delivery fee and cashback information from the current Amazon page.

    Returns fee dict with keys: delivery_fee, handling_fee, free_delivery_threshold, cashback_tiers.
    Returns {"status": "session_expired"} if session is expired.
    """
    if _check_session_expired(page):
        return {"status": "session_expired", "platform": "amazon"}

    fees = {
        "delivery_fee": 40,
        "handling_fee": 0,
        "free_delivery_threshold": 99.0,
        "cashback_tiers": [],
    }

    try:
        page_text = page.locator("body").text_content(timeout=5000) or ""
    except Exception:
        return fees

    # Look for free delivery threshold
    threshold_patterns = [
        r'(?:free|FREE)\s+delivery\s+(?:on\s+orders?\s+)?(?:over|above)\s+₹?\s*(\d[\d,]*)',
        r'₹?\s*(\d[\d,]*)\s+(?:and\s+above|or\s+more)\s+(?:for\s+)?free\s+delivery',
    ]
    for pattern in threshold_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            fees["free_delivery_threshold"] = float(match.group(1).replace(",", ""))
            break

    # Look for delivery fee below threshold (e.g., "₹40 delivery fee")
    delivery_fee_patterns = [
        r'₹\s*(\d[\d,]*)\s+delivery\s+fee',
        r'delivery\s+fee\s+(?:of\s+)?₹\s*(\d[\d,]*)',
        r'₹\s*(\d[\d,]*)\s+shipping',
    ]
    for pattern in delivery_fee_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            fees["delivery_fee"] = float(match.group(1).replace(",", ""))
            break

    # Look for cashback tiers
    # Pattern: "₹50 cashback on orders above ₹399"
    for match in re.finditer(
        r'₹\s*(\d[\d,]*)\s+(?:cashback|back|off)\s+(?:on\s+(?:orders?\s+)?)?(?:above|over)\s+₹?\s*(\d[\d,]*)',
        page_text, re.IGNORECASE,
    ):
        fees["cashback_tiers"].append({
            "min_order": float(match.group(2).replace(",", "")),
            "cashback": float(match.group(1).replace(",", "")),
        })

    return fees
