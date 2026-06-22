"""Synthesize a valid request body from a JSON schema.

Harness ng-manager specs ship no request examples, so to exercise an endpoint
live we must build a body ourselves. We honor ``required``, ``pattern``,
``minLength``/``maxLength``, ``enum`` and ``type`` so the generated payload is
accepted by the API. A caller-supplied ``overrides`` map injects known-good
values (e.g. a unique identifier) for specific fields.
"""

from __future__ import annotations

import re
from typing import Any


def synthesize(schema: dict[str, Any] | None, overrides: dict[str, Any] | None = None) -> Any:
    overrides = overrides or {}
    if not isinstance(schema, dict):
        return None
    return _gen(schema, overrides, field_name=None)


def _gen(schema: dict[str, Any], overrides: dict[str, Any], field_name: str | None) -> Any:
    if field_name and field_name in overrides:
        return overrides[field_name]
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]

    stype = schema.get("type")
    if stype == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        # Generate required fields, plus name/description if present (nicer payloads).
        out: dict[str, Any] = {}
        for name, sub in props.items():
            if name in required or name in overrides or name in ("name", "description"):
                if isinstance(sub, dict):
                    out[name] = _gen(sub, overrides, name)
        return out
    if stype == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return [_gen(items, overrides, None)]
        return []
    if stype == "integer":
        return int(schema.get("minimum", 1))
    if stype == "number":
        return float(schema.get("minimum", 1))
    if stype == "boolean":
        return False
    # string (default)
    return _gen_string(schema, field_name)


def _gen_string(schema: dict[str, Any], field_name: str | None) -> str:
    base = (field_name or "sample").replace("-", "_")
    pattern = schema.get("pattern")
    min_len = schema.get("minLength", 0)
    max_len = schema.get("maxLength", 128)
    if pattern:
        # Common Harness identifier pattern: ^[a-zA-Z_][0-9a-zA-Z_$]{...}$
        candidate = base if re.fullmatch(r"[a-zA-Z_][0-9a-zA-Z_$]*", base) else "sample_value"
        if re.fullmatch(pattern, candidate):
            value = candidate
        else:
            value = "sample_value"
    else:
        value = base
    if len(value) < min_len:
        value = (value + "_xxxxxxxx")[: max(min_len, len(value))]
    if len(value) > max_len:
        value = value[:max_len]
    return value
