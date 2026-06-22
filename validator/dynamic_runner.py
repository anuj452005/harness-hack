

"""Drive the live Harness API and compare reality against the spec.

The runner executes *scenarios* — ordered sequences of real HTTP calls that
create a resource, read it back, update it, then delete it for cleanup. Each call
records the expected status (from the spec) vs the actual status, and diffs the
returned body against the declared response schema. Teardown always runs.

Scenarios are defined declaratively in ``endpoints.yaml`` and resolved here so the
live surface tested is explicit and auditable.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from config import Config
from validator.diffing import compare_response
from validator.models import Diff, Endpoint, Finding
from validator.synth import synthesize


class LiveClient:
    def __init__(self, cfg: Config, timeout: float = 30.0):
        self.base_url = cfg.base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": cfg.harness_api_key or "",
            "Harness-Account": cfg.harness_account or "",
        }
        self._client = httpx.Client(timeout=timeout, headers=self.headers)

    def request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        return self._client.request(method.upper(), url, json=body, params=params or None)

    def close(self) -> None:
        self._client.close()


def _finding(ep_key: str, method: str, path: str, **kw) -> Finding:
    return Finding(endpoint=ep_key, method=method, path=path, source="dynamic", **kw)


def _expected_success_code(ep: Endpoint) -> Optional[str]:
    for code in ("200", "201", "204"):
        if code in ep.responses:
            return code
    for code in ep.responses:
        if code.startswith("2"):
            return code
    return None


def _success_schema(ep: Endpoint, code: str | None) -> Optional[dict]:
    if code and code in ep.responses:
        return ep.responses[code].get("schema")
    return None


# Standard Harness scope query params -> the scenario context key they read from.
# The Harness NextGen API is account/org/project scoped via these query params,
# so they are auto-filled whenever an endpoint declares them.
_SCOPE_QUERY = {
    "accountIdentifier": "account",
    "orgIdentifier": "org",
    "projectIdentifier": "project",
}


def _build_query(ep: Endpoint, ctx: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    """Query params for a live call: auto-filled scope params + explicit overrides.

    Only params the endpoint actually declares as ``in: query`` are auto-filled;
    ``query_overrides`` from the scenario step are rendered against the context
    and take precedence.
    """
    declared = {
        p.get("name")
        for p in ep.parameters
        if isinstance(p, dict) and p.get("in") == "query"
    }
    query: dict[str, Any] = {}
    for param_name, ctx_key in _SCOPE_QUERY.items():
        if param_name in declared and ctx.get(ctx_key) is not None:
            query[param_name] = ctx[ctx_key]
    for k, v in step.get("query_overrides", {}).items():
        query[k] = _render(v, ctx) if isinstance(v, str) else v
    return query


def run_call(
    client: LiveClient,
    ep: Endpoint,
    path: str,
    body: Optional[dict],
    query: Optional[dict] = None,
) -> tuple[list[Finding], httpx.Response | None]:
    """Execute one live call and emit findings about status + response shape."""
    findings: list[Finding] = []
    expected_code = _expected_success_code(ep)
    try:
        resp = client.request(ep.method, path, body, query)
    except httpx.HTTPError as e:
        findings.append(
            _finding(
                ep.key, ep.method, path,
                category="request_error", severity="error", status="fail",
                message=f"Live request failed: {e}",
                detail={"request_body": body, "request_query": query or {}},
            )
        )
        return findings, None

    actual_code = str(resp.status_code)
    try:
        actual_body = resp.json()
    except (json.JSONDecodeError, ValueError):
        actual_body = resp.text

    detail = {
        "request_method": ep.method.upper(),
        "request_url": f"{client.base_url}{path}",
        "request_query": query or {},
        "request_body": body,
        "actual_status": actual_code,
        "actual_body": _truncate(actual_body),
    }

    # 1. Status-code agreement with the spec.
    if expected_code and actual_code != expected_code and not actual_code.startswith("2"):
        findings.append(
            _finding(
                ep.key, ep.method, path,
                category="status_mismatch", severity="error", status="fail",
                message=f"Spec documents {expected_code} but live API returned {actual_code}.",
                diff=Diff(expected=expected_code, actual=actual_code),
                detail=detail,
            )
        )
    elif expected_code and actual_code != expected_code and actual_code.startswith("2"):
        findings.append(
            _finding(
                ep.key, ep.method, path,
                category="status_mismatch", severity="warn", status="warn",
                message=f"Spec documents {expected_code} but live API returned {actual_code} (both success).",
                diff=Diff(expected=expected_code, actual=actual_code),
                detail=detail,
            )
        )

    # 2. If the call succeeded, diff the body against the documented schema.
    if actual_code.startswith("2") and isinstance(actual_body, (dict, list)):
        schema = _success_schema(ep, expected_code if actual_code == expected_code else actual_code)
        for d in compare_response(schema, actual_body):
            sev = "error" if d["kind"] == "type_mismatch" else "warn"
            findings.append(
                _finding(
                    ep.key, ep.method, path,
                    category=f"response_{d['kind']}", severity=sev, status="fail",
                    message=d["message"],
                    diff=Diff(expected=d["expected"], actual=d["actual"]),
                    detail={**detail, "field": d["field"]},
                )
            )

    # 3. If the call failed unexpectedly, record the live error shape.
    if not actual_code.startswith("2"):
        documented = actual_code in ep.responses
        findings.append(
            _finding(
                ep.key, ep.method, path,
                category="live_error",
                severity="error" if not documented else "info",
                status="fail" if not documented else "warn",
                message=(
                    f"Live call returned {actual_code}"
                    + ("" if documented else " which is NOT documented for this endpoint")
                    + "."
                ),
                diff=Diff(expected=sorted(ep.responses), actual=actual_code),
                detail=detail,
            )
        )

    # 4. Nothing wrong -> pass.
    if not findings:
        findings.append(
            _finding(
                ep.key, ep.method, path,
                category="ok", severity="info", status="pass",
                message=f"Live call returned {actual_code}; response matches the documented schema.",
                detail=detail,
            )
        )
    return findings, resp


def run_scenarios(
    cfg: Config,
    endpoints_by_key: dict[str, Endpoint],
    scenarios: list[dict[str, Any]],
) -> list[Finding]:
    """Execute each CRUD scenario; always tears down created resources."""
    client = LiveClient(cfg)
    findings: list[Finding] = []
    try:
        for scn in scenarios:
            findings.extend(_run_one_scenario(client, cfg, endpoints_by_key, scn))
    finally:
        client.close()
    return findings


def _run_one_scenario(
    client: LiveClient,
    cfg: Config,
    endpoints_by_key: dict[str, Endpoint],
    scn: dict[str, Any],
) -> list[Finding]:
    findings: list[Finding] = []
    ctx = {"account": cfg.harness_account, **scn.get("vars", {})}
    created: list[dict[str, Any]] = []  # steps to tear down, in reverse order

    for step in scn.get("steps", []):
        # Skip setup/teardown steps when a prerequisite var is already supplied
        # (e.g. reuse an existing org instead of creating a throwaway one).
        skip_var = step.get("skip_if_var")
        if skip_var and ctx.get(skip_var):
            continue
        key = step["endpoint"]  # e.g. "POST /v1/orgs"
        ep = endpoints_by_key.get(key)
        if ep is None:
            findings.append(
                Finding(
                    endpoint=key, method=key.split()[0].lower(), path=key.split()[-1],
                    source="dynamic", category="config_error", severity="warn",
                    status="warn", message=f"Scenario references unknown endpoint '{key}'.",
                )
            )
            continue

        path = _render(ep.path, ctx)
        body = None
        if ep.method in ("post", "put"):
            overrides = {k: _render(v, ctx) if isinstance(v, str) else v
                         for k, v in step.get("body_overrides", {}).items()}
            body = synthesize(ep.request_schema, overrides)
        query = _build_query(ep, ctx, step)

        step_findings, resp = run_call(client, ep, path, body, query)
        findings.extend(step_findings)

        # Capture identifiers from a successful create for later steps + teardown.
        if resp is not None and str(resp.status_code).startswith("2") and step.get("capture"):
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {}
            for var, jsonpath in step["capture"].items():
                ctx[var] = _extract(data, jsonpath)
        if step.get("teardown_with"):
            created.append({"endpoint": step["teardown_with"], "ctx": dict(ctx)})

    # Teardown in reverse creation order.
    for item in reversed(created):
        ep = endpoints_by_key.get(item["endpoint"])
        if ep is None:
            continue
        path = _render(ep.path, item["ctx"])
        query = _build_query(ep, item["ctx"], {})
        try:
            client.request(ep.method, path, params=query)
        except httpx.HTTPError:
            pass
    return findings


def _render(template: Any, ctx: dict[str, Any]) -> Any:
    if not isinstance(template, str):
        return template
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _extract(data: Any, dotted: str) -> Any:
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _truncate(value: Any, limit: int = 2000) -> Any:
    s = json.dumps(value, default=str) if not isinstance(value, str) else value
    return value if len(s) <= limit else (s[:limit] + "…")
