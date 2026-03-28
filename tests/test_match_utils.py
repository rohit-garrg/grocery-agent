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
