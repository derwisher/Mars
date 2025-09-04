# tools/live_data.py
#!/usr/bin/env python3
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT  = DATA / "prices_eur_snapshot.csv"

# --- Universum: Depot + Watch ------------------------------------------------
def load_universe() -> List[str]:
    uni = set()
    for name in ("universe_core.txt", "universe_watch.txt"):
        p = DATA / name
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    uni.add(ln)
    if not uni:
        uni.update([
            "MSFT","AMZN","GOOGL","NVDA","ASML","LLY","NVO","CRWD",
            "SU.PA","VRT","ENVX","CPNG","SNOW","DDOG","ARM","SHOP","SE"
        ])
    return sorted(uni)

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# --- FX: baue Multiplikatoren -> EUR -----------------------------------------
def _safe_close(symbol: str) -> float | None:
    try:
        s = yf.Ticker(symbol).history(period="1d")["Close"]
        if not s.empty:
            v = float(s.iloc[-1])
            return v if v > 0 else None
    except Exception:
        pass
    return None

def build_fx_to_eur() -> Dict[str, float]:
    """
    Liefert Multiplikatoren von Währung -> EUR:
    EUR: 1.0
    USD: 1/EURUSD=X
    CHF: 1/EURCHF=X
    GBP: 1/EURGBP=X
    JPY: 1/EURJPY=X
    """
    pairs = {
        "EUR": None,          # Baseline
        "USD": "EURUSD=X",
        "CHF": "EURCHF=X",
        "GBP": "EURGBP=X",
        "JPY": "EURJPY=X",
    }
    mult: Dict[str, float] = {"EUR": 1.0}

    # Fallbacks (konservativ) – werden nur genutzt, wenn API ausfällt
    fallback = {"USD": 0.93, "CHF": 1.05, "GBP": 1.17, "JPY": 0.0062}

    for ccy, pair in pairs.items():
        if ccy == "EUR":
            continue
        rate = _safe_close(pair)  # z.B. EURUSD=X = USD pro 1 EUR
        if rate and rate > 0:
            mult[ccy] = 1.0 / rate
        else:
            mult[ccy] = fallback[ccy]

    return mult  # z.B. {"EUR":1.0, "USD":0.93, "CHF":1.05, ...}

# --- Download & Kennzahlen ---------------------------------------------------
def fetch_batch(tickers: List[str]) -> pd.DataFrame:
    rows = []
    to_eur = build_fx_to_eur()  # Multiplikatoren

    for sym in tickers:
        try:
            t = yf.Ticker(sym)

            # 30d/1d für Close/Vol; 90d/1d für DMA50
            hist = t.history(period="30d", interval="1d", auto_adjust=False)
            if hist.empty:
                continue

            close = hist["Close"].astype(float)
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) >= 2 else float("nan")

            # „5-Tage“ Proxy: Close vor 5 Handelstagen, sonst erstverfügbarer Close
            if len(close) >= 6:
                prev5 = float(close.iloc[-6])
            else:
                prev5 = float(close.iloc[0])

            # Volumen
            vol = float(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0.0
            vol20 = float(hist["Volume"].tail(20).mean()) if "Volume" in hist.columns else 0.0

            # DMA50
            hist_long = t.history(period="90d", interval="1d", auto_adjust=False)
            dma50 = float(hist_long["Close"].tail(50).mean()) if not hist_long.empty and len(hist_long) >= 50 else float("nan")

            # Währung ermitteln
            currency = None
            try:
                currency = t.fast_info.currency
            except Exception:
                pass
            if not currency:
                try:
                    currency = t.info.get("currency")
                except Exception:
                    currency = "USD"
            currency = (currency or "USD").upper()

            # EUR-Konvertierung
            mult = to_eur.get(currency, 1.0)  # unbekannte Währungen → 1.0 (neutral)
            def x(v: float) -> float:
                return v * mult if not math.isnan(v) else v

            last_eur   = x(last)
            prev_eur   = x(prev)
            prev5_eur  = x(prev5)
            dma50_eur  = x(dma50)

            # Kennzahlen
            chg_intraday = (last_eur - prev_eur) / prev_eur if (prev_eur and not math.isnan(prev_eur) and prev_eur != 0) else 0.0
            vs5d         = (last_eur - prev5_eur) / prev5_eur if (prev5_eur and not math.isnan(prev5_eur) and prev5_eur != 0) else 0.0
            vol_x        = (vol / vol20) if vol20 else 0.0

            rows.append({
                "ticker": sym,
                "last_eur": round(last_eur, 6),
                "prevClose_eur": round(prev_eur, 6) if not math.isnan(prev_eur) else "",
                "low5_eur": round(prev5_eur, 6) if not math.isnan(prev5_eur) else "",
                "dma50_eur": round(dma50_eur, 6) if not math.isnan(dma50_eur) else "",
                "change_intraday_pct": round(chg_intraday, 6),
                "vs5d_pct": round(vs5d, 6),
                "vol_x": round(vol_x, 3),
                "currency": currency,
                "as_of": now_utc(),
            })

            time.sleep(0.25)  # API freundlich behandeln
        except Exception:
            # Einzelne Ausfälle nicht eskalieren
            continue

    return pd.DataFrame(rows)

# --- Main --------------------------------------------------------------------
def main():
    DATA.mkdir(parents=True, exist_ok=True)
    uni = load_universe()
    df = fetch_batch(uni)
    cols = [
        "ticker","last_eur","prevClose_eur","low5_eur","dma50_eur",
        "change_intraday_pct","vs5d_pct","vol_x","currency","as_of"
    ]
    if not df.empty:
        df = df.reindex(columns=cols)
    df.to_csv(OUT, index=False)
    print(f"[OK] wrote {len(df)} rows to {OUT}")

if __name__ == "__main__":
    main()
