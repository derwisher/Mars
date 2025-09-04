# tools/run_alerts.py
import json
from pathlib import Path
from alerts_engine import run_alerts

def main():
    # Engine aufrufen – liefert Alerts je Depot + Family
    result = {
        "p_a": {"alerts": run_alerts("p_a")},       # Portfolio A (TR/LS)
        "p_b": {"alerts": run_alerts("p_b")},       # Portfolio B (ING/Xetra)
        "family": {"alerts": run_alerts("family")}  # Family-Level
    }

    # Sauberer Output im Terminal
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Sicher und portabel abspeichern
    ROOT = Path(__file__).resolve().parents[1]
    out_path = ROOT / "data" / "alerts_out.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not out_path.exists():
        out_path.write_text("{}", encoding="utf-8")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
