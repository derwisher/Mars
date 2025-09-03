import json
from datetime import datetime
import numpy as np
import pandas as pd

from mars_hub import run_pipeline, MARS_TICKERS, MARS_DCA, correlation_matrix

def pack_dca_flags_only(dca_dict: dict):
    # Nur Ticker + Aktiv-Flag (keine Euro-Beträge im öffentlichen JSON)
    out = []
    for t, eur in sorted(dca_dict.items()):
        out.append({"ticker": t, "active": float(eur) > 0})
    return out

def compute_simple_alerts(prices: pd.DataFrame, universe: list) -> list:
    """
    Breakout (Free-Mode):
    - Close > SMA20 UND Close > SMA60
    - 1d Return > +1.25%
    """
    alerts=[]
    if prices.empty: return alerts
    px=prices[[t for t in universe if t in prices.columns]]
    rets=px.pct_change().fillna(0.0)
    sma20=px.rolling(20).mean(); sma60=px.rolling(60).mean()
    last=px.index[-1]
    for t in px.columns:
        try:
            if px.loc[last,t]>max(sma20.loc[last,t],sma60.loc[last,t]) and rets.loc[last,t]>0.0125:
                alerts.append({"ticker":t,"type":"momentum_breakout"})
        except: pass
    return alerts[:5]

def main():
    payload=run_pipeline()
    prices=payload["prices"]; scores=payload["scores"]; var=payload["var"]
    corr=correlation_matrix(prices)
    alerts=compute_simple_alerts(prices,MARS_TICKERS)
    summary={
      "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
      "universe": list(prices.columns),
      "dca": {"Mars": pack_dca_flags_only(MARS_DCA)},
      "scores_top15":[{"ticker":t,"score":round(float(s),4)} for t,s in scores.head(15).items()],
      "risk": {"var_1d_95":{"Mars":round(float(var["mars"]),6)}},
      "alerts_today": alerts
    }
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
