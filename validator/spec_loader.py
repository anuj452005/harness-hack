"""Load an OpenAPI spec and normalize each operation into an ``Endpoint``.

All ``$ref`` pointers are resolved up front (jsonref) so downstream checkers see
plain dicts. Examples are pulled from every place Harness specs hide them:
content-level ``example``, schema-level ``example``, and the non-standard
``x-examples`` map (which renders nowhere — itself a finding we flag later).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import jsonref
import yaml

from validator.models import Endpoint

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
JSON = "application/json"


def _first_example(media: dict[str, Any]) -> Optional[Any]:
    """Extract an example from a media-type object, checking all the usual spots."""
    if "example" in media:
        return media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
    schema = media.get("schema") or {}
    if isinstance(schema, dict):
        if "example" in schema:
            return schema["example"]
        x = schema.get("x-examples")
        if isinstance(x, dict) and x:
            return next(iter(x.values()))
    return None


def load_spec(spec_path: Path) -> dict[str, Any]:
    """Parse YAML and resolve all internal $refs into plain Python structures."""
    raw = yaml.safe_load(spec_path.read_text())
    # proxies=False -> get concrete dicts/lists rather than lazy proxy objects.
    return jsonref.replace_refs(raw, proxies=False, lazy_load=False)


def load_endpoints(spec_path: Path) -> list[Endpoint]:
    spec = load_spec(spec_path)
    endpoints: list[Endpoint] = []
    for path, path_item in (spec.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters", [])
        for method, op in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            endpoints.append(_build_endpoint(path, method.lower(), op, shared_params))
    return endpoints


def _build_endpoint(
    path: str, method: str, op: dict[str, Any], shared_params: list
) -> Endpoint:
    params = list(shared_params) + list(op.get("parameters", []))

    request_schema = None
    request_example = None
    rb = op.get("requestBody")
    if isinstance(rb, dict):
        media = (rb.get("content") or {}).get(JSON, {})
        request_schema = media.get("schema")
        request_example = _first_example(media)

    responses: dict[str, dict[str, Any]] = {}
    for code, resp in (op.get("responses") or {}).items():
        if not isinstance(resp, dict):
            continue
        media = (resp.get("content") or {}).get(JSON, {})
        responses[str(code)] = {
            "description": resp.get("description"),
            "schema": media.get("schema"),
            "example": _first_example(media),
        }

    return Endpoint(
        method=method,
        path=path,
        operation_id=op.get("operationId"),
        summary=op.get("summary"),
        description=op.get("description"),
        tags=op.get("tags", []) or [],
        parameters=params,
        request_schema=request_schema,
        request_example=request_example,
        responses=responses,
    )
