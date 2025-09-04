#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/render_portfolio_md.py
Erzeugt eine Markdown-Übersicht aus data/portfolios.json:
- Mars (Core/Growth, Satellites, Moonshots, NVDA-Status)
- Venus (Sparpläne, Add-on-Dips, Restpositionen, NVDA-Status)
- Notgroschen (ETF-Sparraten)
- Family (Risikogrenzen, Exposure, Cluster)
Schreibt nach: docs/portfolio_overview.md
"""

from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
PORTF = DATA / "portfolios.json"
OUT   = DOCS / "portfolio_overview.md"


def _load_json(p: Path) -> dict:
    if not p.exists():
        raise FileNotFoundError(f"Fehlt: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _ts_cet() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _fmt_list(items, bullet="- "):
    if not items:
        return "_keine_"
    return "\n".join(f"{bullet}`{x}`" for x in items)


def build_md(data: dict) -> str:
    mars  = data.get("mars", {})
    venus = data.get("venus", {})
    ng    = data.get("notgroschen", {})
    fam   = data.get("family", {})

    # Mars
    m_core   = mars.get("core_growth", [])
    m_nvda   = mars.get("nvda_position", {})
    m_sat    = mars.get("satellites", [])
    m_moon   = mars.get("moonshots", [])

    # Venus
    v_sp     = venus.get("sparplan", [])
    v_nvda   = venus.get("nvda_position", {})
    v_add    = venus.get("add_on_dips", [])
    v_rest   = venus.get("restpositions", [])
    v_ticks  = venus.get("tickers", [])

    # Notgroschen
    ng_sp    = (ng.get("sparplan") or {})
    ng_status = ng.get("status", "—")

    # Family
    fr = fam.get("risk_limits", {})
    fe = fam.get("exposure_limits", {})
    fc = fam.get("clusters", {})

    ts = _ts_cet()
    md = []

    md.append(f"# Portfolio-Übersicht – Stand {ts}\n")

    # Mars
    md.append("## Mars (TR/LS)")
    md.append("**Core/Growth**:")
    md.append(_fmt_list(m_core))
    md.append("\n**NVDA**:")
    if m_nvda:
        md.append(f"- Status: **{m_nvda.get('status','—')}**")
        md.append(f"- Sparplan: **{str(m_nvda.get('sparplan', False)).lower()}**")
    else:
        md.append("- _kein Eintrag_")
    md.append("\n**Satellites**:")
    md.append(_fmt_list(m_sat))
    md.append("\n**Moonshots**:")
    md.append(_fmt_list(m_moon))
    md.append("")

    # Venus
    md.append("## Venus (ING/Xetra)")
    md.append("**Sparpläne**:")
    md.append(_fmt_list(v_sp))
    md.append("\n**NVDA**:")
    if v_nvda:
        md.append(f"- Status: **{v_nvda.get('status','—')}**")
        md.append(f"- Sparplan: **{str(v_nvda.get('sparplan', False)).lower()}**")
        tr = v_nvda.get("tranches", [])
        if tr:
            md.append("- Trimm-/Tranche-Regeln:")
            md.extend([f"  - {rule}" for rule in tr])
    else:
        md.append("- _kein Eintrag_")
    md.append("\n**Add-on-Dips (geplant, no chase)**:")
    md.append(_fmt_list(v_add))
    md.append("\n**Restpositionen (no DCA, hard-break only)**:")
    md.append(_fmt_list(v_rest))
    if v_ticks:
        md.append("\n**Alle Venus-Ticker (Soll/Ist):**")
        md.append(_fmt_list(sorted(set(v_ticks)), bullet="  - "))
    md.append("")

    # Notgroschen
    md.append("## Notgroschen (separat)")
    if ng_sp:
        md.append("**ETF-Sparraten (€/Monat):**")
        for k, v in ng_sp.items():
            md.append(f"- {k}: **{v} €**")
    else:
        md.append("- _keine Sparraten hinterlegt_")
    md.append(f"\n_Status_: {ng_status}\n")

    # Family
    md.append("## Family (Risiko / Exposure / Cluster)")
    if fr:
        md.append("**Drawdown-Grenzen:**")
        md.append(f"- Family DD ≤ **{fr.get('dd_family', '—')}**")
        md.append(f"- Sub-Depot DD ≤ **{fr.get('dd_sub', '—')}**")
    if fe:
        md.append("\n**Exposure:**")
        md.append(f"- Max invested: **{int(fe.get('max_invested', 0)*100)}%**")
        md.append(f"- Min Cash: **{int(fe.get('min_cash', 0)*100)}%**")
    if fc:
        md.append("\n**Cluster:**")
        md.append(f"- NVDA-Family Max: **{int(fc.get('nvda_family_max',0)*100)}%**")
        md.append(f"- Prefer Trim: **{fc.get('prefer_trim','—')}**")
    md.append("")

    return "\n".join(md).strip() + "\n"


def main():
    port = _load_json(PORTF)
    DOCS.mkdir(parents=True, exist_ok=True)
    md = build_md(port)
    OUT.write_text(md, encoding="utf-8")
    print(f"[OK] wrote {OUT}")


if __name__ == "__main__":
    main()
