"""Render a run's results.json into a single self-contained HTML report.

No external assets, no server, no JavaScript framework — just inline CSS and
native <details> elements for collapsing. Open report.html in any browser, or
publish it as a CI artifact.

The report is organized **per endpoint**: each endpoint is one card that brings
together everything known about it — the live request/response (dynamic stage)
*and* the spec/static + semantic (LLM) findings — so you can see, in one place,
how the documented contract compares with reality.
"""

from __future__ import annotations

import html
import json
from typing import Any

from validator.render_common import SEV_COLOR, SOURCE_LABEL, representative_detail

_SEV_RANK = {"error": 3, "warn": 2, "info": 1}


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
    errors = sum(1 for f in findings if f.get("severity") == "error" and f.get("status") != "pass")
    warns = sum(1 for f in findings if f.get("severity") == "warn" and f.get("status") != "pass")
    passes = sum(1 for f in findings if f.get("status") == "pass")

    parts: list[str] = [_HEAD]
    parts.append("<h1>Harness API Quality &amp; Doc-Drift Report</h1>")
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
        parts.append(
            f"<div class='card {cls}'><div class='num'>{val}</div><div class='lbl'>{label}</div></div>"
        )
    parts.append("</div>")

    parts.append(_endpoints_section(findings))
    parts.append("</body></html>")
    return "".join(parts)


def _group_by_endpoint(findings: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group findings by endpoint key, preserving first-seen order."""
    groups: dict[str, list[dict]] = {}
    for f in findings:
        groups.setdefault(f.get("endpoint", "?"), []).append(f)
    ordered = list(groups.items())
    # Worst endpoints first; stable within the same severity.
    ordered.sort(key=lambda kv: -_endpoint_rank(kv[1]))
    return ordered


def _endpoint_rank(items: list[dict]) -> int:
    rank = 0
    for f in items:
        if f.get("status") != "pass":
            rank = max(rank, _SEV_RANK.get(f.get("severity"), 0))
    return rank


def _endpoints_section(findings: list[dict]) -> str:
    groups = _group_by_endpoint(findings)
    out = [
        "<h2>Endpoints</h2>",
        "<p class='muted'>Each card combines the live call (dynamic) with the "
        "spec &amp; semantic checks (static). Cards with errors are expanded.</p>",
    ]
    for key, items in groups:
        out.append(_endpoint_card(key, items))
    return "".join(out)


def _endpoint_card(key: str, items: list[dict]) -> str:
    static_items = [f for f in items if f.get("source") in ("static", "llm")]
    dyn_items = [f for f in items if f.get("source") == "dynamic"]
    static_issues = [f for f in static_items if f.get("status") != "pass"]
    dyn_issues = [f for f in dyn_items if f.get("status") != "pass"]

    all_issues = static_issues + dyn_issues
    errs = sum(1 for f in all_issues if f.get("severity") == "error")
    warns = sum(1 for f in all_issues if f.get("severity") == "warn")
    infos = sum(1 for f in all_issues if f.get("severity") == "info")

    exercised = bool(dyn_items)
    rep = representative_detail(dyn_items)
    status = rep.get("actual_status", "—")

    # ---- summary line (header) ----
    badges: list[str] = []
    if exercised:
        live_ok = not dyn_issues
        badges.append(
            f"<span class='pill {'ok' if live_ok else 'err'}'>HTTP {_esc(status)}</span>"
        )
    else:
        badges.append("<span class='pill muted'>not run live</span>")
    if errs:
        badges.append(f"<span class='pill err'>{errs} error{'s' if errs != 1 else ''}</span>")
    if warns:
        badges.append(f"<span class='pill warn'>{warns} warning{'s' if warns != 1 else ''}</span>")
    if infos and not errs and not warns:
        badges.append(f"<span class='pill info'>{infos} note{'s' if infos != 1 else ''}</span>")
    if not all_issues:
        badges.append("<span class='pill ok'>clean</span>")

    out = ["<details class='ep'" + (" open" if errs else "") + ">"]
    out.append(
        f"<summary><code>{_esc(key)}</code> <span class='badges'>{''.join(badges)}</span></summary>"
    )
    out.append("<div class='ep-body'>")

    # ---- live call ----
    out.append("<div class='sub'>🌐 Live call — real request &amp; response</div>")
    if exercised:
        out.append("<div class='cols'>")
        out.append("<div><h4>Request</h4>")
        out.append(_code(f"{rep.get('request_method', '')} {rep.get('request_url', key)}"))
        if rep.get("request_query"):
            out.append("<div class='muted'>query</div>" + _code(rep["request_query"]))
        out.append(
            "<div class='muted'>body</div>"
            + _code(rep.get("request_body") if rep.get("request_body") is not None else "(no body)")
        )
        out.append("</div>")
        out.append(f"<div><h4>Response — HTTP {_esc(status)}</h4>")
        out.append(_code(rep.get("actual_body", "—")))
        out.append("</div></div>")
        if dyn_issues:
            out.append("<div class='label'>Doc-drift detected on this call</div>")
            for r in dyn_issues:
                out.append(_finding_line(r))
        else:
            out.append(
                "<div class='okmsg'>✓ Live response matches the documented status and schema.</div>"
            )
    else:
        out.append(
            "<p class='muted'>Not exercised against the live API "
            "(no scenario for this endpoint, or the dynamic stage was skipped).</p>"
        )

    # ---- static / semantic ----
    out.append("<div class='sub'>🔍 Spec &amp; semantic checks</div>")
    if static_issues:
        for r in static_issues:
            out.append(_finding_line(r))
    else:
        out.append("<div class='okmsg'>✓ No blocking static or semantic issues found.</div>")

    out.append("</div></details>")
    return "".join(out)


def _finding_line(r: dict) -> str:
    """One finding row, shown inside its endpoint card (no endpoint repeated)."""
    color = SEV_COLOR.get(r.get("severity"), "#888")
    src = SOURCE_LABEL.get(r.get("source"), r.get("source"))
    diff = r.get("diff") or {}
    diff_html = ""
    if isinstance(diff, dict) and (diff.get("expected") is not None or diff.get("actual") is not None):
        diff_html = (
            "<div class='diff'>"
            f"<div><span class='muted'>spec expected</span>{_code(diff.get('expected'))}</div>"
            f"<div><span class='muted'>actual</span>{_code(diff.get('actual'))}</div>"
            "</div>"
        )
    return (
        f"<div class='finding' style='border-left-color:{color}'>"
        f"<span class='tag'>{_esc(src)}</span> "
        f"<code>{_esc(r.get('category'))}</code> · "
        f"<b style='color:{color}'>{_esc(r.get('severity'))}</b><br>"
        f"{_esc(r.get('message'))}{diff_html}</div>"
    )


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
 .card.bad .num,.card.err .num{color:#d62728} .card.warn .num{color:#ff7f0e} .card.ok .num{color:#2ca02c}
 details.ep{background:#fff;border:1px solid #e3e6ea;border-radius:8px;margin:10px 0;padding:8px 14px}
 details.ep[open]{box-shadow:0 1px 4px rgba(0,0,0,.05)}
 summary{cursor:pointer;font-size:15px;list-style-position:inside}
 summary code{font-size:14px;font-weight:600}
 .badges{float:right} .badges .pill{margin-left:6px}
 .ep-body{padding:6px 2px 4px;border-top:1px solid #eceef1;margin-top:8px}
 .sub{font-weight:700;color:#3a4250;margin:16px 0 6px;font-size:14px}
 .label{font-weight:600;color:#5a626b;margin:10px 0 2px;font-size:13px}
 .cols{display:flex;gap:16px;flex-wrap:wrap} .cols>div{flex:1;min-width:280px}
 h4{margin:6px 0 2px;font-size:13px;color:#5a626b}
 .finding{background:#fbfbfc;border:1px solid #e3e6ea;border-left:4px solid #888;border-radius:6px;
   padding:8px 12px;margin:6px 0}
 .tag{display:inline-block;background:#eceef1;color:#3a4250;font-size:11px;font-weight:600;
   padding:1px 7px;border-radius:10px;margin-right:4px}
 .okmsg{color:#2ca02c;background:#eef8ee;border:1px solid #d6ecd6;border-radius:6px;
   padding:7px 12px;margin:6px 0;font-size:13px}
 .diff{display:flex;gap:14px;flex-wrap:wrap;margin-top:6px} .diff>div{flex:1;min-width:240px}
 .muted{color:#7a828b;font-size:12px}
 .pill{font-size:12px;padding:2px 8px;border-radius:10px;color:#fff;white-space:nowrap}
 .pill.ok{background:#2ca02c} .pill.err{background:#d62728}
 .pill.warn{background:#ff7f0e} .pill.info{background:#1f77b4} .pill.muted{background:#9aa1aa}
</style></head><body>"""


def write_report(result: dict, out_path) -> None:
    from pathlib import Path

    Path(out_path).write_text(build_html(result), encoding="utf-8")
