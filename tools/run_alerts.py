#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/run_alerts.py
- keine Klarnamen: 'mars' (TR/LS), 'venus' (ING/Xetra), 'family'
- robust: Pfade mit pathlib, schreibt nach data/alerts_out.json
- lädt config aus data/alerts_config.json
- ruft Engine (alerts_engine.run_alerts) je Bereich auf
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CFG_PATH = DATA_DIR / "alerts_config.json"
OUT_PATH = DATA_DIR / "alerts_out.json"

# Engine-Import robust halten
_run_alerts = None
try:
    from alerts_engine import run_alerts as _run_alerts  # wenn Script direkt in tools/ importierbar
except Exception:
    try:
        from tools.alerts_engine import run_alerts as _run_alerts  # falls Paketpfad notwendig
    except Exception as e:
        sys.stderr.write(f"[warn] alerts_engine import failed: {e}\n")
        _run_alerts = None


def _fallback(name: str) -> list:
    """Failsafe-Payload, falls Engine fehlt/fehlschlägt."""
    return [{
        "portfolio": name,
        "note": "engine_fallback_noop",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "alerts": []
    }]


def _call_engine(name: str, cfg: dict) -> list:
    """Engine sicher aufrufen (verschiedene Signaturen tolerieren)."""
    if _run_alerts is None:
        return _fallback(name)
    try:
        # bevorzugt: run_alerts(name, cfg)
        return _run_alerts(name, cfg)
    except TypeError:
        # alternative: run_alerts(name)
        try:
            return _run_alerts(name)
        except Exception as e:
            sys.stderr.write(f"[warn] engine runtime failed ({name}): {e}\n")
            return _fallback(name)
    except Exception as e:
        sys.stderr.write(f"[warn] engine runtime failed ({name}): {e}\n")
        return _fallback(name)


def main() -> None:
    # Config laden
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        sys.stderr.write(f"[error] cannot read config {CFG_PATH}: {e}\n")
        cfg = {}

    # Engine je Bereich
    res_mars   = _call_engine("mars", cfg.get("mars", {}))
    res_venus  = _call_engine("venus", cfg.get("venus", {}))
    res_family = _call_engine("family", cfg.get("family", {}))

    # Meta + Ergebnis
    ts_cet = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    result = {
        "meta": {
            "timestamp_cet": ts_cet,
            "source": "tools/run_alerts.py",
            "config_loaded": CFG_PATH.name
        },
        "mars":   {"alerts": res_mars},
        "venus":  {"alerts": res_venus},
        "family": {"alerts": res_family}
    }

    # Preview im Terminal
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Output-Datei zuverlässig schreiben
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with OUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        sys.stderr.write(f"[ok] alerts written to {OUT_PATH}\n")
    except Exception as e:
        sys.stderr.write(f"[error] cannot write {OUT_PATH}: {e}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
