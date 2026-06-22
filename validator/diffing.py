"""Compare a live API response against what the spec promised.

This is the heart of the doc-drift detection: given the declared response schema
for a status code and the actual JSON the live API returned, surface concrete
diffs — undocumented fields, documented-but-missing fields, and type mismatches.
"""

from __future__ import annotations

from typing import Any

JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def schema_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Best-effort property map for an object schema, peering through allOf."""
    if not isinstance(schema, dict):
        return {}
    props = dict(schema.get("properties") or {})
    for sub in schema.get("allOf", []) or []:
        if isinstance(sub, dict):
            props.update(schema_properties(sub))
    return props


def compare_response(schema: dict[str, Any] | None, actual: Any) -> list[dict[str, Any]]:
    """Return a list of {kind, field, expected, actual, message} diff records."""
    if schema is None or not isinstance(actual, (dict, list)):
        return []
    diffs: list[dict[str, Any]] = []
    _walk(schema, actual, "$", diffs)
    return diffs


def _walk(schema: dict[str, Any], actual: Any, path: str, out: list) -> None:
    if not isinstance(schema, dict):
        return
    stype = schema.get("type")

    # Arrays: descend into the item schema using the first element as a sample.
    if stype == "array" or "items" in schema:
        if isinstance(actual, list) and actual and isinstance(schema.get("items"), dict):
            _walk(schema["items"], actual[0], f"{path}[0]", out)
        return

    props = schema_properties(schema)
    if not props or not isinstance(actual, dict):
        return

    declared = set(props)
    present = set(actual)

    for field in sorted(present - declared):
        out.append(
            {
                "kind": "undocumented_field",
                "field": f"{path}.{field}",
                "expected": None,
                "actual": _typename(actual[field]),
                "message": f"Response field '{field}' is returned by the API but not in the spec.",
            }
        )

    required = set(schema.get("required", []))
    for field in sorted(required - present):
        out.append(
            {
                "kind": "missing_field",
                "field": f"{path}.{field}",
                "expected": "required by spec",
                "actual": "absent",
                "message": f"Field '{field}' is required by the spec but missing from the live response.",
            }
        )

    for field in sorted(declared & present):
        sub_schema = props[field]
        expected_t = sub_schema.get("type") if isinstance(sub_schema, dict) else None
        if expected_t and not _type_ok(actual[field], expected_t):
            out.append(
                {
                    "kind": "type_mismatch",
                    "field": f"{path}.{field}",
                    "expected": expected_t,
                    "actual": _typename(actual[field]),
                    "message": f"Field '{field}' is '{expected_t}' in spec but "
                    f"'{_typename(actual[field])}' in the live response.",
                }
            )
        elif isinstance(sub_schema, dict) and isinstance(actual[field], (dict, list)):
            _walk(sub_schema, actual[field], f"{path}.{field}", out)


def _type_ok(value: Any, expected: str) -> bool:
    py = JSON_TYPES.get(expected)
    if py is None:
        return True
    if expected == "number" and isinstance(value, bool):
        return False  # bool is a subclass of int — don't count it as a number
    if expected == "integer" and isinstance(value, bool):
        return False
    return isinstance(value, py)


def _typename(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__
