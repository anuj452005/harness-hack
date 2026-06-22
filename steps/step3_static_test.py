#!/usr/bin/env python3
"""STEP 3 — Static testing of the spec.

Deterministic checks need no credentials. The semantic (LLM) checks call
Anthropic and run only if ANTHROPIC_API_KEY is set (otherwise skipped cleanly).
Writes results/static_findings.json.

    python steps/step3_static_test.py
"""

from __future__ import annotations

import os

import _common as C
from config import load_config
from validator import static_checks


def main() -> int:
    cfg = load_config()
    module, tag, sf, _, filtered = C.load_scoped_endpoints()
    label = f"{module} [{tag}]" if tag else module
    print(f"[step3] static checks on {len(filtered)} endpoint(s) ({label})")

    findings = [f.model_dump() for f in static_checks.run_static_checks(filtered)]

    if cfg.can_run_llm:
        limit = int(os.environ.get("LLM_LIMIT", "15"))
        print(f"[step3] LLM semantic checks (≤{limit} endpoints)")
        from validator import llm_checks

        findings += [
            f.model_dump()
            for f in llm_checks.run_llm_checks(filtered, cfg.anthropic_api_key, max_endpoints=limit)
        ]
    else:
        print("[step3] SKIP LLM — ANTHROPIC_API_KEY not set")

    C.write_json(
        C.STATIC_OUT,
        {"module": label, "endpoints_total": len(filtered), "findings": findings},
    )
    fails = sum(1 for f in findings if f["status"] == "fail")
    print(f"[step3] {len(findings)} findings ({fails} fail) -> {C.STATIC_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
