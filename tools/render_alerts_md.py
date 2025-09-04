# tools/render_alerts_md.py
# Erzeugt docs/alerts_brief.md aus data/alerts_out.json (Markdown-Kurzbriefing)

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
INP  = ROOT / "data" / "alerts_out.json"
OUT  = ROOT / "docs" / "alerts_brief.md"

def _safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _md_esc(s: str) -> str:
    return (s or "").replace("|", r"\|").replace("<", "&lt;").replace(">", "&gt;")

def _fmt_alert(a: dict) -> str:
    ts   = a.get("timestampCET") or a.get("ts") or ""
    top  = a.get("topic") or a.get("ticker") or a.get("symbol") or "?"
    act  = a.get("action") or a.get("recommended") or ""
    sc   = a.get("score")
    conf = a.get("confidence")
    varA = a.get("variantA") or a.get("A") or {}
    varB = a.get("variantB") or a.get("B") or {}
    # Varianten knappe Kurzform
    def _short(v: dict) -> str:
        if not isinstance(v, dict): return ""
        steps = v.get("steps") or v.get("plan") or ""
        if isinstance(steps, list): steps = "; ".join(steps)
        budget = v.get("cash") or v.get("budget")
        s = (steps or "").strip()
        if budget not in (None, ""):
            s = (s + f" [€{budget}]").strip()
        return s
    return (
        f"- **{_md_esc(ts)}** — **{_md_esc(top)}** — {_md_esc(act)}  \n"
        f"  Score **{sc if sc is not None else '?'}** | Confidence **{conf if conf is not None else '?'}**  \n"
        f"  A: {_md_esc(_short(varA))}  \n"
        f"  B: {_md_esc(_short(varB))}"
    )

def _section(title: str, alerts: list[dict]) -> str:
    if not alerts:
        return f"### {title}\n_(keine Alerts)_\n"
    lines = "\n".join(_fmt_alert(a) for a in alerts)
    return f"### {title}\n{lines}\n"

def main() -> None:
    data = _safe_load(INP)
    mars   = (data.get("Mars")   or {}).get("alerts") or (data.get("p_a") or {}).get("alerts") or []
    venus  = (data.get("Venus")  or {}).get("alerts") or (data.get("p_b") or {}).get("alerts") or []
    family = (data.get("family") or {}).get("alerts") or []

    now_cet = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    md = [
        f"# Alerts Brief – {now_cet}",
        "",
        _section("Mars (TR/LS)",   mars),
        _section("Venus (ING/Xetra)", venus),
        _section("Family-Level (Risiken/Cluster)", family),
        "---",
        "_Quelle: data/alerts_out.json_",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(md).strip() + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
