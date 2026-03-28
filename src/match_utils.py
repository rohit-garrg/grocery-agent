import re

UNIT_STRINGS = {"kg", "g", "ml", "l", "lb", "oz", "pack", "pcs", "piece", "pieces", "ltr", "litre", "liter"}


def _normalize_tokens(text):
    """Lowercase, strip punctuation (keep digits/letters/spaces), split into tokens.
    Also generates joined unit tokens (e.g., ["1", "kg"] -> "1kg").
    Returns (original_tokens, combined_token_set).
    """
    cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
    original_tokens = cleaned.split()

    joined_tokens = []
    for i in range(len(original_tokens) - 1):
        tok = original_tokens[i]
        next_tok = original_tokens[i + 1]
        if tok.isdigit() and next_tok in UNIT_STRINGS:
            joined_tokens.append(tok + next_tok)

    combined = set(original_tokens) | set(joined_tokens)
    return original_tokens, combined


def _compute_score(query_original_tokens, candidate_token_set):
    """Count how many original query tokens match against the candidate.

    A token matches if:
    - It appears directly in candidate_token_set, OR
    - It's part of a digit+unit pair whose joined form appears in candidate_token_set
    """
    matched = set()

    # Direct matches
    for i, tok in enumerate(query_original_tokens):
        if tok in candidate_token_set:
            matched.add(i)

    # Joined unit token matches: if "1" and "kg" are adjacent query tokens
    # and "1kg" is in candidate_token_set, both tokens match
    for i in range(len(query_original_tokens) - 1):
        tok = query_original_tokens[i]
        next_tok = query_original_tokens[i + 1]
        if tok.isdigit() and next_tok in UNIT_STRINGS:
            joined = tok + next_tok
            if joined in candidate_token_set:
                matched.add(i)
                matched.add(i + 1)

    return len(matched)


def find_best_match(candidates, query, brand_constraint=None):
    """Find the best matching candidate for a query string.

    Args:
        candidates: List of dicts with at least {"name": str, "price": float, "brand": str}.
        query: Search string from master list.
        brand_constraint: Optional brand filter (case-insensitive substring match on candidate["brand"]).

    Returns:
        Best matching candidate dict, or None.
    """
    if not candidates:
        return None

    query_original_tokens, query_token_set = _normalize_tokens(query)

    if not query_original_tokens:
        return None

    # Apply brand filter
    if brand_constraint is not None:
        brand_lower = brand_constraint.lower()
        candidates = [c for c in candidates if brand_lower in c["brand"].lower()]
        if not candidates:
            return None

    threshold = 0.5 * len(query_original_tokens)
    scored = []

    for candidate in candidates:
        _, candidate_token_set = _normalize_tokens(candidate["name"])
        score = _compute_score(query_original_tokens, candidate_token_set)

        if score >= threshold:
            scored.append((candidate, score))

    if not scored:
        return None

    # Return cheapest among those meeting threshold
    scored.sort(key=lambda x: x[0]["price"])
    return scored[0][0]
