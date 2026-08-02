from app.query_engine import (
    _match_catalog_value,
    enforce_state_filter_boundaries,
    infer_compare_values,
    infer_filters,
)


CATALOGS = {
    "state": ["VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "industry": ["Information Technology"],
    "role": ["Business Analyst"],
    "role_family": [],
    "city": [],
    "visa": ["Temporary Graduate (485)"],
    "seniority": [],
    "qualification": [],
    "certification": [],
    "certificate_institution": [],
    "education_institution": [],
}


def state_filters(question: str, primary: str = "visa") -> list[dict]:
    return [
        item
        for item in infer_filters(question, primary, CATALOGS)
        if item.get("field") == "state"
    ]


def test_state_codes_do_not_match_inside_words() -> None:
    assert _match_catalog_value("visa", "state", CATALOGS) is None
    assert _match_catalog_value("clients", "state", CATALOGS) is None
    assert _match_catalog_value("fantastic", "state", CATALOGS) is None
    assert _match_catalog_value("service", "state", CATALOGS) is None
    assert _match_catalog_value("answers", "state", CATALOGS) is None
    assert _match_catalog_value("always", "state", CATALOGS) is None
    assert _match_catalog_value("action", "state", CATALOGS) is None


def test_false_state_filters_are_not_inferred() -> None:
    assert state_filters("visa") == []
    assert state_filters("clients") == []
    assert state_filters("client visa categories") == []


def test_explicit_state_codes_and_names_still_work() -> None:
    assert state_filters("visa categories in SA") == [
        {"field": "state", "operator": "equals", "value": "SA"}
    ]
    assert state_filters("visa categories in Northern Territory") == [
        {"field": "state", "operator": "equals", "value": "NT"}
    ]
    assert state_filters("visa categories in Canberra") == [
        {"field": "state", "operator": "equals", "value": "ACT"}
    ]


def test_compare_values_require_complete_tokens() -> None:
    assert infer_compare_values("compare visa clients", "state", CATALOGS) == []
    assert infer_compare_values("compare SA and VIC", "state", CATALOGS) == ["VIC", "SA"]


def test_llm_state_filters_are_guarded_too() -> None:
    false_plan = {
        "dimension": "visa",
        "filters": [{"field": "state", "operator": "equals", "value": "SA"}],
    }
    assert enforce_state_filter_boundaries("visa", false_plan)["filters"] == []

    explicit_plan = {
        "dimension": "visa",
        "filters": [{"field": "state", "operator": "equals", "value": "SA"}],
    }
    assert enforce_state_filter_boundaries("visa in SA", explicit_plan)["filters"] == [
        {"field": "state", "operator": "equals", "value": "SA"}
    ]
