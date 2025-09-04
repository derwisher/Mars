# tools/live_data.py
#!/usr/bin/env python3
import math, time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT  = DATA / "prices_eur_snapshot.csv"

# === Universum bestimmen (Depot + Watch) ===
def load_universe() -> list[str]:
    uni = set()
    for name in ("universe_core.txt", "universe_watch.txt"):
        p = DATA / name
        if p.exists():
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    uni.add(ln)
    # fallback: harte Minimalmenge
    if not uni:
        uni.update(["MSFT","AMZN","GOOGL","NVDA","ASML","LLY","NVO","CRWD","SU.PA","VRT","ENVX","CPNG","SNOW","DDOG","ARM","SHOP","SE"])
    return sorted(uni)

def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def eur_rate_from_eurusd() -> float:
    """liefert USD->EUR (1 USD = ? EUR)  über EURUSD=X (USD pro 1 EUR)"""
    try:
        eurusd = yf.Ticker("EURUSD=X").history(period="1d")["Close"]
        if not eurusd.empty and eurusd.iloc[-1] > 0:
            return 1.0 / float(eurusd.iloc[-1])
    except Exception:
        pass
    return 0.93  # Fallback

def fetch_batch(tickers: list[str]) -> pd.DataFrame:
    """holt für tickers Kurse/Volumina & baut Kennzahlen"""
    rows = []
    rate_usd_to_eur = eur_rate_from_eurusd()
    for sym in tickers:
        try:
            t = yf.Ticker(sym)

            # 21 Handelstage → ~1 Monat für 20d-Volumen
            hist = t.history(period="30d", interval="1d", auto_adjust=False)
            if hist.empty:
                continue

            # Schlusskurse
            close = hist["Close"].astype(float)
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) >= 2 else float("nan")

            # 5-Tage-Close (C[-5]) für vs5d
            prev5 = float(close.iloc[-6]) if len(close) >= 6 else (float(close.iloc[0]) if len(close) > 0 else float("nan"))

            # Volumen
            if "Volume" in hist.columns:
                vol = float(hist["Volume"].iloc[-1] or 0.0)
                vol20 = float(hist["Volume"].tail(20).mean() or 0.0)
            else:
                vol, vol20 = 0.0, 0.0

            # DMA50 approximieren aus 50d falls verfügbar
            hist_long = t.history(period="90d", interval="1d", auto_adjust=False)
            dma50 = float(hist_long["Close"].tail(50).mean()) if not hist_long.empty and len(hist_long) >= 50 else float("nan")

            # Währung
            info_curr = None
            try:
                info_curr = t.fast_info.currency
            except Exception:
                pass
            if not info_curr:
                try:
                    info_curr = t.info.get("currency")
                except Exception:
                    info_curr = "USD"

            # EUR-Umrechnung (einfach: USD→EUR via Rate; EUR bleibt 1.0)
            def to_eur(v: float, cur: str) -> float:
                if math.isnan(v):
                    return v
                if (cur or "USD").upper() == "USD":
                    return v * rate_usd_to_eur
                return v  # EUR, CHF etc. hier als nominal gelassen

            last_eur = to_eur(last, info_curr)
            prev_eur = to_eur(prev, info_curr)
            prev5_eur = to_eur(prev5, info_curr)
            dma50_eur = to_eur(dma50, info_curr)

            # Kennzahlen
            chg_intraday = (last_eur - prev_eur) / prev_eur if (prev_eur and not math.isnan(prev_eur) and prev_eur != 0) else 0.0
            vs5d = (last_eur - prev5_eur) / prev5_eur if (prev5_eur and not math.isnan(prev5_eur) and prev5_eur != 0) else 0.0
            vol_x = (vol / vol20) if vol20 else 0.0

            rows.append({
                "ticker": sym,
                "last_eur": round(last_eur, 6),
                "prevClose_eur": round(prev_eur, 6) if not math.isnan(prev_eur) else "",
                "low5_eur": round(prev5_eur, 6) if not math.isnan(prev5_eur) else "",
                "dma50_eur": round(dma50_eur, 6) if not math.isnan(dma50_eur) else "",
                "change_intraday_pct": round(chg_intraday, 6),
                "vs5d_pct": round(vs5d, 6),
                "vol_x": round(vol_x, 3),
                "currency": info_curr or "",
                "as_of": now_utc()
            })
            time.sleep(0.25)  # Rate-Limit schonen
        except Exception:
            continue
    return pd.DataFrame(rows)

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    uni = load_universe()
    df = fetch_batch(uni)
    cols = ["ticker","last_eur","prevClose_eur","low5_eur","dma50_eur","change_intraday_pct","vs5d_pct","vol_x","currency","as_of"]
    if not df.empty:
        df = df.reindex(columns=cols)
    df.to_csv(OUT, index=False)
    print(f"[OK] wrote {len(df)} rows to {OUT}")

if __name__ == "__main__":
    main()
