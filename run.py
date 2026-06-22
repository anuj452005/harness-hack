#!/usr/bin/env python3
"""Local orchestrator — runs the four pipeline steps in order.

Each step is an independent script under steps/ (the same scripts a Harness CI
pipeline runs as separate Run steps). This just chains them for local use:

    1. download spec        (no creds)
    2. dynamic test         (HARNESS_API_KEY + HARNESS_ACCOUNT)
    3. static test          (ANTHROPIC_API_KEY for the LLM part)
    4. build dashboard data (no creds)

    python run.py                 # all four steps
    python run.py --serve         # then launch the dashboard
    python run.py --skip-download  # reuse an already-downloaded spec
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

STEPS_DIR = Path(__file__).resolve().parent / "steps"
STEPS = [
    ("step1_download_spec.py", []),
    ("step2_dynamic_test.py", []),
    ("step3_static_test.py", []),
    ("step4_build_dashboard.py", []),
]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    skip_download = "--skip-download" in argv
    serve = "--serve" in argv

    for script, args in STEPS:
        if skip_download and script.startswith("step1"):
            print("=== skipping step1 (download) ===")
            continue
        if serve and script.startswith("step4"):
            args = args + ["--serve"]
        print(f"\n=== {script} ===", flush=True)
        rc = subprocess.run([sys.executable, str(STEPS_DIR / script)], cwd=str(STEPS_DIR)).returncode
        if rc != 0:
            print(f"step {script} failed (exit {rc})", file=sys.stderr)
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
