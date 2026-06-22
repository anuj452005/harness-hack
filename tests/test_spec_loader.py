from pathlib import Path

from validator.spec_loader import load_endpoints

FIXTURE = Path(__file__).parent / "fixtures" / "sample_openapi.yaml"


def test_loads_all_operations():
    eps = load_endpoints(FIXTURE)
    keys = {e.key for e in eps}
    assert keys == {"POST /v1/widgets", "GET /v1/widgets/{widget}"}


def test_request_schema_and_missing_example():
    eps = {e.key: e for e in load_endpoints(FIXTURE)}
    post = eps["POST /v1/widgets"]
    assert post.request_schema["required"] == ["identifier"]
    assert post.request_example is None  # fixture intentionally omits it


def test_responses_captured():
    eps = {e.key: e for e in load_endpoints(FIXTURE)}
    get = eps["GET /v1/widgets/{widget}"]
    assert set(get.responses) == {"200", "404"}
