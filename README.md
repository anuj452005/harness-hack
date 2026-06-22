# Harness API Quality & Doc-Drift Validator

Finds where Harness OpenAPI specs/docs disagree with the live API — broken/missing
examples, schema mismatches, undocumented response fields, wrong status codes, and
more — then shows every "malfunction" in a dashboard with the spec-vs-reality diff.

Scope: deep on the **ng-manager** orgs/projects surface; the engine is generic and
runs against any module via `--module`.

## Pipeline

```
openapi.yaml → spec_loader → static_checks (+ LLM) ┐
                           → dynamic_runner (live CRUD) ┴→ results.json → dashboard
```

- **Static (deterministic):** missing examples, example-vs-schema validation, missing
  error responses, path-param mismatches, loose/empty response schemas, non-standard
  `x-examples`, missing descriptions.
- **Static (LLM, Anthropic):** description-vs-schema contradictions, unrealistic
  examples, ambiguous docs, inconsistencies. Skipped gracefully without a key.
- **Dynamic:** runs documented CRUD scenarios live (`POST→GET→PUT→DELETE`) with
  `apiqual_*` identifiers and automatic teardown; diffs real responses against the
  declared schema and status codes.

## Setup

```bash
cd p1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in keys (only needed for live + LLM stages)
```

## Run

```bash
python run.py --static-only          # no network, no keys needed
python run.py                         # full run (uses .env if present)
python run.py --module access-control # point at another module
streamlit run dashboard.py            # view the report
```

Output is written to `results/results.json`.

## Tests

```bash
python -m pytest -q
```

## Config

- `endpoints.yaml` — curated live CRUD scenarios (which endpoints to exercise).
- `.env` — `HARNESS_API_KEY` (x-api-key), `HARNESS_ACCOUNT`, `ANTHROPIC_API_KEY`.
# harness-hack
