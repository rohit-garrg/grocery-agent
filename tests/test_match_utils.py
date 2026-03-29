from src.match_utils import find_best_match


def test_exact_query_match():
    candidates = [
        {"name": "Toor Dal 1kg", "price": 135.0, "brand": "Tata"},
    ]
    result = find_best_match(candidates, "toor dal 1kg")
    assert result is not None
    assert result["name"] == "Toor Dal 1kg"


def test_partial_match_above_threshold():
    """3 out of 4 query tokens match = 75% >= 50% threshold."""
    candidates = [
        {"name": "Toor Dal Premium 1kg", "price": 150.0, "brand": "Tata"},
    ]
    result = find_best_match(candidates, "toor dal 1kg organic")
    assert result is not None
    assert result["name"] == "Toor Dal Premium 1kg"


def test_partial_match_below_threshold():
    """Only 1 out of 4 query tokens match = 25% < 50% threshold."""
    candidates = [
        {"name": "Basmati Rice 5kg", "price": 400.0, "brand": "India Gate"},
    ]
    result = find_best_match(candidates, "toor dal 1kg organic")
    assert result is None


def test_brand_filtering_exact_case():
    candidates = [
        {"name": "Toor Dal 1kg", "price": 135.0, "brand": "Tata"},
        {"name": "Toor Dal 1kg", "price": 120.0, "brand": "Fortune"},
    ]
    result = find_best_match(candidates, "toor dal 1kg", brand_constraint="Tata")
    assert result is not None
    assert result["brand"] == "Tata"
    assert result["price"] == 135.0


def test_brand_filtering_different_case():
    candidates = [
        {"name": "Toor Dal 1kg", "price": 135.0, "brand": "Tata Sampann"},
    ]
    result = find_best_match(candidates, "toor dal 1kg", brand_constraint="tata")
    assert result is not None
    assert result["brand"] == "Tata Sampann"


def test_brand_filter_no_match():
    candidates = [
        {"name": "Toor Dal 1kg", "price": 120.0, "brand": "Fortune"},
    ]
    result = find_best_match(candidates, "toor dal 1kg", brand_constraint="Tata")
    assert result is None


def test_cheapest_selected_among_multiple():
    candidates = [
        {"name": "Toor Dal 1kg Pack", "price": 160.0, "brand": "Tata"},
        {"name": "Toor Dal 1kg", "price": 120.0, "brand": "Fortune"},
        {"name": "Toor Dal 1kg Premium", "price": 180.0, "brand": "Organic"},
    ]
    result = find_best_match(candidates, "toor dal 1kg")
    assert result is not None
    assert result["price"] == 120.0


def test_empty_candidates():
    result = find_best_match([], "toor dal 1kg")
    assert result is None


def test_single_candidate():
    candidates = [
        {"name": "Amul Butter 500g", "price": 290.0, "brand": "Amul"},
    ]
    result = find_best_match(candidates, "amul butter 500g")
    assert result is not None
    assert result["price"] == 290.0


def test_unit_normalization_query_spaced_candidate_joined():
    """Query '1 kg' should match candidate name containing '1kg'."""
    candidates = [
        {"name": "Toor Dal 1kg", "price": 135.0, "brand": "Tata"},
    ]
    result = find_best_match(candidates, "toor dal 1 kg")
    assert result is not None
    assert result["name"] == "Toor Dal 1kg"


def test_unit_normalization_query_joined_candidate_spaced():
    """Query '1kg' should match candidate name containing '1 kg'."""
    candidates = [
        {"name": "Toor Dal 1 kg", "price": 135.0, "brand": "Tata"},
    ]
    result = find_best_match(candidates, "toor dal 1kg")
    assert result is not None
    assert result["name"] == "Toor Dal 1 kg"


def test_quantity_mismatch_rejected_smaller_size():
    """Query for 500g must not match a 200g product even if other tokens match."""
    candidates = [
        {"name": "Amul Salted Butter 200g", "price": 118.0, "brand": "Amul"},
        {"name": "Amul Butter 500g", "price": 270.0, "brand": "Amul"},
    ]
    result = find_best_match(candidates, "amul butter 500g")
    assert result is not None
    assert result["price"] == 270.0
    assert "500g" in result["name"].lower().replace(" ", "")


def test_quantity_mismatch_rejected_different_volume():
    """Query for 4l must not match a 1l product."""
    candidates = [
        {"name": "Surf Excel Matic Top Load Liquid Detergent 1 L", "price": 149.0, "brand": "Surf Excel"},
        {"name": "Surf Excel Matic Top Load Liquid Detergent 4 L", "price": 549.0, "brand": "Surf Excel"},
    ]
    result = find_best_match(candidates, "surf excel liquid top load 4l")
    assert result is not None
    assert result["price"] == 549.0


def test_quantity_mismatch_only_wrong_size_returns_none():
    """If only wrong-size candidates exist, return None rather than wrong product."""
    candidates = [
        {"name": "Amul Salted Butter 200g", "price": 118.0, "brand": "Amul"},
        {"name": "Amul Salted Butter 100g", "price": 62.0, "brand": "Amul"},
    ]
    result = find_best_match(candidates, "amul butter 500g")
    assert result is None


def test_no_quantity_in_query_works_as_before():
    """Queries without quantity tokens should still pick cheapest above threshold."""
    candidates = [
        {"name": "Amul Butter 500g", "price": 270.0, "brand": "Amul"},
        {"name": "Amul Butter 200g", "price": 118.0, "brand": "Amul"},
    ]
    result = find_best_match(candidates, "amul butter")
    assert result is not None
    assert result["price"] == 118.0


def test_quantity_spaced_in_query_joined_in_candidate():
    """Query '500 g' should enforce quantity match against candidate '500g'."""
    candidates = [
        {"name": "Amul Butter 200g", "price": 118.0, "brand": "Amul"},
        {"name": "Amul Butter 500g", "price": 270.0, "brand": "Amul"},
    ]
    result = find_best_match(candidates, "amul butter 500 g")
    assert result is not None
    assert result["price"] == 270.0


def test_quantity_joined_in_query_spaced_in_candidate():
    """Query '500g' should enforce quantity match against candidate '500 g'."""
    candidates = [
        {"name": "Amul Butter 200 g", "price": 118.0, "brand": "Amul"},
        {"name": "Amul Butter 500 g", "price": 270.0, "brand": "Amul"},
    ]
    result = find_best_match(candidates, "amul butter 500g")
    assert result is not None
    assert result["price"] == 270.0


def test_multiple_quantity_tokens_in_query():
    """If query has multiple quantity tokens, candidate must match at least one."""
    candidates = [
        {"name": "Dettol Handwash 200ml Pack of 3", "price": 150.0, "brand": "Dettol"},
        {"name": "Dettol Handwash 750ml", "price": 180.0, "brand": "Dettol"},
    ]
    result = find_best_match(candidates, "dettol handwash 200ml")
    assert result is not None
    assert "200ml" in result["name"].lower().replace(" ", "")


def test_quantity_filter_with_brand_constraint():
    """Quantity filter and brand filter should both apply."""
    candidates = [
        {"name": "Tata Toor Dal 500g", "price": 60.0, "brand": "Tata"},
        {"name": "Tata Toor Dal 1kg", "price": 120.0, "brand": "Tata"},
        {"name": "Fortune Toor Dal 1kg", "price": 110.0, "brand": "Fortune"},
    ]
    result = find_best_match(candidates, "toor dal 1kg", brand_constraint="Tata")
    assert result is not None
    assert result["brand"] == "Tata"
    assert result["price"] == 120.0


def test_quantity_unit_alias_normalization():
    """Query '4 ltr' should match candidate '4 L' via canonical normalization."""
    candidates = [
        {"name": "Surf Excel Liquid 1 L", "price": 149.0, "brand": "Surf Excel"},
        {"name": "Surf Excel Liquid 4 L", "price": 549.0, "brand": "Surf Excel"},
    ]
    result = find_best_match(candidates, "surf excel liquid 4 ltr")
    assert result is not None
    assert result["price"] == 549.0
