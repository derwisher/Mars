# tools/alerts_engine.py
from __future__ import annotations
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# --------- kleine Hilfen ---------
def now_cet_str() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

def load_json(p: Path, default: Any) -> Any:
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default

def load_csv_map(p: Path, key: str) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    if not p.exists():
        return out
    with p.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            out[row[key].strip().upper()] = {k: v for k, v in row.items()}
    return out

def to_float(v: Optional[str], default: float = 0.0) -> float:
    try:
        return float(str(v).replace("%","").replace(",",".")) if v is not None else default
    except:
        return default

# --------- Datenquellen ---------
def load_fx_snapshot() -> Dict[str, Dict[str, str]]:
    # pair,rate,source
    return load_csv_map(DATA / "fx_snapshot.csv", "pair")

def load_prices_eur() -> Dict[str, Dict[str, str]]:
    # ticker,price_eur,chg_intraday_pct,chg_5d_pct,vol_x,low5_eur,dma50_eur,pivot_eur,entry_eur
    return load_csv_map(DATA / "prices_eur_snapshot.csv", "ticker")

# --------- Scoring & QA ---------
@dataclass
class QaContext:
    fx_ok: bool
    vol_ok: bool
    debounce_ok: bool
    min_move_ok: bool

def score_from_flags(flags: QaContext, severity: float) -> int:
    base = int(60 + 40*max(0.0, min(1.0, severity)))
    if not flags.fx_ok:        base -= 25
    if not flags.vol_ok:       base -= 15
    if not flags.debounce_ok:  base -= 10
    if not flags.min_move_ok:  base -= 10
    return max(0, min(100, base))

def confidence_from_flags(flags: QaContext) -> int:
    c = 1
    if flags.fx_ok:       c += 1
    if flags.vol_ok:      c += 1
    if flags.debounce_ok: c += 1
    if flags.min_move_ok: c += 1
    return max(1, min(5, c))

# --------- Core Engine ---------
def run_alerts(scope: str) -> List[str]:
    """
    scope: "p_a" (TR/LS), "p_b" (ING/Xetra), "family"
    returns: list of formatted alert strings
    """
    cfg = load_json(DATA / "alerts_config.json", default={})
    meta = cfg.get("meta", {})
    fx_tol = float(meta.get("fx_check", {}).get("tolerance", 0.002))  # ≤0.2%
    vol_min = float(meta.get("volume_min_x", 1.3))
    vol_spike = float(meta.get("volume_spike_x", 1.5))
    debounce_s = int(meta.get("debounce_seconds", 120))
    min_move = float(meta.get("min_move_eur_low_price", 0.40))

    fx_map = load_fx_snapshot()
    prices = load_prices_eur()

    alerts: List[str] = []

    # ---- Hilfsfunktionen für Trigger ----
    def fx_gate_ok() -> bool:
        # Wenn keine Daten: im Demo-Mode als OK behandeln
        if not fx_map:
            return True
        # Beispiel-Mehrheitsentscheidung: wenn alle existierenden Feeds ~konsistent sind
        rates = []
        for row in fx_map.values():
            r = to_float(row.get("rate"), 0.0)
            if r > 0: rates.append(r)
        if len(rates) < 2:
            return True
        mean = sum(rates)/len(rates)
        devs = [abs(r-mean)/mean for r in rates]
        return max(devs) <= fx_tol

    def check_vol_ok(tkr: str, need_spike: bool) -> bool:
        volx = to_float(prices.get(tkr, {}).get("vol_x"), 1.0)
        return volx >= (vol_spike if need_spike else vol_min)

    def check_min_move_ok(tkr: str) -> bool:
        p = to_float(prices.get(tkr, {}).get("price_eur"), 0.0)
        chg = to_float(prices.get(tkr, {}).get("chg_intraday_pct"), 0.0)
        move = abs(p * chg)
        return move >= min_move

    def format_alert(tkr: str, what: str, action: str, severity: float, need_spike=False) -> str:
        flags = QaContext(
            fx_ok = fx_gate_ok(),
            vol_ok = check_vol_ok(tkr, need_spike),
            debounce_ok = True,          # echtes Debounce würdest du mit State/Redis etc. halten
            min_move_ok = check_min_move_ok(tkr)
        )
        sc = score_from_flags(flags, severity)
        conf = confidence_from_flags(flags)
        # Varianten kurz
        var_a = f"A: konservativ – {action} (gestaffelt/Stops enger)."
        var_b = f"B: aggressiv – {action} (größerer Anteil, Stops weiter)."
        ts = now_cet_str()
        # Output-Format wie vorgegeben
        txt = (
            f"🚨 Execution Alert – {ts} CET 🚨\n"
            f"📌 Betreff: {tkr}\n"
            f"📝 Inhalt: {what}\n"
            f"➕ Zusatz: {action}\n"
            f"Score: {sc} | Confidence: {conf} | Variante A/B: {var_a} / {var_b}"
        )
        return txt

    # ---------- Portfolio A (TR/LS) ----------
    if scope == "p_a":
        oa = cfg.get("Mars", {})
        # Core/Growth
        cg = oa.get("core_growth", {})
        for tkr in cg.get("tickers", []):
            p = prices.get(tkr, {})
            if not p:  # keine Daten -> überspringen
                continue
            chg5d = to_float(p.get("chg_5d_pct"), 0.0)
            chgintra = to_float(p.get("chg_intraday_pct"), 0.0)

            # Trim falls ≤ -12% vs 5d
            if chg5d <= cg.get("trim_drop_5d", -0.12):
                alerts.append(format_alert(
                    tkr,
                    what=f"5-Tage-Verlust {chg5d:.2%} (EUR).",
                    action="Trim 10–20% erwägen.",
                    severity=min(1.0, abs(chg5d)/0.2),
                    need_spike=False
                ))
                continue

            # Take-Profit bei ≥ +12% intraday
            if chgintra >= cg.get("tp_gain_intraday", 0.12):
                alerts.append(format_alert(
                    tkr,
                    what=f"Intraday +{chgintra:.2%} (EUR).",
                    action="TP/Stop anheben.",
                    severity=min(1.0, chgintra/0.2),
                    need_spike=False
                ))

        # NVDA fail-safe
        nv = oa.get("nvda", {})
        tkr = "NVDA"
        p = prices.get(tkr, {})
        if p:
            chgintra = to_float(p.get("chg_intraday_pct"), 0.0)
            low5 = to_float(p.get("low5_eur"), 0.0)
            price = to_float(p.get("price_eur"), 0.0)
            trig = False
            why = []
            if chgintra <= -0.12:
                trig = True; why.append("intraday ≤ −12%")
            if low5 > 0 and price < low5:
                trig = True; why.append("close < LOW5")
            if trig:
                alerts.append(format_alert(
                    tkr,
                    what="NVDA Fail-Safe aktiviert: " + ", ".join(why),
                    action="Keine Adds; Risiko reduzieren/Stops prüfen.",
                    severity=0.9,
                    need_spike=True
                ))

        # Satellites (Schneider/Vertiv/CRWD)
        sat = oa.get("satellites", {})
        # CRWD add if −10% vs entry
        tkr = "CRWD"
        p = prices.get(tkr, {})
        if p and sat.get("CRWD"):
            entry = to_float(p.get("entry_eur"), 0.0)
            price = to_float(p.get("price_eur"), 0.0)
            if entry > 0 and (price - entry)/entry <= -0.10:
                alerts.append(format_alert(
                    tkr,
                    what=f"Preis −{(entry-price)/entry:.2%} vs Entry.",
                    action="Add-Tranche (≤⅓ Ziel) erlaubt.",
                    severity=0.6
                ))

        # Schneider (hier Kürzel SU)
        tkr = "SU"
        p = prices.get(tkr, {})
        if p and sat.get("SU"):
            price = to_float(p.get("price_eur"), 0.0)
            if price < float(sat["SU"]["add_below_eur"]):
                alerts.append(format_alert(
                    tkr,
                    what=f"Unter Add-Level ({price:.2f} €).",
                    action="Add-Tranche; Stop-Orientierung <200€ Close.",
                    severity=0.5
                ))

        # Vertiv
        tkr = "VRT"
        p = prices.get(tkr, {})
        if p and sat.get("VRT"):
            price = to_float(p.get("price_eur"), 0.0)
            if price < float(sat["VRT"]["add_below_eur"]):
                alerts.append(format_alert(
                    tkr,
                    what=f"Unter Add-Level ({price:.2f} €).",
                    action="Add-Tranche; Stop-Orientierung <95€ Close.",
                    severity=0.5
                ))

        # Moonshots warn
        ms = oa.get("moonshots", {})
        for tkr in ms.get("tickers", []):
            p = prices.get(tkr, {})
            if not p: continue
            chgintra = to_float(p.get("chg_intraday_pct"), 0.0)
            chg5d = to_float(p.get("chg_5d_pct"), 0.0)
            if (chgintra <= ms["rules"].get("warn_intraday", -0.15) and check_vol_ok(tkr=True)) or \
               (chg5d <= ms["rules"].get("warn_vs5d", -0.25)):
                alerts.append(format_alert(
                    tkr,
                    what=f"Moonshot-Druck (intraday {chgintra:.2%}, 5d {chg5d:.2%}).",
                    action="Warnung: nur halten, keine neuen Adds.",
                    severity=min(1.0, max(abs(chgintra), abs(chg5d))/0.25),
                    need_spike=True
                ))

        return alerts

    # ---------- Portfolio B (ING/Xetra) ----------
    if scope == "p_b":
        gb = cfg.get("Venus", {})

        # NVDA Tranches
        nv = gb.get("nvda_tranches", {})
        tkr = "NVDA"
        p = prices.get(tkr, {})
        if p:
            price = to_float(p.get("price_eur"))
            low5  = to_float(p.get("low5_eur"))
            dma50 = to_float(p.get("dma50_eur"))
            chgintra = to_float(p.get("chg_intraday_pct"))
            messages = []
            if (low5 > 0 and price < low5) or (chgintra <= -0.06 and check_vol_ok(tkr, True)):
                messages.append("T1 25% möglich (close<LOW5 oder intraday≤−6% vol↑)")
            if (dma50 > 0 and price < dma50) or (to_float(p.get("pivot_eur"))>0 and price < to_float(p.get("pivot_eur")) and check_vol_ok(tkr, False)):
                messages.append("T2 10–15% möglich (close<DMA50 oder Pivot-Break vol↑)")
            if messages:
                alerts.append(format_alert(
                    tkr,
                    what="; ".join(messages),
                    action="Tranche gemäß Plan setzen; nicht jagen.",
                    severity=0.7,
                    need_spike=True
                ))

        # Adds auf Dips (ASML/LLY/NVO/PEP/VOO/BEP)
        dips = gb.get("add_on_dips", {})
        dip_low, dip_high = -0.05, -0.03
        if dips:
            for tkr in dips.get("tickers", []):
                p = prices.get(tkr, {})
                if not p: continue
                chgintra = to_float(p.get("chg_intraday_pct"))
                if dip_low <= chgintra <= dip_high:
                    alerts.append(format_alert(
                        tkr,
                        what=f"Dip {chgintra:.2%} im Zielkorridor.",
                        action="Add-Tranche zulässig (keine Verfolgung).",
                        severity=min(1.0, abs(chgintra)/0.06)
                    ))

        # Restpositionen – harte Brüche melden
        rest = gb.get("restpositions", {})
        for tkr in rest.get("tickers", []):
            p = prices.get(tkr, {})
            if not p: continue
            chg5d = to_float(p.get("chg_5d_pct"))
            if chg5d <= -0.20:  # „hard break“ proxy
                alerts.append(format_alert(
                    tkr,
                    what=f"Harter 5d-Break {chg5d:.2%}.",
                    action="Nur Risiko prüfen; kein DCA.",
                    severity=min(1.0, abs(chg5d)/0.3),
                    need_spike=False
                ))

        return alerts

    # ---------- Family-Level ----------
    if scope == "family":
        fam = cfg.get("family", {})
        # Hier setzen wir Platzhalter; real: Family-P&L, Sub-P&L, Invested-Quote, NVDA-Cluster, Corr
        # Du kannst sie später aus deinem Report-JSON befüllen.
        pnl_family = -0.028   # Demo
        pnl_sub = -0.036      # Demo
        invested_ratio = 0.96 # Demo
        ndx_corr = 0.92       # Demo
        nvda_weight = 0.21    # Demo

        if pnl_family <= fam.get("risk", {}).get("pnl_family_dd", -0.025) or \
           pnl_sub    <= fam.get("risk", {}).get("pnl_sub_dd", -0.035):
            alerts.append(format_alert(
                "FAMILY",
                what=f"Drawdown Family {pnl_family:.2%} / Sub {pnl_sub:.2%}.",
                action="Keine neuen Käufe; Cash prüfen; Stops disziplinieren.",
                severity=0.8
            ))

        if invested_ratio > fam.get("exposure", {}).get("max_invested", 0.95):
            alerts.append(format_alert(
                "FAMILY",
                what=f"Invested {invested_ratio:.1%} > 95% bei schwachem Markt.",
                action="De-Risk Vorschlag: 5–10% trims/hedges.",
                severity=0.6
            ))

        if nvda_weight > fam.get("cluster", {}).get("nvda_family_max", 0.20):
            alerts.append(format_alert(
                "NVDA_CLUSTER",
                what=f"NVDA Cluster {nvda_weight:.0%} Family.",
                action="Trim bevorzugt in p_b; keine Adds in p_a.",
                severity=0.7
            ))

        if ndx_corr > fam.get("correlation", {}).get("ndx_threshold", 0.90):
            alerts.append(format_alert(
                "CORR",
                what=f"Family–NDX Korr {ndx_corr:.2f} > 0.90.",
                action="Diversifikation (Infra/Cash/Staples) erwägen.",
                severity=0.4
            ))

        return alerts

    # Fallback
    return []
