def _format_price(price_info, qty):
    """Format a single price cell for the comparison table."""
    if price_info is None:
        return "N/A"
    price = price_info["price"]
    if qty > 1:
        return f"₹{price:.0f} ea"
    return f"₹{price:.0f}"


def _build_comparison_table(item_details):
    """Build the item comparison table with box-drawing characters."""
    rows = []
    for item in item_details:
        amazon = item["prices"].get("amazon")
        blinkit = item["prices"].get("blinkit")

        # Pick brand from first available platform
        brand = None
        if amazon and amazon.get("brand"):
            brand = amazon["brand"]
        elif blinkit and blinkit.get("brand"):
            brand = blinkit["brand"]

        rows.append({
            "name": item["name"],
            "qty": f"x{item['qty']}",
            "amazon": _format_price(amazon, item["qty"]),
            "blinkit": _format_price(blinkit, item["qty"]),
            "brand": brand,
        })

    # Column widths
    name_w = max(len("Item"), *(len(r["name"]) for r in rows))
    for r in rows:
        if r["brand"]:
            name_w = max(name_w, len(f"({r['brand']})"))
    qty_w = max(len("Qty"), *(len(r["qty"]) for r in rows))
    amz_w = max(len("Amazon"), *(len(r["amazon"]) for r in rows))
    blk_w = max(len("Blinkit"), *(len(r["blinkit"]) for r in rows))

    def separator(sep_l, sep_m, sep_r, fill):
        return (f"{sep_l}{fill * (name_w + 2)}{sep_m}{fill * (qty_w + 2)}"
                f"{sep_m}{fill * (amz_w + 2)}{sep_m}{fill * (blk_w + 2)}{sep_r}")

    def data_line(c1, c2, c3, c4):
        return f"│ {c1:<{name_w}} │ {c2:<{qty_w}} │ {c3:<{amz_w}} │ {c4:<{blk_w}} │"

    lines = ["ITEM COMPARISON:"]
    lines.append(separator("┌", "┬", "┐", "─"))
    lines.append(data_line("Item", "Qty", "Amazon", "Blinkit"))
    lines.append(separator("├", "┼", "┤", "─"))

    for i, r in enumerate(rows):
        lines.append(data_line(r["name"], r["qty"], r["amazon"], r["blinkit"]))
        if r["brand"]:
            lines.append(data_line(f"({r['brand']})", "", "", ""))
        if i < len(rows) - 1:
            lines.append(separator("├", "┼", "┤", "─"))

    lines.append(separator("└", "┴", "┘", "─"))
    return "\n".join(lines)


def _format_platform_section(platform, optimizer_result):
    """Format the recommendation section for one platform."""
    display = "Amazon" if platform == "amazon" else "Blinkit"
    items = optimizer_result["recommendation"][platform]
    if not items:
        return None

    num_items = len(items)
    total_units = sum(it["qty"] for it in items)

    lines = []
    if total_units > num_items:
        lines.append(f"From {display} ({num_items} item{'s' if num_items != 1 else ''}, {total_units} units):")
    else:
        lines.append(f"From {display} ({num_items} item{'s' if num_items != 1 else ''}):")

    for item in items:
        info = item["prices"][platform]
        price = info["price"]
        brand = info.get("brand") or ""
        qty = item["qty"]

        line = f"  • {item['name']}"
        if qty > 1:
            line += f" x{qty}"
        if brand:
            line += f" — {brand}"
        if qty > 1:
            line += f" — ₹{price:.0f} x{qty} = ₹{price * qty:.0f}"
        else:
            line += f" — ₹{price:.0f}"
        lines.append(line)

    subtotal = optimizer_result[f"{platform}_subtotal"]
    delivery_fee = optimizer_result[f"{platform}_delivery_fee"]
    handling_fee = optimizer_result[f"{platform}_handling_fee"]
    cashback = optimizer_result[f"{platform}_cashback"]
    platform_total = optimizer_result[f"{platform}_total"]

    lines.append(f"  Subtotal: ₹{subtotal:,.0f}")

    if delivery_fee == 0:
        lines.append("  Delivery: Free")
    else:
        lines.append(f"  Delivery: ₹{delivery_fee:.0f}")

    if handling_fee > 0:
        lines.append(f"  Handling: ₹{handling_fee:.0f}")

    if cashback > 0:
        lines.append(f"  Cashback: ₹{cashback:.0f}")

    lines.append(f"  Platform total: ₹{platform_total:,.0f}")
    return "\n".join(lines)


def format_comparison(optimizer_result, item_details):
    """Format the full comparison output for Telegram.

    Args:
        optimizer_result: Dict from optimize_cart().
        item_details: List of {"id", "name", "qty", "prices": {"amazon": {...}|None, "blinkit": {...}|None}}.

    Returns:
        str: Formatted comparison text.
    """
    parts = []

    # Section 1: header + comparison table
    parts.append("📊 Price Comparison Results")
    parts.append("")
    parts.append(_build_comparison_table(item_details))

    # Section 2: recommended split
    parts.append("")
    parts.append("✅ RECOMMENDED SPLIT:")
    parts.append("")

    for platform in ("amazon", "blinkit"):
        section = _format_platform_section(platform, optimizer_result)
        if section:
            parts.append(section)
            parts.append("")

    # Section 3: totals
    combined = optimizer_result["combined_total"]
    parts.append(f"💰 COMBINED TOTAL: ₹{combined:,.0f}")

    all_amazon = optimizer_result["all_amazon_total"]
    all_blinkit = optimizer_result["all_blinkit_total"]

    if all_amazon is not None:
        parts.append(f"vs all from Amazon: ₹{all_amazon:,.0f}")
    else:
        parts.append("vs all from Amazon: N/A (some items unavailable)")

    if all_blinkit is not None:
        parts.append(f"vs all from Blinkit: ₹{all_blinkit:,.0f}")
    else:
        parts.append("vs all from Blinkit: N/A (some items unavailable)")

    savings = optimizer_result["savings"]
    if savings > 0:
        parts.append(f"Savings with split: ₹{savings:,.0f}")

    if optimizer_result.get("fee_warning"):
        parts.append("")
        parts.append("⚠️ High fee ratio: delivery + handling fees exceed 20% of item cost.")

    return "\n".join(parts)


def _hard_split(text, max_length):
    """Split text at newline boundaries, never exceeding max_length per chunk."""
    chunks = []
    while len(text) > max_length:
        idx = text.rfind("\n", 0, max_length)
        if idx == -1:
            idx = max_length
        chunks.append(text[:idx])
        text = text[idx:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def _split_at_row_boundaries(text, max_length):
    """Split text at table row boundaries (lines starting with ├)."""
    lines = text.split("\n")
    chunks = []
    current_lines = []
    current_len = 0

    for line in lines:
        line_cost = len(line) + (1 if current_lines else 0)

        if current_len + line_cost > max_length and line.startswith("├") and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = len(line)
        else:
            current_lines.append(line)
            current_len += line_cost

    if current_lines:
        chunks.append("\n".join(current_lines))

    # Safety: hard-split any chunks still over limit
    result = []
    for chunk in chunks:
        if len(chunk) <= max_length:
            result.append(chunk)
        else:
            result.extend(_hard_split(chunk, max_length))

    return result


def split_message(text, max_length=4096):
    """Split formatted output into Telegram-safe chunks.

    Priority:
    (a) If text fits, return as single-element list.
    (b) Split at the ✅ RECOMMENDED SPLIT boundary.
    (c) If the table part still exceeds max_length, split at row boundaries.
    (d) Hard-split at last newline before max_length as fallback.

    Returns:
        list[str]: Message chunks, each <= max_length.
    """
    if len(text) <= max_length:
        return [text]

    split_marker = "\n✅ RECOMMENDED SPLIT:\n"
    if split_marker in text:
        idx = text.index(split_marker)
        part1 = text[:idx].rstrip()
        part2 = text[idx:].lstrip("\n")

        if len(part1) <= max_length and len(part2) <= max_length:
            return [part1, part2]

        # Table too big: split at row boundaries
        if len(part1) > max_length:
            table_parts = _split_at_row_boundaries(part1, max_length)
        else:
            table_parts = [part1]

        if len(part2) > max_length:
            rec_parts = _hard_split(part2, max_length)
        else:
            rec_parts = [part2]

        return table_parts + rec_parts

    return _hard_split(text, max_length)


def format_unavailable(items):
    """Format a note listing items not found on any platform.

    Args:
        items: List of dicts with at least {"name": str}.

    Returns:
        str: Formatted note, or empty string if no items.
    """
    if not items:
        return ""
    lines = ["⚠️ Not found on any platform:"]
    for item in items:
        lines.append(f"  • {item['name']}")
    return "\n".join(lines)
