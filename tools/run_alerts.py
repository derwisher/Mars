# tools/run_alerts.py
# Robust: arbeitet relativ zur Datei (Path), schreibt atomar nach data/alerts_out.json
# Keys sind bewusst "Mars" und "Venus", plus "family".

import json
from pathlib import Path
from alerts_engine import run_alerts


def main() -> None:
    # 1) Alerts je Depot + Family über die Engine holen
    result = {
        "Mars":   {"alerts": run_alerts("Mars")},    # Portfolio A (TR/LS)
        "Venus":  {"alerts": run_alerts("Venus")},   # Portfolio B (ING/Xetra)
        "family": {"alerts": run_alerts("family")}   # Family-Level Guards
    }

    # 2) Sauber im Terminal ausgeben (zum schnellen Prüfen)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 3) Sicher & portabel speichern: <repo-root>/data/alerts_out.json
    root = Path(__file__).resolve().parents[1]          # .../Mars
    out_dir = root / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "alerts_out.json"
    tmp_path = out_dir / "alerts_out.json.tmp"           # atomar schreiben

    # Falls Datei noch nie existierte, eine leere Grundstruktur erzeugen
    if not out_path.exists():
        out_path.write_text("{}", encoding="utf-8")

    # Atomar schreiben (erst tmp, dann ersetzen) – vermeidet halb geschriebene Dateien
    tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(out_path)


if __name__ == "__main__":
    main()
