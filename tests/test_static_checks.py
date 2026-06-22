from pathlib import Path

from validator import static_checks
from validator.models import Endpoint
from validator.spec_loader import load_endpoints

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def _categories(findings):
    return {f.category for f in findings}


def test_known_defects_are_flagged():
    eps = load_endpoints(FIXTURE)
    findings = static_checks.run_static_checks(eps)
    cats = _categories(findings)
    assert "missing_description" in cats   # POST has no summary/description
    assert "missing_example" in cats       # POST request body has no example
    assert "missing_error_response" in cats  # POST declares no 400
    assert "param_mismatch" in cats        # {widget} not declared as a path param


def test_invalid_example_detected():
    ep = Endpoint(
        method="post",
        path="/x",
        request_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
        request_example={"count": "not-a-number"},
    )
    findings = list(static_checks.check_example_validates(ep))
    assert findings and findings[0].category == "schema_mismatch"
    assert findings[0].status == "fail"


def test_valid_example_passes():
    ep = Endpoint(
        method="post",
        path="/x",
        request_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
        request_example={"count": 3},
    )
    assert list(static_checks.check_example_validates(ep)) == []
