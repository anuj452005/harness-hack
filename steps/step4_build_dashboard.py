#!/usr/bin/env python3
"""STEP 4 — Merge findings and update the dashboard data.

Combines results/static_findings.json + results/dynamic_findings.json into
results/results.json (the file the Streamlit dashboard reads). Needs no
credentials. Pass --serve to also launch the dashboard locally.

    python steps/step4_build_dashboard.py
    python steps/step4_build_dashboard.py --serve
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys

import _common as C


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    static = C.read_json(C.STATIC_OUT)
    dynamic = C.read_json(C.DYNAMIC_OUT)
    if not static and not dynamic:
        print("[step4] ERROR: no findings to merge — run steps 2 and/or 3 first.", file=sys.stderr)
        return 1

    findings = list(static.get("findings", [])) + list(dynamic.get("findings", []))
    # Timestamp is supplied via env in CI (SOURCE_DATE), else stamped here.
    generated = os.environ.get("SOURCE_DATE") or _dt.datetime.now(_dt.timezone.utc).isoformat()

    result = {
        "module": static.get("module", dynamic.get("module", "unknown")),
        "base_url": dynamic.get("base_url", ""),
        "generated_at": generated,
        "endpoints_total": static.get("endpoints_total", 0),
        "endpoints_tested_live": dynamic.get("endpoints_tested_live", 0),
        "findings": findings,
    }
    C.write_json(C.RESULTS_OUT, result)

    # Self-contained HTML report (open without Streamlit / publish as CI artifact).
    from validator.report import write_report

    report_path = C.RESULTS_OUT.parent / "report.html"
    write_report(result, report_path)

    counts = {"pass": 0, "warn": 0, "fail": 0}
    for f in findings:
        counts[f.get("status", "warn")] = counts.get(f.get("status", "warn"), 0) + 1
    print(
        f"[step4] merged {len(findings)} findings "
        f"(pass={counts['pass']} warn={counts['warn']} fail={counts['fail']})"
    )
    print(f"[step4]   data   -> {C.RESULTS_OUT}")
    print(f"[step4]   report -> {report_path}")

    if "--serve" in argv:
        print("[step4] launching dashboard at http://localhost:8501")
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(C.P1_ROOT / "dashboard.py")],
            cwd=str(C.P1_ROOT),
        )
    else:
        print("[step4] view it:  streamlit run dashboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
