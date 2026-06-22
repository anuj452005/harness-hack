"""Deterministic static checks over the OpenAPI spec.

Each check is a small function that takes an ``Endpoint`` and yields zero or more
``Finding`` objects. They are pure (no network, no LLM) so they are fast and fully
reproducible — the backbone of the quality report.
"""

from __future__ import annotations

import re
from typing import Iterator

import jsonschema

from validator.models import Diff, Endpoint, Finding

# Error responses we expect a well-documented mutating endpoint to declare.
EXPECTED_ERROR_CODES = {"post": ["400"], "put": ["400", "404"], "delete": ["404"]}
COMMON_ERROR_CODES = ["400", "401", "403", "404", "500"]
PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")


def _finding(ep: Endpoint, **kw) -> Finding:
    return Finding(endpoint=ep.key, method=ep.method, path=ep.path, source="static", **kw)


def check_request_example(ep: Endpoint) -> Iterator[Finding]:
    if ep.request_schema is None:
        return
    if ep.request_example is None:
        yield _finding(
            ep,
            category="missing_example",
            severity="warn",
            status="fail",
            message="Request body has a schema but no example — docs render an empty 'try it' body.",
        )


def check_response_examples(ep: Endpoint) -> Iterator[Finding]:
    for code, resp in ep.responses.items():
        if not code.startswith("2"):
            continue
        if resp.get("schema") is not None and resp.get("example") is None:
            yield _finding(
                ep,
                category="missing_example",
                severity="info",
                status="warn",
                message=f"Success response {code} has a schema but no example.",
            )


def check_example_validates(ep: Endpoint) -> Iterator[Finding]:
    """If both an example and a schema exist, the example must validate."""
    if ep.request_schema is None or ep.request_example is None:
        return
    try:
        jsonschema.validate(ep.request_example, ep.request_schema)
    except jsonschema.ValidationError as e:
        yield _finding(
            ep,
            category="schema_mismatch",
            severity="error",
            status="fail",
            message=f"Documented request example does not validate against its schema: {e.message}",
            diff=Diff(expected=_short(ep.request_schema), actual=ep.request_example),
        )
    except jsonschema.SchemaError:
        pass  # malformed schema is caught by a different check


def check_error_responses(ep: Endpoint) -> Iterator[Finding]:
    declared = set(ep.responses)
    expected = EXPECTED_ERROR_CODES.get(ep.method, [])
    missing = [c for c in expected if c not in declared]
    if missing:
        yield _finding(
            ep,
            category="missing_error_response",
            severity="warn",
            status="fail",
            message=f"{ep.method.upper()} declares no {', '.join(missing)} response; "
            "callers cannot know the documented error shape.",
            diff=Diff(expected=expected, actual=sorted(declared)),
        )
    if not any(c in declared for c in COMMON_ERROR_CODES):
        yield _finding(
            ep,
            category="missing_error_response",
            severity="warn",
            status="warn",
            message="No common error response (4xx/5xx) documented at all.",
        )


def check_descriptions(ep: Endpoint) -> Iterator[Finding]:
    if not (ep.summary or ep.description):
        yield _finding(
            ep,
            category="missing_description",
            severity="info",
            status="warn",
            message="Operation has neither a summary nor a description.",
        )
    for p in ep.parameters:
        if isinstance(p, dict) and not p.get("description"):
            yield _finding(
                ep,
                category="missing_description",
                severity="info",
                status="warn",
                message=f"Parameter '{p.get('name')}' has no description.",
            )


def check_path_params(ep: Endpoint) -> Iterator[Finding]:
    """Every {placeholder} in the path must be a declared, required path param."""
    in_path = set(PATH_PARAM_RE.findall(ep.path))
    declared = {
        p.get("name")
        for p in ep.parameters
        if isinstance(p, dict) and p.get("in") == "path"
    }
    for name in in_path - declared:
        yield _finding(
            ep,
            category="param_mismatch",
            severity="error",
            status="fail",
            message=f"Path placeholder '{{{name}}}' is not declared as a path parameter.",
            diff=Diff(expected=sorted(in_path), actual=sorted(declared)),
        )
    for p in ep.parameters:
        if not isinstance(p, dict) or p.get("in") != "path":
            continue
        if p.get("name") not in in_path:
            yield _finding(
                ep,
                category="param_mismatch",
                severity="warn",
                status="fail",
                message=f"Declared path param '{p.get('name')}' does not appear in the path template.",
            )
        if p.get("required") is False:
            yield _finding(
                ep,
                category="param_mismatch",
                severity="error",
                status="fail",
                message=f"Path param '{p.get('name')}' is marked required: false (path params must be required).",
            )


def check_response_schema_shape(ep: Endpoint) -> Iterator[Finding]:
    """Flag success responses whose schema is empty / says nothing useful."""
    for code, resp in ep.responses.items():
        if not code.startswith("2"):
            continue
        schema = resp.get("schema")
        if schema is None:
            yield _finding(
                ep,
                category="loose_schema",
                severity="warn",
                status="warn",
                message=f"Success response {code} declares no schema — response shape is undocumented.",
            )
            continue
        if isinstance(schema, dict):
            t = schema.get("type")
            has_shape = any(k in schema for k in ("properties", "items", "$ref", "allOf", "oneOf", "anyOf"))
            if t == "object" and not schema.get("properties") and schema.get("additionalProperties") in (None, True):
                yield _finding(
                    ep,
                    category="loose_schema",
                    severity="warn",
                    status="warn",
                    message=f"Success response {code} is an open object with no declared properties.",
                )
            elif t is None and not has_shape:
                yield _finding(
                    ep,
                    category="loose_schema",
                    severity="info",
                    status="warn",
                    message=f"Success response {code} schema has neither a type nor a structure.",
                )


def check_success_response_declared(ep: Endpoint) -> Iterator[Finding]:
    """Every endpoint should document at least one 2xx success response."""
    if not any(code.startswith("2") for code in ep.responses):
        yield _finding(
            ep,
            category="missing_success_response",
            severity="error",
            status="fail",
            message="No success (2xx) response is documented; the spec only declares "
            f"{sorted(ep.responses)}. Callers have no documented success shape.",
            diff=Diff(expected="a 2xx response", actual=sorted(ep.responses)),
        )


def check_nonstandard_examples(ep: Endpoint) -> Iterator[Finding]:
    """x-examples renders in no standard tooling — a silent doc-quality trap."""
    schema = ep.request_schema or {}
    if isinstance(schema, dict) and _has_x_examples(schema):
        yield _finding(
            ep,
            category="nonstandard_example",
            severity="warn",
            status="warn",
            message="Example is stored under non-standard 'x-examples'; "
            "Swagger/Redoc will not render it as the request example.",
        )


def _has_x_examples(schema: dict, depth: int = 0) -> bool:
    if depth > 4 or not isinstance(schema, dict):
        return False
    if "x-examples" in schema:
        return True
    for v in schema.get("properties", {}).values():
        if isinstance(v, dict) and _has_x_examples(v, depth + 1):
            return True
    return False


def _short(schema, limit: int = 400) -> str:
    import json

    s = json.dumps(schema, default=str)
    return s if len(s) <= limit else s[:limit] + "…"


ALL_CHECKS = [
    check_request_example,
    check_response_examples,
    check_example_validates,
    check_error_responses,
    check_descriptions,
    check_path_params,
    check_response_schema_shape,
    check_success_response_declared,
    check_nonstandard_examples,
]


def run_static_checks(endpoints: list[Endpoint]) -> list[Finding]:
    findings: list[Finding] = []
    for ep in endpoints:
        produced = False
        for check in ALL_CHECKS:
            for f in check(ep):
                findings.append(f)
                if f.status == "fail":
                    produced = True
        if not produced:
            # Record a pass so the dashboard can show coverage, not just failures.
            findings.append(
                Finding(
                    endpoint=ep.key,
                    method=ep.method,
                    path=ep.path,
                    source="static",
                    category="ok",
                    severity="info",
                    status="pass",
                    message="No blocking static issues found.",
                )
            )
    return findings
