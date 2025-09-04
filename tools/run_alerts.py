import json
from alerts_engine import run_alerts

def main():
    out = {
        "portfolio_a": {"alerts": run_alerts("portfolio_a")},
        "portfolio_b": {"alerts": run_alerts("portfolio_b")},
        "family":      {"alerts": run_alerts("family")}
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
out_path = ROOT / "data" / "alerts_out.json"
with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
