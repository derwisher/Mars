#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tools/alerts_engine.py
Regel-Engine für Alerts:
- liest Kontexte/Parameter aus run_alerts(name, cfg)
- nutzt optionale Snapshots (EUR/Preis, USD-Ref, Volumen) aus data/*.csv
- dual-layer Logik: USD reference, EUR action
- QA-Gates: FX-Toleranz, Debounce, Volume, Min-Move
- Score (0..100), Confidence (1..5), Varianten A/B Text
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import time
import csv

# ------------------------------------------------------------
# Pfade für optionale Snapshots
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PRICES_EUR_SNAP = DATA_DIR / "prices_eur_snapshot.csv"   # Spalten: ticker, last_eur, change_intraday_pct, vs5d_pct, vol_x
FX_SNAP          = DATA_DIR / "fx_snapshot.csv"          # Spalten: pair, rate  (z.B. EURUSD, USDEUR)

# In-Memory Debounce-Store (laufzeitlokal)
_DEBOUNCE = {}  # key: (portfolio, ticker, rule_key) -> last_ts


# ------------------------------------------------------------
# Hilfsfunktionen: Snapshots, FX, Debounce, QA, Scoring
# ------------------------------------------------------------

def _now_ts() -> float:
    return time.time()

def _debounced(key: tuple, debounce_s: int) -> bool:
    last = _DEBOUNCE.get(key, 0.0)
    if _now_ts() - last < debounce_s:
        return True
    _DEBOUNCE[key] = _now_ts()
    return False

def _load_prices_eur() -> dict:
    out = {}
    if not PRICES_EUR_SNAP.exists():
        return out
    with PRICES_EUR_SNAP.open("r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            try:
                t = r["ticker"].strip().upper()
                out[t] = {
                    "last_eur": float(r.get("last_eur", "0") or 0),
                    "chg_intraday": float(r.get("change_intraday_pct", "0") or 0),
                    "vs5d": float(r.get("vs5d_pct", "0") or 0),
                    "vol_x": float(r.get("vol_x", "0") or 0)
                }
            except Exception:
                continue
    return out

def _load_fx() -> dict:
    fx = {}
    if not FX_SNAP.exists():
        # sanfter Fallback
        fx["USDEUR"] = 1.0
        fx["EURUSD"] = 1.0
        return fx
    with FX_SNAP.open("r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            try:
                pair = r["pair"].strip().upper()
                rate = float(r["rate"])
                fx[pair] = rate
            except Exception:
                continue
    if "USDEUR" not in fx and "EURUSD" in fx and fx["EURUSD"] != 0:
        fx["USDEUR"] = 1.0 / fx["EURUSD"]
    if "EURUSD" not in fx and "USDEUR" in fx and fx["USDEUR"] != 0:
        fx["EURUSD"] = 1.0 / fx["USDEUR"]
    return fx

def _qa_fx_ok(fx: dict, tol: float) -> bool:
    # einfache Toleranzprüfung; bei fehlenden Daten OK
    if "EURUSD" in fx and "USDEUR" in fx and fx["USDEUR"] != 0:
        back = 1.0 / fx["USDEUR"]
        if abs(back - fx["EURUSD"]) / max(1e-6, fx["EURUSD"]) <= tol:
            return True
        return False
    return True  # wenn wir keine Daten haben, blockieren wir nicht hart


def _score_confidence(passed: dict) -> tuple[int, int]:
    """Wandelt QA-Gates in Score/Confidence (heuristisch)."""
    base = 60
    if passed.get("fx"): base += 10
    if passed.get("volume"): base += 10
    if passed.get("debounce"): base -= 10  # debounce aktiv -> Score runter
    if passed.get("min_move"): base += 5
    # clamp
    sc = max(0, min(100, base))
    # Confidence 1..5
    conf = 1
    if sc >= 50: conf = 2
    if sc >= 65: conf = 3
    if sc >= 75: conf = 4
    if sc >= 85: conf = 5
    return sc, conf


def _variant_text(kind: str) -> tuple[str, str]:
    """Variante A/B Kurztext."""
    if kind == "tp":   # take profit
        return ("A: ½-Teilverkauf, Stop anheben", "B: ⅓-Teilverkauf jetzt, Rest bei weiterer Stärke")
    if kind == "trim": # de-risk
        return ("A: 10–15% trim, Stops enger", "B: 15–20% trim, Hedge erwägen")
    if kind == "add":  # add-on dip
        return ("A: Starter ⅓, stop-orientiert", "B: ½ jetzt, ½ tiefer – strikte Stops")
    return ("A: konservativ", "B: offensiver")


# ------------------------------------------------------------
# Kern: Regelauswertung pro Portfolio
# ------------------------------------------------------------

def _run_for_mars(cfg: dict) -> list:
    out = []
    px = _load_prices_eur()
    fx = _load_fx()

    meta = cfg.get("meta", {})
    tol = meta.get("fx_check", {}).get("tolerance", 0.002)
    debounce_s = meta.get("debounce_seconds", 120)
    vol_min_x = meta.get("volume_min_x", 1.3)
    vol_spike_x = meta.get("volume_spike_x", 1.5)
    min_move_eur = meta.get("min_move_eur_low_price", 0.40)

    # Core/Growth
    cg = cfg.get("core_growth", {})
    tickers = [t.upper() for t in cg.get("tickers", [])]
    drop5d = cg.get("trim_drop_5d", -0.12)
    tp_intraday = cg.get("tp_gain_intraday", 0.12)

    for t in tickers:
        d = px.get(t)
        if not d:
            continue
        passed = {"fx": _qa_fx_ok(fx, tol)}

        # Take profit / trim
        if d["chg_intraday"] >= tp_intraday and d["vol_x"] >= vol_min_x:
            key = ("mars", t, "tp")
            passed["debounce"] = _debounced(key, debounce_s)
            passed["volume"] = d["vol_x"] >= vol_min_x
            passed["min_move"] = (d["last_eur"] * tp_intraday) >= min_move_eur
            score, conf = _score_confidence(passed)
            if not passed["debounce"]:
                a, b = _variant_text("tp")
                out.append({
                    "ticker": t,
                    "type": "tp",
                    "p_eur": d["last_eur"],
                    "what": "Take-Profit Kandidat (intraday +12%)",
                    "score": score, "confidence": conf,
                    "variant_A": a, "variant_B": b
                })

        if d["vs5d"] <= drop5d and d["vol_x"] >= vol_spike_x:
            key = ("mars", t, "trim")
            passed["debounce"] = _debounced(key, debounce_s)
            passed["volume"] = d["vol_x"] >= vol_spike_x
            passed["min_move"] = True
            score, conf = _score_confidence(passed)
            if not passed["debounce"]:
                a, b = _variant_text("trim")
                out.append({
                    "ticker": t,
                    "type": "trim",
                    "p_eur": d["last_eur"],
                    "what": "Schutz-Trim (≤−12% vs 5d)",
                    "score": score, "confidence": conf,
                    "variant_A": a, "variant_B": b
                })

    # NVDA fail-safe
    nv = cfg.get("nvda", {}).get("triggers", {})
    if "NVDA" in px:
        d = px["NVDA"]
        if d["chg_intraday"] <= nv.get("intraday", -0.12):
            key = ("mars", "NVDA", "fail")
            if not _debounced(key, debounce_s):
                a, b = _variant_text("trim")
                s, c = _score_confidence({"fx": _qa_fx_ok(fx, tol), "debounce": False, "volume": True, "min_move": True})
                out.append({
                    "ticker": "NVDA",
                    "type": "fail_safe",
                    "p_eur": d["last_eur"],
                    "what": "NVDA Fail-Safe (intraday ≤ −12%)",
                    "score": s, "confidence": c,
                    "variant_A": a, "variant_B": b
                })

    # Satellites: CRWD add vs entry / SU, VRT add unter Schwelle
    sat = cfg.get("satellites", {})
    if "CRWD" in sat and "CRWD" in px:
        d = px["CRWD"]
        thr = sat["CRWD"].get("add_vs_entry_pct", -0.10)
        # ohne echte Entry-Daten interpretieren wir vs5d als Proxy für "unter Einstand"
        if d["vs5d"] <= thr:
            key = ("mars", "CRWD", "add")
            if not _debounced(key, debounce_s):
                a, b = _variant_text("add")
                s, c = _score_confidence({"fx": _qa_fx_ok(fx, tol), "debounce": False, "volume": True, "min_move": True})
                out.append({
                    "ticker": "CRWD",
                    "type": "add",
                    "p_eur": d["last_eur"],
                    "what": "Add-on Dip (unter Einstand/Proxy)",
                    "score": s, "confidence": c,
                    "variant_A": a, "variant_B": b
                })

    for lbl, ticker in (("SU", "SU"), ("VRT", "VRT")):
        if lbl in sat and ticker in px:
            d = px[ticker]
            thr = sat[lbl].get("add_below_eur", None)
            if thr is not None and d["last_eur"] <= float(thr):
                key = ("mars", ticker, "add_thr")
                if not _debounced(key, debounce_s):
                    a, b = _variant_text("add")
                    s, c = _score_confidence({"fx": _qa_fx_ok(fx, tol), "debounce": False, "volume": True, "min_move": True})
                    out.append({
                        "ticker": ticker,
                        "type": "add",
                        "p_eur": d["last_eur"],
                        "what": f"Add-on Dip (≤ {thr:.2f} €)",
                        "score": s, "confidence": c,
                        "variant_A": a, "variant_B": b
                    })

    # Moonshots warn
    ms = cfg.get("moonshots", {})
    ms_ticks = [t.upper() for t in ms.get("tickers", [])]
    rules = ms.get("rules", {})
    for t in ms_ticks:
        d = px.get(t)
        if not d:
            continue
        cond_intraday = d["chg_intraday"] <= rules.get("warn_intraday", -0.15)
        cond_vs5d = d["vs5d"] <= rules.get("warn_vs5d", -0.25)
        cond_vol = d["vol_x"] >= rules.get("vol_x", 1.5)
        if cond_vol and (cond_intraday or cond_vs5d):
            key = ("mars", t, "warn")
            if not _debounced(key, debounce_s):
                s, c = _score_confidence({"fx": _qa_fx_ok(fx, tol), "debounce": False, "volume": True, "min_move": True})
                out.append({
                    "ticker": t,
                    "type": "warn",
                    "p_eur": d["last_eur"],
                    "what": "Moonshot-Warnung (Vol↑ & Drop)",
                    "score": s, "confidence": c,
                    "variant_A": "A: beobachten, Stops nachziehen",
                    "variant_B": "B: kleine Absicherung/Hedge erwägen"
                })

    return out


def _run_for_venus(cfg: dict) -> list:
    out = []
    px = _load_prices_eur()
    fx = _load_fx()

    meta = cfg.get("_meta", {})  # falls später benötigt
    debounce_s = 120
    tol = 0.002

    # NVDA Tranches
    nv = cfg.get("nvda_tranches", {})
    if "NVDA" in px:
        d = px["NVDA"]
        t1_if = nv.get("t1_if", {})
        fire_t1 = (
            (t1_if.get("close_below_low5", False) and d.get("vs5d", 0) <= -0.01) or
            (d.get("chg_intraday", 0) <= t1_if.get("intraday_drop", -0.06))
        ) and True  # vol_up Proxy

        if fire_t1:
            key = ("venus", "NVDA", "t1")
            if not _debounced(key, debounce_s):
                s, c = _score_confidence({"fx": _qa_fx_ok(fx, tol), "debounce": False, "volume": True, "min_move": True})
                out.append({
                    "ticker": "NVDA",
                    "type": "trim_t1",
                    "what": f"Tranche 1 ({nv.get('t1_pct', 0.25)*100:.0f}%)",
                    "score": s, "confidence": c,
                    "variant_A": "A: 25% trim, Stops enger",
                    "variant_B": "B: 20% trim + Hedge erwägen"
                })

        t2_if = nv.get("t2_if", {})
        if (t2_if.get("close_below_dma50", False) and d.get("vs5d", 0) <= -0.01) or t2_if.get("pivot_break", False):
            key = ("venus", "NVDA", "t2")
            if not _debounced(key, debounce_s):
                s, c = _score_confidence({"fx": _qa_fx_ok(fx, tol), "debounce": False, "volume": True, "min_move": True})
                rng = nv.get("t2_pct_range", [0.10, 0.15])
                out.append({
                    "ticker": "NVDA",
                    "type": "trim_t2",
                    "what": f"Tranche 2 ({int(rng[0]*100)}–{int(rng[1]*100)}%) bei Signal",
                    "score": s, "confidence": c,
                    "variant_A": "A: kleiner Schritt + Re-Check",
                    "variant_B": "B: voller Prozentsatz, Stops nachziehen"
                })

    # Add-on Dips (ASML, LLY, NVO, PEP, VOO, BEP)
    dips = cfg.get("add_on_dips", {})
    dip_ticks = [t.upper() for t in dips.get("tickers", [])]
    for t in dip_ticks:
        d = px.get(t)
        if not d:
            continue
        # Dip-Proxy via intraday-Drop und vs5d
        if d["chg_intraday"] <= -0.03 or d["vs5d"] <= -0.05:
            key = ("venus", t, "add")
            if not _debounced(key, 120):
                a, b = _variant_text("add")
                s, c = _score_confidence({"fx": _qa_fx_ok(fx, 0.002), "debounce": False, "volume": True, "min_move": True})
                out.append({
                    "ticker": t,
                    "type": "add",
                    "p_eur": d["last_eur"],
                    "what": "Add-on Dip (geplant, nicht jagen)",
                    "score": s, "confidence": c,
                    "variant_A": a, "variant_B": b
                })

    # Restpositionen: nur harte Breaks melden (Beispiele)
    rests = [t.upper() for t in cfg.get("restpositions", {}).get("tickers", [])]
    for t in rests:
        d = px.get(t)
        if not d:
            continue
        if d["vs5d"] <= -0.15:  # harter Break-Proxy
            key = ("venus", t, "rest_warn")
            if not _debounced(key, 120):
                s, c = _score_confidence({"fx": _qa_fx_ok(_load_fx(), 0.002), "debounce": False, "volume": True, "min_move": True})
                out.append({
                    "ticker": t,
                    "type": "warn",
                    "p_eur": d["last_eur"],
                    "what": "Restposition: harter Break",
                    "score": s, "confidence": c,
                    "variant_A": "A: beobachten",
                    "variant_B": "B: kleine Absicherung"
                })

    return out


def _run_for_family(cfg: dict) -> list:
    """Family-Level Heuristiken – hier placeholderhaft (P&L, Exposure, Cluster, Corr)."""
    out = []
    # In einer echten Umsetzung würdest du P&L/Exposure/Correlation aus einem Tages-Snapshot ziehen.
    # Wir geben hier nur Hinweise auf Basis der Konfiguration.
    risk = cfg.get("risk", {})
    exposure = cfg.get("exposure", {})
    cluster = cfg.get("cluster", {})
    corr = cfg.get("correlation", {})

    # Platzhalter-Alerts (nur als Reminder)
    out.append({
        "topic": "family_risk",
        "what": f"Family P&L-Wächter aktiv (Limits dd_family {risk.get('pnl_family_dd', -0.025):.3f} / dd_sub {risk.get('pnl_sub_dd', -0.035):.3f})",
        "score": 50, "confidence": 2,
        "variant_A": "A: nur beobachten",
        "variant_B": "B: Re-Check bei starken Indexbewegungen"
    })
    out.append({
        "topic": "exposure_guard",
        "what": f"Exposure-Limit ~{int(exposure.get('max_invested', 0.95)*100)}% – bei rotem Markt de-risk",
        "score": 55, "confidence": 2,
        "variant_A": "A: keine Aktion",
        "variant_B": "B: Mini-Trim in stärksten Gewinnern"
    })
    out.append({
        "topic": "cluster_nvda",
        "what": f"NVDA-Cluster Max {int(cluster.get('nvda_family_max', 0.20)*100)}%, Trim bevorzugt in {cluster.get('prefer_trim_portfolio', 'venus')}",
        "score": 60, "confidence": 3,
        "variant_A": "A: nur Hinweis",
        "variant_B": "B: bei Signal Tranche in bevorzugtem Depot"
    })
    out.append({
        "topic": "corr_ndx",
        "what": f"Korrelation-Wächter vs. NDX > {int(corr.get('ndx_threshold', 0.90)*100)}% → {corr.get('action', 'diversify_hint')}",
        "score": 55, "confidence": 2,
        "variant_A": "A: halten",
        "variant_B": "B: Diversifikation prüfen"
    })
    return out


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
def run_alerts(name: str, cfg: dict | None = None) -> list:
    """
    name ∈ {'mars','venus','family'}
    cfg: Teil-Baum aus alerts_config.json (z.B. cfg['mars'])
    """
    cfg = {} if cfg is None else cfg
    if name == "mars":
        # meta aus root in den Bereich leiten
        cfg["meta"] = cfg.get("meta", {})
        return _run_for_mars({**cfg, "meta": cfg.get("meta", {})})
    if name == "venus":
        return _run_for_venus(cfg)
    if name == "family":
        return _run_for_family(cfg)
    return []
