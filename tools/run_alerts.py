import json
from alerts_engine import run_alerts
from pathlib import Path

def main():
    out = {
        "portfolio_a": {"alerts": run_alerts("portfolio_a")},
        "portfolio_b": {"alerts": run_alerts("portfolio_b")},
        "family":     {"alerts": run_alerts("family")}
    }

    # Sauberer JSON-Output ins Terminal
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # Immer korrektes data/-Verzeichnis finden
    ROOT = Path(__file__).resolve().parents[1]
    out_path = ROOT / "data" / "alerts_out.json"

    # Datei schreiben
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
