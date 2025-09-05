#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, pathlib, datetime

ALERTS_JSON = pathlib.Path("docs/alerts.json")
OUT_MD      = pathlib.Path("docs/alerts_brief.md")

def main():
    try:
        data = json.loads(ALERTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Alerts Brief — {ts}", ""]

    for sec in ("mars", "venus", "family"):
        lines.append(f"## {sec}")
        alerts = (data.get(sec) or {}).get("alerts", [])
        if not alerts:
            lines.append("_(keine Alerts)_\n")
            continue

        for a in alerts[:10]:
            topic = a.get("ticker") or a.get("topic") or "?"
            sc = a.get("score", "?")
            cf = a.get("confidence", "?")
            what = (a.get("what") or "").strip()
            lines.append(f"- **{topic}** — Score {sc} | Confidence {cf}\n  {what}")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
