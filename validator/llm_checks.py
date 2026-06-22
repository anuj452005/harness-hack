"""Semantic doc-quality checks using the Anthropic API.

These catch issues the deterministic checks cannot: a description that contradicts
the schema, an example that is syntactically valid but semantically nonsensical,
ambiguous wording, or cross-version drift. The model is asked to return strict
JSON. Any failure (no key, network error, bad JSON) degrades gracefully to an
empty list — the run never depends on the LLM being available.
"""

from __future__ import annotations

import json
from typing import Any

from validator.models import Endpoint, Finding

MODEL = "claude-sonnet-4-6"
SYSTEM = (
    "You are an API documentation quality auditor. You are given one OpenAPI "
    "operation (already $ref-resolved). Identify concrete documentation-quality "
    "problems: descriptions that contradict the schema, unrealistic or "
    "unrunnable examples, ambiguous or missing semantics, and inconsistencies. "
    "Do NOT report purely stylistic nits. Respond ONLY with a JSON array; each "
    "item must be an object with keys: category (one of "
    "'description_schema_mismatch','unrealistic_example','ambiguous_doc',"
    "'inconsistency'), severity ('info'|'warn'|'error'), and message (a concise, "
    "specific sentence). Return [] if there are no real problems."
)


def _endpoint_payload(ep: Endpoint) -> str:
    return json.dumps(
        {
            "method": ep.method,
            "path": ep.path,
            "operationId": ep.operation_id,
            "summary": ep.summary,
            "description": ep.description,
            "parameters": ep.parameters,
            "requestSchema": ep.request_schema,
            "requestExample": ep.request_example,
            "responses": ep.responses,
        },
        default=str,
    )[:12000]


def run_llm_checks(
    endpoints: list[Endpoint], api_key: str, max_endpoints: int | None = None
) -> list[Finding]:
    try:
        import anthropic
    except ImportError:
        return []
    client = anthropic.Anthropic(api_key=api_key)
    findings: list[Finding] = []
    targets = endpoints if max_endpoints is None else endpoints[:max_endpoints]
    for ep in targets:
        findings.extend(_check_one(client, ep))
    return findings


def _check_one(client: Any, ep: Endpoint) -> list[Finding]:
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": _endpoint_payload(ep)}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        items = _parse_json_array(text)
    except Exception:
        return []  # graceful degradation — LLM is best-effort

    out: list[Finding] = []
    for item in items:
        if not isinstance(item, dict) or "message" not in item:
            continue
        sev = item.get("severity", "warn")
        sev = sev if sev in ("info", "warn", "error") else "warn"
        out.append(
            Finding(
                endpoint=ep.key,
                method=ep.method,
                path=ep.path,
                source="llm",
                category=str(item.get("category", "llm_finding")),
                severity=sev,
                status="warn" if sev == "info" else "fail",
                message=str(item["message"]),
            )
        )
    return out


def _parse_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
