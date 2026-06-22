#!/usr/bin/env python3
"""STEP 1 — Download the OpenAPI spec.

Needs no credentials. Downloads the spec that apidocs.harness.io is generated
from (override with SPEC_URL) and saves it to the path the configured module
expects, so later steps can load it.

    python steps/step1_download_spec.py
"""

from __future__ import annotations

import os
import sys

import httpx

import _common as C
from config import module_spec_path

DEFAULT_SPEC_URL = "https://apidocs.harness.io/_bundle/index.yaml"


def main() -> int:
    url = os.environ.get("SPEC_URL", DEFAULT_SPEC_URL)
    module, _, _ = C.scope()
    out = module_spec_path(module)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[step1] downloading spec for module '{module}'")
    print(f"        {url}")
    try:
        r = httpx.get(url, timeout=180, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        print(f"[step1] ERROR: download failed: {e}", file=sys.stderr)
        return 1

    out.write_bytes(r.content)
    print(f"[step1] saved {len(r.content):,} bytes -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
