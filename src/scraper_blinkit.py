"""Blinkit price scraping via Playwright (sync API)."""

import re
import time


def _check_session_expired(page):
    """Check if the current page indicates a session expiry."""
    url = page.url.lower()
    return any(keyword in url for keyword in ("signin", "login", "auth"))


def set_location(page, pincode):
    """Navigate to blinkit.com and ensure delivery location is set to pincode.

    Returns True on success. Raises RuntimeError on failure.
    Raises ValueError if pincode is not a 6-digit string.
    """
    if not (isinstance(pincode, str) and pincode.isdigit() and len(pincode) == 6):
        raise ValueError(f"pincode must be a 6-digit string, got: {pincode!r}")

    page.goto("https://blinkit.com", wait_until="domcontentloaded", timeout=30000)

    if _check_session_expired(page):
        raise RuntimeError("Blinkit session expired — please re-login in the browser profile.")

    time.sleep(2)

    # Dismiss any modals first so we can interact with the page
    dismiss_modals(page)

    # Check if location is already set by looking for pincode in the location display
    try:
        # Blinkit shows the delivery location in the header area
        location_selectors = [
            "div[class*='LocationBar'] span",
            "div[class*='location'] span",
            "[data-testid='location-text']",
            "div.LocationBar__Title",
            ".LocationBar__Container span",
        ]
        for selector in location_selectors:
            elems = page.locator(selector)
            if elems.count() > 0:
                for j in range(min(elems.count(), 5)):
                    text = (elems.nth(j).text_content(timeout=2000) or "").strip()
                    if pincode in text or "gurugram" in text.lower() or "gurgaon" in text.lower():
                        return True
    except Exception:
        pass

    # Try to open the location modal and enter pincode
    try:
        # Click on location bar/widget to open location picker
        location_triggers = [
            "div[class*='LocationBar']",
            "[data-testid='location-bar']",
            "div[class*='location']",
            ".LocationBar__Container",
        ]
        for selector in location_triggers:
            trigger = page.locator(selector)
            if trigger.count() > 0:
                trigger.first.click(timeout=3000)
                time.sleep(1)
                break

        # Look for pincode/search input in the modal
        input_selectors = [
            "input[placeholder*='area']",
            "input[placeholder*='location']",
            "input[placeholder*='search']",
            "input[placeholder*='pincode']",
            "input[type='text'][class*='SearchBar']",
            "input[type='search']",
        ]
        input_filled = False
        for selector in input_selectors:
            inp = page.locator(selector)
            if inp.count() > 0:
                inp.first.fill("", timeout=3000)
                inp.first.fill(pincode)
                time.sleep(2)
                input_filled = True
                break

        if not input_filled:
            raise RuntimeError("Could not find location input on Blinkit")

        # Select the first suggestion / result
        suggestion_selectors = [
            "div[class*='LocationSearch'] div[class*='result']",
            "div[class*='suggestion']",
            "div[class*='SearchResult']",
            "[class*='Dropdown'] [class*='item']",
            "[class*='dropdown'] li",
        ]
        for selector in suggestion_selectors:
            suggestions = page.locator(selector)
            if suggestions.count() > 0:
                suggestions.first.click(timeout=3000)
                time.sleep(2)
                break

        # Try confirm button if present
        confirm_selectors = [
            "button:has-text('Confirm')",
            "button:has-text('confirm')",
            "button[class*='Confirm']",
        ]
        for selector in confirm_selectors:
            btn = page.locator(selector)
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                time.sleep(1)
                break

    except RuntimeError:
        raise
    except Exception:
        raise RuntimeError(f"Could not set pincode {pincode} on Blinkit — location widget may have changed")

    # Verify location was set
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
        body_text = page.locator("body").text_content(timeout=5000) or ""
        if pincode in body_text or "gurugram" in body_text.lower() or "gurgaon" in body_text.lower():
            return True
    except Exception:
        pass

    raise RuntimeError(
        f"Could not verify pincode {pincode} was set on Blinkit — "
        "location widget may have changed structure"
    )


def dismiss_modals(page):
    """Dismiss app-install banners and overlay modals on Blinkit.

    Must be called before any search interaction. Safe to call multiple times.
    """
    # Close button selectors for common Blinkit modals
    close_selectors = [
        "button[aria-label='close']",
        "button[aria-label='Close']",
        "[class*='Modal'] button[class*='close']",
        "[class*='modal'] button[class*='Close']",
        "[class*='Banner'] button[class*='close']",
        "[class*='banner'] [class*='dismiss']",
        "[class*='AppInstall'] button",
        "div[class*='overlay'] button[class*='close']",
        "[class*='Popup'] [class*='close']",
        "button[class*='CloseButton']",
    ]

    for selector in close_selectors:
        try:
            elems = page.locator(selector)
            for i in range(min(elems.count(), 3)):
                try:
                    elems.nth(i).click(timeout=1000)
                    time.sleep(0.3)
                except Exception:
                    pass
        except Exception:
            pass

    # Press Escape as a catch-all for modals
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass


def search_items(page, query):
    """Search for items on Blinkit.

    Uses the search bar to enter query and wait for results.
    Raises RuntimeError if session has expired.
    """
    if _check_session_expired(page):
        raise RuntimeError("Blinkit session expired — please re-login in the browser profile.")

    dismiss_modals(page)

    # Find and use the search bar
    search_selectors = [
        "input[placeholder*='Search']",
        "input[placeholder*='search']",
        "input[type='search']",
        "input[class*='SearchBar']",
        "input[class*='search']",
        "[data-testid='search-input']",
    ]

    search_input = None
    for selector in search_selectors:
        inp = page.locator(selector)
        if inp.count() > 0:
            search_input = inp.first
            break

    if search_input is None:
        raise RuntimeError("Could not find Blinkit search bar")

    search_input.fill("", timeout=5000)
    search_input.fill(query)
    time.sleep(1)

    # Submit search — press Enter or click search button
    search_input.press("Enter")

    page.wait_for_load_state("domcontentloaded", timeout=30000)
    time.sleep(2)

    if _check_session_expired(page):
        raise RuntimeError("Blinkit session expired — please re-login in the browser profile.")


def extract_results(page):
    """Extract product candidates from Blinkit search results page.

    Returns list of dicts: {"name": str, "price": float, "brand": str, "unit": str}.
    """
    results = []

    # Blinkit product card selectors — try multiple patterns
    card_selectors = [
        "div[class*='Product__UpdatedPlpProductContainer']",
        "div[class*='ProductCard']",
        "a[class*='Product']",
        "div[data-testid='plp-product']",
        "[class*='product-card']",
        "div[class*='plp-product']",
    ]

    result_cards = None
    for selector in card_selectors:
        cards = page.locator(selector)
        if cards.count() > 0:
            result_cards = cards
            break

    if result_cards is None:
        return results

    count = result_cards.count()

    for i in range(min(count, 20)):
        try:
            card = result_cards.nth(i)

            # Extract product name
            name_selectors = [
                "div[class*='Product__UpdatedTitle']",
                "[class*='ProductName']",
                "[class*='product-name']",
                "[class*='Title']",
                "div[class*='name']",
            ]
            name = ""
            for sel in name_selectors:
                name_elem = card.locator(sel)
                if name_elem.count() > 0:
                    name = (name_elem.first.text_content(timeout=1000) or "").strip()
                    if name:
                        break

            if not name:
                # No name selector matched — skip this card rather than fall
                # back to raw card text (which often starts with discount badges
                # like "60% OFF" rather than the product name).
                continue

            # Extract price
            price_selectors = [
                "div[class*='Product__UpdatedPriceAndAtcRow'] div[class*='Price']",
                "[class*='ProductPrice']",
                "[class*='product-price']",
                "[class*='price']",
                "span[class*='Price']",
            ]
            price = None
            for sel in price_selectors:
                price_elem = card.locator(sel)
                if price_elem.count() > 0:
                    price_text = (price_elem.first.text_content(timeout=1000) or "").strip()
                    # Extract numeric price from text like "₹135" or "Rs. 135"
                    price_match = re.search(r'₹?\s*(\d[\d,.]*)', price_text)
                    if price_match:
                        try:
                            price = float(price_match.group(1).replace(",", ""))
                            break
                        except ValueError:
                            continue

            if price is None:
                continue

            # Extract brand — try brand-specific elements, else infer from name
            brand = _extract_brand(card, name)

            # Extract unit from the product name or weight text
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
            })
        except Exception:
            continue

    return results


def _extract_brand(card, product_name):
    """Try to extract brand name from a Blinkit product card.

    Returns empty string if no brand-specific element is found.
    """
    # Try brand-specific selectors
    brand_selectors = [
        "[class*='Brand']",
        "[class*='brand']",
        "[class*='ProductBrand']",
    ]
    for sel in brand_selectors:
        elem = card.locator(sel)
        if elem.count() > 0:
            text = (elem.first.text_content(timeout=500) or "").strip()
            if text:
                return text

    # No brand selector matched — return empty string rather than guess from
    # product name (first-word inference produces wrong results for multi-word
    # brands like "Mother Dairy" or adjectives like "Low Fat").
    return ""


def discover_fees_blinkit(page):
    """Read delivery fee and handling charge information from Blinkit.

    Reads fee info from banners on the current page, then always also
    navigates to the empty cart page (the most authoritative source).
    Returns fee dict or defaults if nothing found.
    Returns {"status": "session_expired"} if session is expired.
    """
    if _check_session_expired(page):
        return {"status": "session_expired", "platform": "blinkit"}

    fees = {
        "delivery_fee": 25,
        "handling_fee": 9,
        "free_delivery_threshold": 199.0,
        "cashback_tiers": [],
    }

    # Read fees from current page first (e.g., search results banners)
    _read_fees_from_page(page, fees)

    # Always also check the cart page — it's the most authoritative source for
    # fee structure and may have fields that were absent on the current page.
    try:
        current_url = page.url
        page.goto("https://blinkit.com/cart", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)

        if _check_session_expired(page):
            return {"status": "session_expired", "platform": "blinkit"}

        _read_fees_from_page(page, fees)

        # Navigate back
        page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)
    except Exception:
        pass

    # Deduplicate cashback tiers — both page reads append to the same list,
    # so the same tier can appear twice if both pages show the same banner.
    seen = set()
    unique_tiers = []
    for t in fees["cashback_tiers"]:
        key = (t["min_order"], t["cashback"])
        if key not in seen:
            seen.add(key)
            unique_tiers.append(t)
    fees["cashback_tiers"] = unique_tiers

    return fees


def _read_fees_from_page(page, fees):
    """Read fee information from the current page text. Mutates fees dict in place.

    Returns True if any fee information was found, False otherwise.
    """
    try:
        page_text = page.locator("body").text_content(timeout=5000) or ""
    except Exception:
        return False

    found = False

    # Look for free delivery threshold
    threshold_patterns = [
        r'(?:free|FREE)\s+delivery\s+(?:on\s+orders?\s+)?(?:over|above)\s+₹?\s*(\d[\d,]*)',
        r'₹?\s*(\d[\d,]*)\s+(?:and\s+above|or\s+more)\s+(?:for\s+)?free\s+delivery',
        r'free\s+delivery\s+above\s+₹?\s*(\d[\d,]*)',
    ]
    for pattern in threshold_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            fees["free_delivery_threshold"] = float(match.group(1).replace(",", ""))
            found = True
            break

    # Look for delivery fee
    delivery_patterns = [
        r'₹\s*(\d[\d,]*)\s+delivery\s+(?:fee|charge)',
        r'delivery\s+(?:fee|charge)\s+(?:of\s+)?₹\s*(\d[\d,]*)',
        r'delivery\s+₹\s*(\d[\d,]*)',
    ]
    for pattern in delivery_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            fee_val = match.group(1).replace(",", "")
            fees["delivery_fee"] = float(fee_val)
            found = True
            break

    # Look for handling fee / platform fee
    handling_patterns = [
        r'(?:handling|platform|surge)\s+(?:fee|charge)\s+(?:of\s+)?₹\s*(\d[\d,]*)',
        r'₹\s*(\d[\d,]*)\s+(?:handling|platform|surge)\s+(?:fee|charge)',
    ]
    for pattern in handling_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            fees["handling_fee"] = float(match.group(1).replace(",", ""))
            found = True
            break

    # Look for cashback tiers
    for match in re.finditer(
        r'₹\s*(\d[\d,]*)\s+(?:cashback|back|off)\s+(?:on\s+(?:orders?\s+)?)?(?:above|over)\s+₹?\s*(\d[\d,]*)',
        page_text, re.IGNORECASE,
    ):
        fees["cashback_tiers"].append({
            "min_order": float(match.group(2).replace(",", "")),
            "cashback": float(match.group(1).replace(",", "")),
        })
        found = True

    return found
