"""Shared helpers for the pipeline steps.

Each step under steps/ is an independent, runnable script (a Harness CI "Run"
step). They communicate only through JSON artifacts in results/, so any step can
run on its own as long as its inputs exist:

    results/dynamic_findings.json   <- step 2 (live API)
    results/static_findings.json    <- step 3 (spec + LLM)
    results/results.json            <- step 4 (merged; what the dashboard reads)

Scope (which module/tag) and live scenarios come from endpoints.yaml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

P1_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(P1_ROOT))  # make config / validator importable

import yaml  # noqa: E402

from config import RESULTS_DIR, module_spec_path  # noqa: E402
from validator.spec_loader import load_endpoints  # noqa: E402

SCENARIO_FILE = P1_ROOT / "endpoints.yaml"
DYNAMIC_OUT = RESULTS_DIR / "dynamic_findings.json"
STATIC_OUT = RESULTS_DIR / "static_findings.json"
RESULTS_OUT = RESULTS_DIR / "results.json"


def scenario_file() -> dict:
    if not SCENARIO_FILE.exists():
        return {}
    return yaml.safe_load(SCENARIO_FILE.read_text()) or {}


def scope() -> tuple[str, str | None, dict]:
    """(module, tag_filter, scenario_file_dict)."""
    sf = scenario_file()
    return sf.get("module", "apidocs"), sf.get("tag_filter"), sf


def load_scoped_endpoints():
    """Returns (module, tag, scenario_dict, endpoints_by_key, filtered_endpoints)."""
    module, tag, sf = scope()
    spec_path = module_spec_path(module)
    if not spec_path.exists():
        raise FileNotFoundError(
            f"Spec not found at {spec_path}. Run step 1 (download_spec) first."
        )
    endpoints = load_endpoints(spec_path)
    by_key = {e.key: e for e in endpoints}
    filtered = [e for e in endpoints if tag in e.tags] if tag else endpoints
    return module, tag, sf, by_key, filtered


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())
