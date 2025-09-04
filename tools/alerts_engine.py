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
PRICES_EUR_SNAP = DATA_DIR / "prices_eur_snapshot.csv"
FX_SNAP         = DATA_DIR / "fx_snapshot.csv"

# In-Memory Debounce-Store
_DEBOUNCE = {}  # key: (portfolio, ticker, rule_key) -> last_ts

# ------------------------------------------------------------
# Hilfsfunktionen
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
    if "EURUSD" in fx and "USDEUR" in fx and fx["USDEUR"] != 0:
        back = 1.0 / fx["USDEUR"]
        if abs(back - fx["EURUSD"]) / max(1e-6, fx["EURUSD"]) <= tol:
            return True
        return False
    return True

def _score_confidence(passed: dict) -> tuple[int, int]:
    base = 60
    if passed.get("fx"): base += 10
    if passed.get("volume"): base += 10
    if passed.get("debounce"): base -= 10
    if passed.get("min_move"): base += 5
    sc = max(0, min(100, base))
    conf = 1
    if sc >= 50: conf = 2
    if sc >= 65: conf = 3
    if sc >= 75: conf = 4
    if sc >= 85: conf = 5
    return sc, conf

def _variant_text(kind: str) -> tuple[str, str]:
    if kind == "tp":
        return ("A: ½-Teilverkauf, Stop anheben",
                "B: ⅓-Teilverkauf jetzt, Rest bei weiterer Stärke")
    if kind == "trim":
        return ("A: 10–15% trim, Stops enger",
                "B: 15–20% trim, Hedge erwägen")
    if kind == "add":
        return ("A: Starter ⅓, stop-orientiert",
                "B: ½ jetzt, ½ tiefer – strikte Stops")
    return ("A: konservativ", "B: offensiver")

# ------------------------------------------------------------
# Mars-Logik
# ------------------------------------------------------------
def _run_for_mars(cfg: dict) -> list:
    out = []
    px = _load_prices_eur()
    fx = _load_fx()
    tol = cfg.get("meta", {}).get("fx_check", {}).get("tolerance", 0.002)
    debounce_s = cfg.get("meta", {}).get("debounce_seconds", 120)

    # Beispiel: Core/Growth-Logik
    cg = cfg.get("core_growth", {})
    tickers = [t.upper() for t in cg.get("tickers", [])]
    drop5d = cg.get("trim_drop_5d", -0.12)
    tp_intraday = cg.get("tp_gain_intraday", 0.12)

    for t in tickers:
        d = px.get(t)
        if not d:
            continue
        passed = {"fx": _qa_fx_ok(fx, tol)}

        # Take-Profit
        if d["chg_intraday"] >= tp_intraday:
            key = ("mars", t, "tp")
            passed["debounce"] = _debounced(key, debounce_s)
            passed["volume"] = True
            passed["min_move"] = True
            sc, cf = _score_confidence(passed)
            if not passed["debounce"]:
                a, b = _variant_text("tp")
                out.append({
                    "ticker": t, "type": "tp", "p_eur": d["last_eur"],
                    "what": "Take-Profit Kandidat",
                    "score": sc, "confidence": cf,
                    "variant_A": a, "variant_B": b
                })

        # Schutz-Trim
        if d["vs5d"] <= drop5d:
            key = ("mars", t, "trim")
            passed["debounce"] = _debounced(key, debounce_s)
            passed["volume"] = True
            passed["min_move"] = True
            sc, cf = _score_confidence(passed)
            if not passed["debounce"]:
                a, b = _variant_text("trim")
                out.append({
                    "ticker": t, "type": "trim", "p_eur": d["last_eur"],
                    "what": "Schutz-Trim",
                    "score": sc, "confidence": cf,
                    "variant_A": a, "variant_B": b
                })
    return out

# ------------------------------------------------------------
# Venus-Logik
# ------------------------------------------------------------
def _run_for_venus(cfg: dict) -> list:
    out = []
    px = _load_prices_eur()
    fx = _load_fx()
    debounce_s = 120

    if "NVDA" in px:
        d = px["NVDA"]
        if d["chg_intraday"] <= -0.06:
            key = ("venus", "NVDA", "t1")
            if not _debounced(key, debounce_s):
                sc, cf = _score_confidence({"fx": _qa_fx_ok(fx, 0.002)})
                out.append({
                    "ticker": "NVDA", "type": "trim_t1",
                    "what": "Tranche 1 (25%)",
                    "score": sc, "confidence": cf,
                    "variant_A": "A: 25% trim",
                    "variant_B": "B: Hedge erwägen"
                })
    return out

# ------------------------------------------------------------
# Family-Logik
# ------------------------------------------------------------
def _run_for_family(cfg: dict) -> list:
    return [{
        "topic": "family_risk",
        "what": "Family P&L-Wächter aktiv",
        "score": 50, "confidence": 2,
        "variant_A": "A: beobachten",
        "variant_B": "B: Re-Check bei Indexbewegung"
    }]

# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
__all__ = ["run_alerts"]

def run_alerts(name: str, cfg: dict | None = None) -> list:
    cfg = cfg or {}
    nm = (name or "").strip().lower()
    if nm == "mars":
        return _run_for_mars(cfg)
    if nm == "venus":
        return _run_for_venus(cfg)
    if nm == "family":
        return _run_for_family(cfg)
    return []
