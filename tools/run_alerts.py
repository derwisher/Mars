#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/run_alerts.py
- lädt alerts_engine robust (lokal & CI)
- schreibt docs/alerts.json + data/alerts_out.json
- druckt JSON auf STDOUT
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# --------------------------------------------------------------------
# Robust laden: zuerst Paket-Import, dann Fallback via PYTHONPATH
# --------------------------------------------------------------------
ae = None
try:
    # klappt, wenn 'tools' als Paket erkannt wird
    from tools import alerts_engine as ae  # type: ignore
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "tools"))
    import alerts_engine as ae  # type: ignore

# defensive: sicherstellen, dass run_alerts vorhanden ist
if not hasattr(ae, "run_alerts"):
    raise RuntimeError(f"alerts_engine geladen aus {getattr(ae, '__file__', '?')}, "
                       f"aber ohne run_alerts(). Bitte Datei prüfen.")

run_alerts = ae.run_alerts  # Alias


def load_config(cfg_path: Path) -> dict:
    if not cfg_path.exists():
        raise FileNotFoundError(f"Konfiguration nicht gefunden: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ROOT = Path(__file__).resolve().parents[1]  # /…/Mars
    data_dir = ROOT / "data"
    docs_dir = ROOT / "docs"

    cfg_path = data_dir / "alerts_config.json"
    out_data = data_dir / "alerts_out.json"
    out_docs = docs_dir / "alerts.json"

    cfg = load_config(cfg_path)

    # Konfig-Bäume (klein geschrieben)
    cfg_mars   = cfg.get("mars",   {})
    cfg_venus  = cfg.get("venus",  {})
    cfg_family = cfg.get("family", {})

    result = {
        "as_of_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mars":   {"alerts": run_alerts("mars",   cfg_mars)},
        "venus":  {"alerts": run_alerts("venus",  cfg_venus)},
        "family": {"alerts": run_alerts("family", cfg_family)},
    }

    docs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    with out_docs.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with out_data.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
