#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/run_alerts.py
Kombinierte, robuste Fassung:
- keine Klarnamen (nur 'mars', 'venus', 'family')
- kompatible Imports (alerts_engine nebenan ODER in tools/)
- sauberer JSON-Preview und Output nach data/alerts_out.json
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

# ------------------------------------------------------------
# Import-Strategie: zuerst lokal (gleiches Verzeichnis), dann tools/
# ------------------------------------------------------------
_run_alerts_func = None
try:
    from alerts_engine import run_alerts as _run_alerts_func  # wenn Script in tools/ läuft
except Exception:
    try:
        from tools.alerts_engine import run_alerts as _run_alerts_func  # falls Paket-Import
    except Exception as e:
        sys.stderr.write(f"[warn] alerts_engine import failed: {e}\n")
        _run_alerts_func = None

def _engine_fallback(name: str) -> list:
    """Failsafe: wenn Engine nicht importierbar oder crasht, liefern wir leere Alerts."""
    return [{
        "portfolio": name,
        "note": "engine_fallback_noop",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "alerts": []
    }]

def _run_engine(name: str) -> list:
    """Versucht, run_alerts(name[, cfg]) aufzurufen, sonst Fallback."""
    if _run_alerts_func is None:
        return _engine_fallback(name)
    # 1) übliche Signatur: run_alerts("mars")
    try:
        return _run_alerts_func(name)
    except TypeError:
        # 2) alternative Signatur: run_alerts("mars", cfg_dict) – wir geben None, Engine liest selbst
        try:
            return _run_alerts_func(name, None)
        except Exception as e:
            sys.stderr.write(f"[warn] alerts_engine runtime failed ({name}): {e}\n")
            return _engine_fallback(name)
    except Exception as e:
        sys.stderr.write(f"[warn] alerts_engine runtime failed ({name}): {e}\n")
        return _engine_fallback(name)

# ------------------------------------------------------------
# Pfade
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "alerts_out.json"

def main() -> None:
    # Engine für mars/venus/family ausführen
    res_mars   = _run_engine("mars")
    res_venus  = _run_engine("venus")
    res_family = _run_engine("family")

    # Meta + Ergebnis strukturieren
    ts_cet = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    result = {
        "meta": {
            "timestamp_cet": ts_cet,
            "source": "tools/run_alerts.py"
        },
        "mars":   {"alerts": res_mars},
        "venus":  {"alerts": res_venus},
        "family": {"alerts": res_family}
    }

    # Preview in der Konsole (lesbar)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Datei zuverlässig schreiben
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not OUT_PATH.exists():
            OUT_PATH.write_text("{}", encoding="utf-8")
        with OUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        sys.stderr.write(f"[ok] alerts written to {OUT_PATH}\n")
    except Exception as e:
        sys.stderr.write(f"[error] cannot write {OUT_PATH}: {e}\n")
        sys.exit(2)

if __name__ == "__main__":
    main()
