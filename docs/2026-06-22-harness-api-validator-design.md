# Harness API Quality & Doc-Drift Validator — Design

**Date:** 2026-06-22
**Problem:** Harness exposes hundreds of APIs via OpenAPI specs. Docs drift from real
behavior — examples break, fields change, required/optional flips. There is no automated
way to know which APIs are misrepresented. This tool finds those "malfunctions".

## Scope

- **One module, deep:** `ng-manager`, the orgs/projects CRUD surface (~10–15 endpoints).
- Engine is **generic** — point it at any module's `openapi.yaml` via `--module`.
- 48h hackathon build, local Python only.

## Architecture & data flow

```
openapi.yaml (ng-manager)
        │
   spec_loader.py   ── resolve $refs, extract per-endpoint model
        │
        ├──────────► static_checks.py  (deterministic) + llm_checks.py (Anthropic)
        │
        └──────────► dynamic_runner.py (live CRUD on app.harness.io + teardown)
                                 │
                          results.json  (unified Finding schema)
                                 │
                          dashboard.py  (Streamlit: metrics, malfunctions, diffs)
```

Stages share only the `Endpoint` model and `results.json`. Orchestrated by `run.py`
with flags `--module`, `--static-only`, `--dynamic-only`, `--no-llm`.

## Components

- **config.py** — env-driven: `HARNESS_API_KEY`, `HARNESS_ACCOUNT`, `ANTHROPIC_API_KEY`,
  base URL (`https://app.harness.io`). `endpoints.yaml` curates the live-tested endpoints.
- **spec_loader.py** — PyYAML + jsonref; yields `Endpoint(method, path, operation_id,
  params, request_schema, request_example, responses_by_status, descriptions)`.
- **static_checks.py** (deterministic): missing request/response examples; example does not
  validate against schema; missing error responses (400/401/403/404/500); required-vs-optional
  gaps; missing descriptions/summaries; path-param vs declared-param mismatch; empty/loose
  response schema; non-standard example placement (`x-examples`).
- **llm_checks.py** (Anthropic): description-vs-schema mismatch, example realism, ambiguous
  or contradictory docs, cross-version inconsistency. Degrades gracefully if key/network absent.
- **dynamic_runner.py** — builds a real request from the spec (synthesizes a valid body when
  no example exists, honoring patterns/min/max), runs CRUD `POST→GET→PUT→DELETE` with
  `apiqual_<ts>` identifiers, teardown in `finally`. Records expected vs actual status + body.
- **diffing.py** — diffs the live response against the declared response schema: undocumented
  fields, documented-but-missing fields, type mismatches, status-code mismatch, error-format.
- **models.py** — one `Finding` (pydantic): `endpoint, method, source(static|dynamic|llm),
  category, severity(info|warn|error), status(pass|warn|fail), message, diff{expected,actual}`.
- **dashboard.py** — Streamlit: summary metrics; filterable malfunction table (source/severity/
  endpoint); per-endpoint drill-down with side-by-side, color-coded diff.

## Error handling

- Missing live creds → dynamic stage skipped with a banner; static still runs.
- LLM/network failure → fall back to deterministic findings; never crash.
- Live API errors captured **as findings**, not exceptions. Cleanup always in `finally`.

## Testing

- Fixture OpenAPI with known defects → each deterministic check asserted to fire.
- Unit tests for spec_loader ref-resolution and response-diff logic.
- dynamic_runner tested against mocked responses (no live calls in tests).

## Tech stack

Python 3.11+ · PyYAML + jsonref · jsonschema · httpx · anthropic SDK · pydantic · Streamlit.
