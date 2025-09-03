import json, os, pathlib
from datetime import datetime
import numpy as np
import pandas as pd
from mars_hub import run_pipeline, MARS_TICKERS, MARS_DCA, VENUS_TICKERS, VENUS_DCA, correlation_matrix

def pack_dca_flags_only(dca_dict: dict):
    return [{"ticker": t, "active": float(eur) > 0} for t, eur in sorted(dca_dict.items())]

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def load_alerts_config():
    p = pathlib.Path("data/alerts_config.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def compute_alerts(prices: pd.DataFrame, volumes: pd.DataFrame | None, universe: list, depot_map: dict, cfg: dict) -> list:
    alerts=[]; 
    if prices is None or prices.empty: return alerts
    cols=[t for t in universe if t in prices.columns]
    px=prices[cols].copy(); rets=px.pct_change().fillna(0.0)
    sma20=px.rolling(20).mean(); sma60=px.rolling(60).mean(); hh20=px.rolling(20).max()

    def gval(t, book, key, fallback):
        tk=(cfg.get("tickers") or {}).get(t, {})
        if key in tk: return float(tk[key])
        bk=(cfg.get("books") or {}).get(book, {})
        if key in bk: return float(bk[key])
        df=(cfg.get("default") or {})
        return float(df.get(key, fallback))

    vol=None; vol20=None
    if volumes is not None:
        vol=volumes.reindex(px.index)[cols].fillna(0); vol20=vol.rolling(20).mean()

    last=px.index[-1]; prev1=px.index[-2] if len(px)>=2 else last

    for t in cols:
        try:
            book=depot_map.get(t,"Mars")
            mv=gval(t,book,"breakout_move_vol",1.0)/100.0
            mnv=gval(t,book,"breakout_move_novol",2.0)/100.0
            ts=gval(t,book,"trim_stretch",8.0)/100.0
            tr=gval(t,book,"trim_rsi",72.0)
            ddL=gval(t,book,"drawdown20",8.0)/100.0

            # Breakout (same-day)
            cond_ma=px.loc[last,t]>max(sma20.loc[last,t],sma60.loc[last,t])
            if vol is not None and vol20 is not None and vol20.loc[last,t]>0:
                cond_bo = cond_ma and ((rets.loc[last,t]>=mv and vol.loc[last,t]>1.5*vol20.loc[last,t]) or (rets.loc[last,t]>=mnv))
            else:
                cond_bo = cond_ma and (rets.loc[last,t]>=mnv)
            if cond_bo:
                alerts.append({"ticker":t,"type":"momentum_breakout","status":"watch","book":book,
                               "severity":"info","reason":f"BO {rets.loc[last,t]*100:.2f}% vs SMA20/60"})

            # Trim
            stretch=(px.loc[last,t]-sma20.loc[last,t])/(sma20.loc[last,t]+1e-9)
            rsi=_rsi(px[t]); rsi_last=float(rsi.iloc[-1]) if len(rsi)>0 else 0.0
            five_up=(px.loc[last,t]/px.loc[px.index[-6],t]-1)>=0.10 if len(px)>=6 else False
            stall  =px.loc[last,t]<=px.loc[prev1,t]
            if (stretch>=ts) and (rsi_last>=tr) and (stall or five_up):
                alerts.append({"ticker":t,"type":"trim","status":"consider","book":book,
                               "severity":"warn","reason":f"Stretch {stretch*100:.1f}%, RSI {rsi_last:.0f}"})

            # Risk drawdown vs 20d high
            dd=1.0-(px.loc[last,t]/(hh20.loc[last,t]+1e-9))
            if dd>=ddL:
                alerts.append({"ticker":t,"type":"risk_drawdown","status":"alert","book":book,
                               "severity":"alert","reason":f"Drawdown {dd*100:.1f}% vs 20d high"})
        except Exception:
            pass
    return alerts[:20]

def main():
    payload = run_pipeline()
    prices  = payload["prices"]; volumes = payload["volumes"]
    scores  = payload["scores"]; var = payload["var"]
    macro   = payload.get("macro", {}); depot_map=payload.get("depot_map",{})
    corr    = correlation_matrix(prices)

    universe = list(prices.columns)
    cfg = load_alerts_config()
    alerts = compute_alerts(prices, volumes, universe, depot_map, cfg)

    summary = {
      "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
      "universe": universe,
      "dca": {
        "Mars":  pack_dca_flags_only(MARS_DCA),
        "Venus": pack_dca_flags_only(VENUS_DCA)
      },
      "scores_top15":[{"ticker":t,"score":round(float(s),4)} for t,s in scores.head(15).items()],
      "risk": {"var_1d_95":{"Mars":round(float(var["mars"]),6), "Venus":round(float(var["venus"]),6)}},
      "macro": macro,
      "alerts_today": alerts
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__=="__main__": main()
