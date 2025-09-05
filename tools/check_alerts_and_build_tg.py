#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, pathlib, argparse, os

ALERTS_JSON = pathlib.Path("docs/alerts.json")
OUT_TXT     = pathlib.Path("/tmp/tg_msg.txt")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-url", default="", help="Link zum CI-Run")
    args = ap.parse_args()

    try:
        d = json.loads(ALERTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        d = {}

    found = False
    for k in ("mars","venus","family"):
        sec = d.get(k)
        if isinstance(sec, dict) and sec.get("alerts"):
            if len(sec["alerts"]) > 0:
                found = True
                break

    if not found:
        return 0  # kein /tmp/tg_msg.txt => Step sendet nichts

    lines = []
    lines.append("🚨 Alerts-Run (Mars/Venus)")
    if args.run_url:
        lines.append(args.run_url)
    lines.append("")
    lines.append("--- Erste Zeilen aus docs/alerts.json ---")

    # präge Kurzvorschau
    try:
        preview = ALERTS_JSON.read_text(encoding="utf-8").splitlines()[:10]
        lines.extend(preview)
    except Exception:
        pass

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
