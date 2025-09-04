# tools/run_alerts.py
import json
from pathlib import Path
from alerts_engine import run_alerts

def main():
    # Engine aufrufen – liefert Alerts je Depot + Family
    result = {
        "Mars":   {"alerts": run_alerts("Mars")},    # Portfolio A (TR/LS)
        "Venus":  {"alerts": run_alerts("Venus")},   # Portfolio B (ING/Xetra)
        "family": {"alerts": run_alerts("family")}   # Family-Level
    }

    # Sauberer Output im Terminal
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Sicher und portabel abspeichern
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "alerts_out.json"
    tmp_path = out_dir / "alerts_out.json.tmp"

    if not out_path.exists():
        out_path.write_text("{}", encoding="utf-8")

    tmp_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(out_path)

if __name__ == "__main__":
    main()
