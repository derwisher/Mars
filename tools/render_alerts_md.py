#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/render_alerts_md.py
Erzeugt aus docs/alerts.json einen kurzen Markdown-Brief docs/alerts_brief.md
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

DOCS = Path("docs")
ALERTS_JSON = DOCS / "alerts.json"
BRIEF_MD = DOCS / "alerts_brief.md"

def load_alerts() -> dict:
    try:
        return json.loads(ALERTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def render_brief(data: dict) -> str:
    lines = [f"# Alerts Brief — {now_utc()}", ""]
    for sec in ("mars", "venus", "family"):
        lines.append(f"## {sec}")
        alerts = (data.get(sec) or {}).get("alerts", [])
        if not alerts:
            lines.append("_(keine Alerts)_")
            lines.append("")
            continue
        for a in alerts[:10]:
            topic = a.get("ticker") or a.get("topic") or "?"
            sc = a.get("score", "?")
            cf = a.get("confidence", "?")
            what = (a.get("what") or "").strip()
            lines.append(f"- **{topic}** — Score {sc} | Confidence {cf}\n  {what}")
        lines.append("")
    return "\n".join(lines)

def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    data = load_alerts()
    BRIEF_MD.write_text(render_brief(data), encoding="utf-8")
    print(f"[OK] wrote {BRIEF_MD}")

if __name__ == "__main__":
    main()
