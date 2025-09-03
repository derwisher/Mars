# Mars Hub v0.3 (Free-Mode, neutral)
from __future__ import annotations
import os, json, math, random
from datetime import datetime, timezone
from typing import Dict, List
import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

FREE_MODE = True
random.seed(42); np.random.seed(42)

# ==== Mars-Depot (neutral) ====
MARS_TICKERS = ["GOOGL","DDOG","MSFT","CPNG","ARM","ENVX","SHOP","SNOW","AMZN","NVDA","SE","MPWR","TSM"]
MARS_DCA     = {"GOOGL":105,"DDOG":315,"MSFT":150,"CPNG":63,"ARM":315,"ENVX":62,"SHOP":125,"SNOW":315,"AMZN":115,"NVDA":190,"SE":125,"MPWR":305,"TSM":315}

# ==== Preise via yfinance (Free) ====
try:
    import yfinance as yf
except Exception:
    yf = None

def fetch_prices(tickers: List[str], days: int = 252) -> pd.DataFrame:
    if FREE_MODE and yf is not None:
        end = datetime.now(timezone.utc)
        start = end - pd.Timedelta(days=int(days*1.6))
        data = yf.download(tickers, start=start, end=end, progress=False, interval="1d", auto_adjust=True, group_by='column')
        if isinstance(data.columns, pd.MultiIndex):
            close = data['Close'].copy()
        else:
            close = data.copy()
        close = close.dropna(how="all").ffill().dropna(how="all")
        for t in tickers:
            if t not in close.columns:
                close[t] = np.nan
        close = close[tickers].ffill()
        return close.tail(days)
    # Fallback: einfache konstante Mock-Serie (nur als Notnagel)
    dates = pd.bdate_range(end=datetime.today(), periods=days)
    return pd.DataFrame({t:100.0 for t in tickers}, index=dates)

# ==== Fundamentals (Mock) ====
class Fundamentals:
    def __init__(self, tickers: List[str]):
        self.revenue_growth = {t: float(np.random.uniform(0.05,0.40)) for t in tickers}
        self.fcf_margin     = {t: float(np.random.uniform(0.05,0.35)) for t in tickers}
        self.net_debt_to_ebitda = {t: float(np.random.uniform(0.0,2.0)) for t in tickers}
        self.pe_forward     = {t: float(np.random.uniform(15,55)) for t in tickers}

def fetch_fundamentals(tickers: List[str]) -> Fundamentals:
    return Fundamentals(tickers)

# ==== Faktoren & Risiko ====
def compute_momentum(prices: pd.DataFrame) -> pd.Series:
    scores = {}
    for t in prices.columns:
        try:
            s = (prices[t].iloc[-1]/prices[t].iloc[-20]-1 + prices[t].iloc[-1]/prices[t].iloc[-60]-1)/2
        except Exception:
            s = 0.0
        scores[t] = s
    return pd.Series(scores)

def compute_quality(f: Fundamentals) -> pd.Series:
    df = pd.DataFrame({
        "fcf": pd.Series(f.fcf_margin),
        "debt": -pd.Series(f.net_debt_to_ebitda),
        "pe": -(pd.Series(f.pe_forward)/60.0),
    })
    df = (df-df.min())/(df.max()-df.min()+1e-9)
    return df.mean(axis=1)

def compute_growth(f: Fundamentals) -> pd.Series:
    g = pd.Series(f.revenue_growth)
    return (g-g.min())/(g.max()-g.min()+1e-9)

def compute_risk(prices: pd.DataFrame) -> pd.Series:
    vol = prices.pct_change().dropna().std()
    return (vol-vol.min())/(vol.max()-vol.min()+1e-9)

def correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna().corr()

def historical_var(prices: pd.DataFrame, alpha=0.95) -> float:
    rets = prices.pct_change().dropna().mean(axis=1)
    return float(-np.percentile(rets, (1-alpha)*100))

def composite_score(prices: pd.DataFrame, f: Fundamentals) -> pd.Series:
    mom = compute_momentum(prices)
    qual = compute_quality(f)
    gro  = compute_growth(f)
    risk = compute_risk(prices)
    def norm(x): return (x-x.min())/(x.max()-x.min()+1e-9)
    score = 0.35*gro + 0.25*qual + 0.25*norm(mom) + 0.10*0.5 + (-0.05)*norm(risk)
    return score.sort_values(ascending=False)

def run_pipeline(days=252) -> dict:
    tickers = MARS_TICKERS
    prices  = fetch_prices(tickers, days)
    f       = fetch_fundamentals(tickers)
    scores  = composite_score(prices,f)
    var     = historical_var(prices)
    return {"prices":prices,"fundamentals":f,"scores":scores,"var":{"mars":var}}
