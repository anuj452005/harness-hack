"""Shared rendering helpers used by both result renderers.

The Streamlit dashboard (``dashboard.py``) and the self-contained HTML report
(``validator/report.py``) present the same ``results.json`` in two formats, so
they share the severity palette, the source labels, and the logic for finding
the row that carries a live call's real request/response payload.
"""

from __future__ import annotations

from typing import Any

# Severity -> color (Tableau palette: red / orange / blue).
SEV_COLOR = {"error": "#d62728", "warn": "#ff7f0e", "info": "#1f77b4"}
SOURCE_LABEL = {"static": "🔍 Static", "llm": "🤖 LLM", "dynamic": "🌐 Live"}


def representative_detail(rows: list[dict]) -> dict:
    """Pick the row whose ``detail`` carries the real request/response payload.

    Accepts any iterable of finding-like mappings (plain dicts or pandas rows).
    """
    for r in rows:
        d = r.get("detail")
        if isinstance(d, dict) and ("actual_body" in d or "request_url" in d):
            return d
    return {}
