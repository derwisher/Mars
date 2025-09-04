#!/usr/bin/env python3
# tools/live_data.py
#
# Zieht Live-Kurse per yfinance, normiert auf EUR und schreibt einen Snapshot
# nach data/prices_eur_snapshot.csv. Für die Alerts werden diese Preise gelesen.

import os
import time
import json
import csv
import math
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_CSV = DATA / "prices_eur_snapshot.csv"

# --------- Hilfen

def now_utc_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]

def load_portfolio_tickers() -> set[str]:
    """liest data/portfolios.json (Mars & Venus) falls vorhanden"""
    tickers = set()
    f = DATA / "portfolios.json"
    if f.exists():
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
            for k in ("Mars", "Venus"):
                if k in obj and "tickers" in obj[k]:
                    tickers.update(obj[k]["tickers"])
        except Exception:
            pass
    return tickers

def load_universe() -> list[str]:
    uni = set()
    for name in ("universe_core.txt", "universe_watch.txt"):
        uni.update(read_lines(DATA / name))
    uni.update(load_portfolio_tickers())
    # Filter offensichtliche Fehleinträge
    return sorted(t for t in uni if len(t) >= 2 and all(ch not in t for ch in (" ", ",")))

def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

# --------- FX (EUR-Umrechnung)

def fetch_eur_fx():
    """liefert Umrechnungskurse in ein dict: { 'USD': usd_to_eur, 'EUR': 1.0, ... }"""
    fx = {"EUR": 1.0}
    # EURUSD=X ist USD pro 1 EUR. Wir brauchen USD->EUR => 1 / (EURUSD)
    try:
        eurusd = yf.Ticker("EURUSD=X").history(period="1d")["Close"]
        if not eurusd.empty and eurusd.iloc[-1] > 0:
            fx["USD"] = 1.0 / float(eurusd.iloc[-1])
    except Exception:
        pass
    # einfache Defaults, falls FX nicht abrufbar:
    fx.setdefault("USD", 0.93)  # grobe Hausnummer als Fallback
    return fx

# --------- Kurse ziehen

def fetch_snapshot(tickers: list[str]) -> pd.DataFrame:
    """
    Holt fast_info / Kursdaten via yfinance.
    Ergebnis-DataFrame mit Spalten: last, prevClose, volume, avgVol, currency
    """
    rows = []
    for batch in chunk(tickers, 50):  # schonend
        info = yf.Tickers(" ".join(batch))
        # yfinance liefert .tickers dict
        for sym in batch:
            try:
                t = info.tickers.get(sym)
                if t is None:
                    continue
                fi = getattr(t, "fast_info", None)
                last = None
                prev = None
                vol = None
                avg_vol = None
                curr = None

                if fi:
                    # fast_info (neue API) – robust
                    last = getattr(fi, "last_price", None)
                    prev = getattr(fi, "previous_close", None)
                    vol  = getattr(fi, "last_volume", None)
                    avg_vol = getattr(fi, "ten_day_average_volume", None)
                    curr = getattr(fi, "currency", None)
                # Fallback: history
                if last is None or curr is None:
                    h = t.history(period="1d")
                    if not h.empty:
                        last = float(h["Close"].iloc[-1])
                        prev = float(h["Close"].iloc[0])
                    info2 = t.info or {}
                    curr = curr or info2.get("currency")
                    vol = vol or info2.get("volume")
                    avg_vol = avg_vol or info2.get("averageVolume")

                if last is None:
                    continue

                rows.append({
                    "ticker": sym,
                    "last": float(last),
                    "prevClose": float(prev) if prev is not None else math.nan,
                    "volume": int(vol) if vol is not None and not math.isnan(float(vol)) else 0,
                    "avgVol": int(avg_vol) if avg_vol is not None and not math.isnan(float(avg_vol)) else 0,
                    "currency": curr or "USD"
                })
            except Exception:
                # still & steady – wir überspringen fehlerhafte Symbole
                continue
        time.sleep(0.8)  # Rate-Limit schonen
    return pd.DataFrame(rows)

def convert_to_eur(df: pd.DataFrame, fx: dict) -> pd.DataFrame:
    if df.empty:
        return df
    def _conv(v, cur):
        if pd.isna(v):
            return v
        rate = fx.get(cur or "EUR", 1.0)
        return float(v) * float(rate)
    df = df.copy()
    df["last_eur"] = [ _conv(v, c) for v, c in zip(df["last"], df["currency"]) ]
    df["prevClose_eur"] = [ _conv(v, c) for v, c in zip(df["prevClose"], df["currency"]) ]
    df["as_of"] = now_utc_iso()
    return df

def save_csv(df: pd.DataFrame, path: Path):
    cols = ["ticker","last","prevClose","volume","avgVol","currency","last_eur","prevClose_eur","as_of"]
    df = df.reindex(columns=cols)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)

def main():
    tickers = load_universe()
    if not tickers:
        print("No tickers in data/universe_*.txt or portfolios.json")
        return
    fx = fetch_eur_fx()
    df = fetch_snapshot(tickers)
    df = convert_to_eur(df, fx)
    save_csv(df, OUT_CSV)
    print(f"[OK] prices snapshot -> {OUT_CSV} ({len(df)} rows)")

if __name__ == "__main__":
    main()
