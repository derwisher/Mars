# Mars Hub v0.6 (Mars+Venus, Rotation 4, FRED macro, Volume, Stooq fallback, Ignore/Big-Universe)
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

# ==== Depots ====
MARS_TICKERS  = ["GOOGL","DDOG","MSFT","CPNG","ARM","ENVX","SHOP","SNOW","AMZN","NVDA","SE","MPWR","TSM"]
VENUS_TICKERS = ["MSFT","AMZN","ASML","NVDA","LLY","NVO","PEP","PG","VOO"]

MARS_DCA  = {"GOOGL":105,"DDOG":315,"MSFT":150,"CPNG":63,"ARM":315,"ENVX":62,"SHOP":125,"SNOW":315,"AMZN":115,"NVDA":190,"SE":125,"MPWR":305,"TSM":315}
VENUS_DCA = {"MSFT":58,"AMZN":58,"ASML":48,"NVDA":29,"LLY":60,"NVO":60,"PEP":34,"PG":34,"VOO":99}

DEPOT_MAP: Dict[str,str] = {t:"Mars" for t in MARS_TICKERS} | {t:"Venus" for t in VENUS_TICKERS}

# ---- yfinance + Stooq ----
try:
    import yfinance as yf
except Exception:
    yf = None
from pandas_datareader import data as pdr

def _fetch_yf_ohlcv(tickers: List[str], days: int):
    if yf is None or not tickers: return None, None
    end = datetime.now(timezone.utc); start = end - pd.Timedelta(days=int(days*1.6))
    data = yf.download(tickers, start=start, end=end, progress=False, interval="1d", auto_adjust=True, group_by="column")
    if data is None or len(data)==0: return None, None
    if isinstance(data.columns, pd.MultiIndex):
        close = data['Close'].copy(); vol = data['Volume'].copy()
    else:
        close = data.copy(); vol = None
    close = close.dropna(how="all").ffill().dropna(how="all")
    if vol is not None: vol = vol.reindex_like(close).fillna(0)
    for t in tickers:
        if t not in close.columns: close[t]=np.nan
        if vol is not None and t not in vol.columns: vol[t]=0
    close = close[tickers].ffill().tail(days)
    if vol is not None: vol = vol[tickers].tail(days)
    return close, vol

def _fetch_stooq_close(tickers: List[str], days: int):
    try:
        end = datetime.now(timezone.utc); start = end - pd.Timedelta(days=int(days*1.6))
        frames=[]
        for t in tickers:
            try:
                df = pdr.DataReader(t, "stooq", start=start, end=end)[["Close"]].rename(columns={"Close":t})
                frames.append(df.sort_index())
            except Exception:
                pass
        if not frames: return None
        close = pd.concat(frames, axis=1).ffill().dropna(how="all").tail(days)
        for t in tickers:
            if t not in close.columns: close[t]=np.nan
        return close[tickers]
    except Exception:
        return None

def fetch_prices_volumes(tickers: List[str], days: int = 252):
    if FREE_MODE:
        close, vol = _fetch_yf_ohlcv(tickers, days)
        if close is None or close.empty:
            close = _fetch_stooq_close(tickers, days); vol = None
        if close is not None and not close.empty:
            return close, vol
    dates = pd.bdate_range(end=datetime.today(), periods=days)
    return pd.DataFrame({t:100.0 for t in tickers}, index=dates), None

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
            s = 0.5*(prices[t].iloc[-1]/prices[t].iloc[-20]-1) + 0.5*(prices[t].iloc[-1]/prices[t].iloc[-60]-1)
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
    mom = compute_momentum(prices); qual = compute_quality(f); gro = compute_growth(f); risk = compute_risk(prices)
    def norm(x): return (x-x.min())/(x.max()-x.min()+1e-9)
    score = 0.35*gro + 0.25*qual + 0.25*norm(mom) + 0.10*0.5 + (-0.05)*norm(risk)
    return score.sort_values(ascending=False)

# ==== Ignore & Rotation ====
def read_ignore() -> set:
    s=set()
    try:
        with open("data/universe_ignore.txt","r",encoding="utf-8") as f:
            for line in f:
                k=line.strip().upper()
                if k and not k.startswith("#"): s.add(k)
    except Exception: pass
    return s

def read_universe_files() -> List[str]:
    tickers = set(MARS_TICKERS + VENUS_TICKERS)
    for path in ["data/universe_core.txt","data/universe_watch.txt","data/universe_all.txt"]:
        try:
            with open(path,"r",encoding="utf-8") as f:
                for line in f:
                    s=line.strip().upper()
                    if s and not s.startswith("#"): tickers.add(s)
        except Exception: pass
    ignore = read_ignore()
    return [t for t in sorted(tickers) if t not in ignore]

def rotate_universe(tickers: List[str], max_n: int=200, slots: int=4) -> List[str]:
    if len(tickers) <= max_n: return tickers
    now = datetime.utcnow(); slot_idx = now.hour % max(slots,1)
    chunk_size = math.ceil(len(tickers)/slots)
    start = slot_idx*chunk_size; end = min((slot_idx+1)*chunk_size, len(tickers))
    return tickers[start:end][:max_n]

# ==== FRED Macro (DGS10) ====
from pandas_datareader import data as pdr_fred
def fetch_macro_10y() -> float | None:
    try:
        ser = pdr_fred.DataReader("DGS10", "fred")
        val = float(ser.dropna().iloc[-1].values[0]) / 100.0
        return val
    except Exception:
        return None

# ==== Pipeline ====
def run_pipeline(days=252) -> dict:
    all_tickers = read_universe_files()
    slots = int(os.getenv("ROTATION_SLOTS","4"))
    tickers = rotate_universe(all_tickers, max_n=200, slots=slots)
    prices, volumes = fetch_prices_volumes(tickers, days)
    f      = fetch_fundamentals(tickers)
    scores = composite_score(prices,f)
    var_mars  = historical_var(prices[[t for t in MARS_TICKERS  if t in prices.columns]])
    var_venus = historical_var(prices[[t for t in VENUS_TICKERS if t in prices.columns]])
    macro10 = fetch_macro_10y()
    return {
        "prices":prices, "volumes":volumes,
        "fundamentals":f, "scores":scores,
        "var":{"mars":var_mars,"venus":var_venus},
        "macro":{"UST10Y": macro10},
        "depot_map": DEPOT_MAP
    }
