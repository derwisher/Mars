#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/run_alerts.py
Erzeugt die Alert-Ausgabe für mars / venus / family auf Basis von data/alerts_config.json

- nutzt die Engine in tools/alerts_engine.py
- schreibt nach docs/alerts.json (für Report/Brief)
- spiegelt zusätzlich nach data/alerts_out.json (Debug/Archiv)
- gibt das JSON auch auf STDOUT aus (für Logs)
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# --------------------------------------------------------------------
# Robust: 'alerts_engine' unabhängig von Arbeitsverzeichnis laden
#   - lokal:   import tools.alerts_engine
#   - CI:      ergänzt PYTHONPATH mit <repo>/tools und importiert alerts_engine
# --------------------------------------------------------------------
try:
    # klappt lokal, wenn das Paket 'tools' als Paket verfügbar ist
    from tools.alerts_engine import run_alerts  # type: ignore
except ModuleNotFoundError:
    ROOT = Path(__file__).resolve().parents[1]  # /…/Mars
    sys.path.insert(0, str(ROOT / "tools"))
    from alerts_engine import run_alerts  # type: ignore


def load_config(cfg_path: Path) -> dict:
    if not cfg_path.exists():
        raise FileNotFoundError(f"Konfiguration nicht gefunden: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    # Projekt-Root: /…/Mars
    ROOT = Path(__file__).resolve().parents[1]
    data_dir = ROOT / "data"
    docs_dir = ROOT / "docs"

    cfg_path = data_dir / "alerts_config.json"
    out_data = data_dir / "alerts_out.json"   # Spiegel/Archiv
    out_docs = docs_dir / "alerts.json"       # vom Workflow konsumiert

    cfg = load_config(cfg_path)

    # Konfig-Bäume (klein geschrieben, wie besprochen)
    cfg_mars   = cfg.get("mars",   {})
    cfg_venus  = cfg.get("venus",  {})
    cfg_family = cfg.get("family", {})

    # Engine laufen lassen
    result = {
        "as_of_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mars":   {"alerts": run_alerts("mars",   cfg_mars)},
        "venus":  {"alerts": run_alerts("venus",  cfg_venus)},
        "family": {"alerts": run_alerts("family", cfg_family)},
    }

    # Ausgabe-Verzeichnisse sicherstellen
    docs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1) in docs/alerts.json (für Report/Brief)
    with out_docs.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 2) zusätzlich nach data/alerts_out.json (Debug/Archiv)
    with out_data.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 3) auch auf STDOUT für Logs
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
