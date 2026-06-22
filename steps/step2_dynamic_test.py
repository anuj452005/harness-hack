#!/usr/bin/env python3
"""STEP 2 — Dynamic (live) testing against the real Harness API.

Needs HARNESS_API_KEY (x-api-key) and HARNESS_ACCOUNT (account id); optionally
HARNESS_ORG to reuse an existing org and HARNESS_BASE_URL for the cluster.
Runs the CRUD scenarios in endpoints.yaml, diffs live responses against the
spec, and writes results/dynamic_findings.json. Skips cleanly if creds absent.

    python steps/step2_dynamic_test.py
"""

from __future__ import annotations

import _common as C
from config import load_config


def main() -> int:
    cfg = load_config()
    module, tag, sf, by_key, _ = C.load_scoped_endpoints()

    findings: list[dict] = []
    tested = 0
    if not cfg.can_run_live:
        print("[step2] SKIP — HARNESS_API_KEY / HARNESS_ACCOUNT not set")
    else:
        scenarios = sf.get("scenarios", [])
        if cfg.harness_org:
            for scn in scenarios:
                scn.setdefault("vars", {})["org"] = cfg.harness_org
            print(f"[step2] using existing org '{cfg.harness_org}'")
        print(f"[step2] running {len(scenarios)} scenario(s) against {cfg.base_url}")
        from validator.dynamic_runner import run_scenarios

        dyn = run_scenarios(cfg, by_key, scenarios)
        findings = [f.model_dump() for f in dyn]
        tested = len({f["endpoint"] for f in findings})

    C.write_json(
        C.DYNAMIC_OUT,
        {"base_url": cfg.base_url, "endpoints_tested_live": tested, "findings": findings},
    )
    fails = sum(1 for f in findings if f["status"] == "fail")
    print(f"[step2] {len(findings)} findings ({fails} fail) -> {C.DYNAMIC_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
