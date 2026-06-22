"""Render a run's results.json into a single self-contained HTML report.

No external assets, no server, no JavaScript framework — just inline CSS and
native <details> elements for collapsing. Open report.html in any browser, or
publish it as a CI artifact. Mirrors the Streamlit dashboard: summary metrics,
live API calls with real request/response, and every finding with its diff.
"""

from __future__ import annotations

import html
import json
from typing import Any

SEV_COLOR = {"error": "#d62728", "warn": "#e8890c", "info": "#1f77b4"}
SOURCE_LABEL = {"static": "🔍 Static", "llm": "🤖 LLM", "dynamic": "🌐 Live"}


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _code(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, indent=2, default=str)
    else:
        text = str(value)
    return f"<pre>{html.escape(text)}</pre>"


def build_html(result: dict) -> str:
    findings = result.get("findings", [])
    malfunctions = [f for f in findings if f.get("status") != "pass"]
    errors = sum(1 for f in findings if f.get("severity") == "error")
    warns = sum(1 for f in findings if f.get("severity") == "warn")
    passes = sum(1 for f in findings if f.get("status") == "pass")

    parts: list[str] = [_HEAD]
    parts.append(f"<h1>Harness API Quality &amp; Doc-Drift Report</h1>")
    parts.append(
        f"<p class='meta'>Module <b>{_esc(result.get('module'))}</b> · "
        f"base <code>{_esc(result.get('base_url'))}</code> · "
        f"generated {_esc(str(result.get('generated_at'))[:19])} · "
        f"{_esc(result.get('endpoints_total'))} endpoints · "
        f"{_esc(result.get('endpoints_tested_live'))} exercised live</p>"
    )

    # Metric cards
    parts.append("<div class='cards'>")
    for label, val, cls in [
        ("Findings", len(findings), ""),
        ("Malfunctions", len(malfunctions), "bad"),
        ("Errors", errors, "err"),
        ("Warnings", warns, "warn"),
        ("Passing", passes, "ok"),
    ]:
        parts.append(f"<div class='card {cls}'><div class='num'>{val}</div><div class='lbl'>{label}</div></div>")
    parts.append("</div>")

    parts.append(_live_section(findings))
    parts.append(_findings_section(findings))
    parts.append("</body></html>")
    return "".join(parts)


def _live_section(findings: list[dict]) -> str:
    live = [f for f in findings if f.get("source") == "dynamic"]
    if not live:
        return "<h2>🌐 Live API calls</h2><p class='muted'>Dynamic stage was skipped (no Harness credentials).</p>"

    order: list[str] = []
    for f in live:
        if f["endpoint"] not in order:
            order.append(f["endpoint"])

    out = ["<h2>🌐 Live API calls — real request &amp; response</h2>"]
    for ep in order:
        rows = [f for f in live if f["endpoint"] == ep]
        rep = _representative(rows)
        issues = [r for r in rows if r.get("status") != "pass"]
        status = rep.get("actual_status", "—")
        badge = ("<span class='pill ok'>OK</span>" if not issues
                 else f"<span class='pill err'>{len(issues)} issue(s)</span>")
        out.append("<details" + (" open" if issues else "") + ">")
        out.append(f"<summary><code>{_esc(ep)}</code> → HTTP {_esc(status)} {badge}</summary>")
        out.append("<div class='cols'>")
        out.append("<div><h4>Request</h4>")
        out.append(_code(f"{rep.get('request_method','')} {rep.get('request_url', ep)}"))
        if rep.get("request_query"):
            out.append("<div class='muted'>query</div>" + _code(rep["request_query"]))
        out.append("<div class='muted'>body</div>" +
                   _code(rep.get("request_body") if rep.get("request_body") is not None else "(no body)"))
        out.append("</div>")
        out.append(f"<div><h4>Response — HTTP {_esc(status)}</h4>")
        out.append(_code(rep.get("actual_body", "—")))
        out.append("</div></div>")
        if issues:
            out.append("<h4>Doc-drift on this call</h4>")
            for r in issues:
                out.append(_finding_line(r))
        out.append("</details>")
    return "".join(out)


def _findings_section(findings: list[dict]) -> str:
    out = ["<h2>All findings</h2>"]
    for src in ("static", "llm", "dynamic"):
        group = [f for f in findings if f.get("source") == src and f.get("status") != "pass"]
        if not group:
            continue
        out.append(f"<h3>{SOURCE_LABEL.get(src, src)} ({len(group)})</h3>")
        for r in group:
            out.append(_finding_line(r))
    return "".join(out)


def _finding_line(r: dict) -> str:
    color = SEV_COLOR.get(r.get("severity"), "#888")
    diff = r.get("diff") or {}
    diff_html = ""
    if isinstance(diff, dict) and (diff.get("expected") is not None or diff.get("actual") is not None):
        diff_html = (
            "<div class='diff'>"
            f"<div><span class='muted'>spec expected</span>{_code(diff.get('expected'))}</div>"
            f"<div><span class='muted'>live actual</span>{_code(diff.get('actual'))}</div>"
            "</div>"
        )
    return (
        f"<div class='finding' style='border-left-color:{color}'>"
        f"<code>{_esc(r.get('endpoint'))}</code> · "
        f"<code>{_esc(r.get('category'))}</code> · "
        f"<b style='color:{color}'>{_esc(r.get('severity'))}</b><br>"
        f"{_esc(r.get('message'))}{diff_html}</div>"
    )


def _representative(rows: list[dict]) -> dict:
    for r in rows:
        d = r.get("detail")
        if isinstance(d, dict) and ("actual_body" in d or "request_url" in d):
            return d
    return {}


_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harness API Quality Report</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;
   background:#f6f7f9;color:#1b1f24;line-height:1.45}
 h1{margin:0 0 4px} h2{margin-top:32px;border-bottom:2px solid #e3e6ea;padding-bottom:6px}
 .meta{color:#5a626b;margin:0 0 18px}
 code{background:#eceef1;padding:1px 5px;border-radius:4px;font-size:.9em}
 pre{background:#0d1117;color:#e6edf3;padding:10px;border-radius:6px;overflow:auto;font-size:12px;margin:4px 0}
 .cards{display:flex;gap:12px;flex-wrap:wrap}
 .card{background:#fff;border:1px solid #e3e6ea;border-radius:10px;padding:14px 20px;min-width:110px;text-align:center}
 .card .num{font-size:28px;font-weight:700} .card .lbl{color:#5a626b;font-size:13px}
 .card.bad .num,.card.err .num{color:#d62728} .card.warn .num{color:#e8890c} .card.ok .num{color:#2ca02c}
 details{background:#fff;border:1px solid #e3e6ea;border-radius:8px;margin:8px 0;padding:6px 12px}
 summary{cursor:pointer;font-size:15px} summary code{font-size:14px}
 .cols{display:flex;gap:16px;flex-wrap:wrap} .cols>div{flex:1;min-width:280px}
 h4{margin:10px 0 2px}
 .finding{background:#fff;border:1px solid #e3e6ea;border-left:4px solid #888;border-radius:6px;
   padding:8px 12px;margin:6px 0}
 .diff{display:flex;gap:14px;flex-wrap:wrap;margin-top:6px} .diff>div{flex:1;min-width:240px}
 .muted{color:#7a828b;font-size:12px} .pill{font-size:12px;padding:2px 8px;border-radius:10px;color:#fff}
 .pill.ok{background:#2ca02c} .pill.err{background:#d62728}
</style></head><body>"""


def write_report(result: dict, out_path) -> None:
    from pathlib import Path

    Path(out_path).write_text(build_html(result), encoding="utf-8")
