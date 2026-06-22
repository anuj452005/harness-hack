"""Streamlit dashboard for the validation results.

Run with:  streamlit run dashboard.py
Reads results.json (override path in the sidebar) and renders summary metrics, a
filterable malfunction table, and a per-endpoint drill-down showing the
spec-vs-reality diff side by side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config import RESULTS_DIR
from validator.render_common import SEV_COLOR, SOURCE_LABEL, representative_detail

st.set_page_config(page_title="Harness API Quality", layout="wide")


@st.cache_data
def load_results(path: str, mtime: float) -> dict:  # mtime busts the cache on re-run
    return json.loads(Path(path).read_text())


def main() -> None:
    st.title("Harness API Quality & Doc-Drift Report")

    default_path = str(RESULTS_DIR / "results.json")
    path = st.sidebar.text_input("results.json path", value=default_path)
    if not Path(path).exists():
        st.warning(f"No results at `{path}`. Run `python run.py` first.")
        return

    data = load_results(path, Path(path).stat().st_mtime)
    findings = data.get("findings", [])
    df = pd.DataFrame(findings)
    if df.empty:
        st.info("No findings recorded.")
        return

    _header(data, df)
    _live_calls_section(df)
    _filters_and_table(df)


def _header(data: dict, df: pd.DataFrame) -> None:
    st.caption(
        f"Module **{data.get('module')}** · base `{data.get('base_url')}` · "
        f"generated {data.get('generated_at', '')[:19]} · "
        f"{data.get('endpoints_total')} endpoints parsed · "
        f"{data.get('endpoints_tested_live')} exercised live"
    )
    malfunctions = df[df["status"] != "pass"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Findings", len(df))
    c2.metric("Malfunctions", len(malfunctions))
    c3.metric("Errors", int((df["severity"] == "error").sum()))
    c4.metric("Warnings", int((df["severity"] == "warn").sum()))
    c5.metric("Passing", int((df["status"] == "pass").sum()))

    st.subheader("Malfunctions by category")
    cat = (
        malfunctions.groupby(["source", "category"]).size().reset_index(name="count")
        if not malfunctions.empty
        else pd.DataFrame(columns=["source", "category", "count"])
    )
    if not cat.empty:
        st.bar_chart(cat.pivot_table(index="category", columns="source", values="count", fill_value=0))


def _live_calls_section(df: pd.DataFrame) -> None:
    """List every live API call with its actual request and response."""
    live = df[df["source"] == "dynamic"]
    if live.empty:
        st.info("No live API calls in this run (dynamic stage was skipped).")
        return

    st.subheader("🌐 Live API calls — real request & response")
    # One block per endpoint actually called, in call order.
    seen: list[str] = []
    for ep in live["endpoint"]:
        if ep not in seen:
            seen.append(ep)

    for ep in seen:
        rows = live[live["endpoint"] == ep]
        rep = representative_detail(rows.to_dict("records"))  # row carrying request/response
        issues = rows[rows["status"] != "pass"]
        status_code = rep.get("actual_status", "—") if rep else "—"
        ok = issues.empty
        badge = "✅" if ok else f"❌ {len(issues)} issue(s)"
        with st.expander(f"{ep}  →  HTTP {status_code}   {badge}", expanded=not ok):
            req_col, resp_col = st.columns(2)
            with req_col:
                st.markdown("**Request**")
                if rep:
                    st.code(
                        f"{rep.get('request_method', '')} {rep.get('request_url', ep)}",
                        language="http",
                    )
                    st.caption("Body")
                    st.code(_fmt(rep.get("request_body")) if rep.get("request_body") is not None
                            else "(no request body)", language="json")
                else:
                    st.write("—")
            with resp_col:
                st.markdown(f"**Response — HTTP {status_code}**")
                st.code(_fmt(rep.get("actual_body")) if rep else "—", language="json")

            if not issues.empty:
                st.markdown("**Doc-drift found on this call:**")
                for _, r in issues.iterrows():
                    color = SEV_COLOR.get(r["severity"], "#888")
                    diff = r.get("diff") or {}
                    extra = ""
                    if isinstance(diff, dict) and (diff.get("expected") is not None or diff.get("actual") is not None):
                        extra = f" &nbsp; <code>spec: {diff.get('expected')}</code> → <code>live: {diff.get('actual')}</code>"
                    st.markdown(
                        f"<div style='border-left:3px solid {color};padding:2px 10px;margin:4px 0'>"
                        f"<code>{r['category']}</code> · <b style='color:{color}'>{r['severity']}</b> — "
                        f"{r['message']}{extra}</div>",
                        unsafe_allow_html=True,
                    )


def _filters_and_table(df: pd.DataFrame) -> None:
    st.sidebar.header("Filters")
    sources = st.sidebar.multiselect("Source", sorted(df["source"].unique()),
                                     default=sorted(df["source"].unique()))
    severities = st.sidebar.multiselect("Severity", ["error", "warn", "info"],
                                        default=["error", "warn"])
    statuses = st.sidebar.multiselect("Status", ["fail", "warn", "pass"],
                                      default=["fail", "warn"])
    search = st.sidebar.text_input("Search endpoint / message")

    view = df[
        df["source"].isin(sources)
        & df["severity"].isin(severities)
        & df["status"].isin(statuses)
    ]
    if search:
        s = search.lower()
        view = view[
            view["endpoint"].str.lower().str.contains(s)
            | view["message"].str.lower().str.contains(s)
        ]

    st.subheader(f"Malfunctions ({len(view)})")
    if view.empty:
        st.success("Nothing matches the current filters.")
        return

    show = view[["endpoint", "source", "severity", "category", "message"]].copy()
    show["source"] = show["source"].map(lambda s: SOURCE_LABEL.get(s, s))
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.subheader("Endpoint drill-down")
    endpoints = sorted(view["endpoint"].unique())
    selected = st.selectbox("Endpoint", endpoints)
    _render_endpoint(view[view["endpoint"] == selected])


def _render_endpoint(rows: pd.DataFrame) -> None:
    for _, r in rows.iterrows():
        color = SEV_COLOR.get(r["severity"], "#888")
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:4px 12px;margin:6px 0'>"
            f"<b>{SOURCE_LABEL.get(r['source'], r['source'])}</b> · "
            f"<code>{r['category']}</code> · <b style='color:{color}'>{r['severity']}</b><br/>"
            f"{r['message']}</div>",
            unsafe_allow_html=True,
        )
        diff = r.get("diff")
        if isinstance(diff, dict) and (diff.get("expected") is not None or diff.get("actual") is not None):
            a, b = st.columns(2)
            a.markdown("**Spec says (expected)**")
            a.code(_fmt(diff.get("expected")), language="json")
            b.markdown("**Reality (actual)**")
            b.code(_fmt(diff.get("actual")), language="json")
        detail = r.get("detail")
        if isinstance(detail, dict) and detail:
            with st.expander("Request / response detail"):
                st.code(_fmt(detail), language="json")


def _fmt(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, default=str)
    return str(value)


if __name__ == "__main__":
    main()
