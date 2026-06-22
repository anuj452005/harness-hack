from validator.diffing import compare_response
from validator.synth import synthesize

SCHEMA = {
    "type": "object",
    "required": ["identifier", "name"],
    "properties": {
        "identifier": {"type": "string"},
        "name": {"type": "string"},
        "count": {"type": "integer"},
    },
}


def _kinds(diffs):
    return {d["kind"] for d in diffs}


def test_undocumented_field():
    actual = {"identifier": "a", "name": "b", "extra": True}
    diffs = compare_response(SCHEMA, actual)
    assert "undocumented_field" in _kinds(diffs)
    assert any(d["field"].endswith("extra") for d in diffs)


def test_missing_required_field():
    actual = {"identifier": "a"}  # 'name' missing
    diffs = compare_response(SCHEMA, actual)
    assert "missing_field" in _kinds(diffs)


def test_type_mismatch():
    actual = {"identifier": "a", "name": "b", "count": "three"}
    diffs = compare_response(SCHEMA, actual)
    assert "type_mismatch" in _kinds(diffs)


def test_clean_response_has_no_diffs():
    actual = {"identifier": "a", "name": "b", "count": 3}
    assert compare_response(SCHEMA, actual) == []


def test_synth_honors_required_and_pattern():
    schema = {
        "type": "object",
        "required": ["identifier"],
        "properties": {
            "identifier": {
                "type": "string",
                "pattern": "^[a-zA-Z_][0-9a-zA-Z_$]{0,127}$",
                "minLength": 1,
            }
        },
    }
    body = synthesize(schema, {"identifier": "apiqual_org"})
    assert body["identifier"] == "apiqual_org"
