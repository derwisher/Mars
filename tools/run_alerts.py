# tools/run_alerts.py
import json
from pathlib import Path
from alerts_engine import run_alerts

def main():
    # Engine je Depot + Family aufrufen
    result = {
        "Mars":   {"alerts": run_alerts("Mars")},
        "Venus":  {"alerts": run_alerts("Venus")},
        "family": {"alerts": run_alerts("family")},
    }

    # Sauberer Output in der Action-Log
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Sicher & portabel abspeichern
    root    = Path(__file__).resolve().parents[1]   # Repo-Root
    out_dir = root / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "alerts_out.json"
    tmp_path = out_dir / "alerts_out.json.tmp"

    # atomar schreiben
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    tmp_path.replace(out_path)

if __name__ == "__main__":
    main()
