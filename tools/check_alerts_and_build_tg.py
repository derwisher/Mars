#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/check_alerts_and_build_tg.py
Prüft, ob in docs/alerts.json Alerts vorhanden sind.
Falls ja, baut eine Telegram-Message in /tmp/tg_msg.txt
"""

from __future__ import annotations
import json
import argparse
from pathlib import Path

DOCS = Path("docs")
ALERTS_JSON = DOCS / "alerts.json"
TG_MSG = Path("/tmp/tg_msg.txt")

def has_alerts(d: dict) -> bool:
    for k in ("mars", "venus", "family"):
        sec = d.get(k)
        if isinstance(sec, dict) and isinstance(sec.get("alerts"), list):
            if len(sec["alerts"]) > 0:
                return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-url", default="", help="Link zum Actions-Run")
    args = ap.parse_args()

    try:
        d = json.loads(ALERTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return  # keine Datei / ungültig -> kein TG

    if not has_alerts(d):
        return

    # Message aufbauen
    lines = []
    lines.append("🚨 Alerts-Run (Mars/Venus) – Details:")
    if args.run_url:
        lines.append(args.run_url)
    lines.append("")
    lines.append("--- Erste Zeilen aus docs/alerts.json ---")

    try:
        preview = "\n".join(ALERTS_JSON.read_text(encoding="utf-8").splitlines()[:10])
    except Exception:
        preview = "{}"
    lines.append(preview)

    TG_MSG.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()
