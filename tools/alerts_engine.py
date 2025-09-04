import csv, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG  = json.load(open(ROOT / "data" / "alerts_config.json", "r", encoding="utf-8"))

def load_fx(path=ROOT / "data" / "fx_snapshot.csv"):
    if not path.exists():
        return {"ok": True, "rate": 1.085, "sample": [1.085]}
    rates=[]
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try: rates.append(float(row["rate"]))
            except: pass
    ok = len(rates) >= 3
    rate = sum(rates)/len(rates) if rates else 1.085
    return {"ok": ok, "rate": rate, "sample": rates}

def fx_gate(fx):
    if not fx["ok"] or len(fx["sample"])<3: return False
    mx, mn = max(fx["sample"]), min(fx["sample"])
    mid = (mx+mn)/2
    return (mx-mn) <= CFG["fx_tolerance"] * mid

def load_prices_csv(path=ROOT / "data" / "prices_eur_snapshot.csv"):
    """CSV-Header: ticker,eur,usd,low5,dma50,change5d,changeIntraday,volX"""
    if not path.exists(): return {}
    out={}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[row["ticker"]] = {
                    "eur": float(row["eur"]),
                    "usd": float(row["usd"]),
                    "low5": float(row["low5"]),
                    "dma50": float(row["dma50"]),
                    "change5d": float(row["change5d"]),
                    "changeIntraday": float(row["changeIntraday"]),
                    "volX": float(row["volX"])
                }
            except: pass
    return out

def ts_cet():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

def build_alert(scope,ticker,topic,msg,eur,usd,score,confidence):
    aid = f"{datetime.utcnow().isoformat()}_{ticker}_{topic.replace(' ','')}"
    return {
        "id": aid, "triggered": True, "scope": scope, "ticker": ticker,
        "topic": topic, "message": msg, "score": score, "confidence": confidence,
        "variantA": "Variante A: konservativ – De-Risk/Trim/Cash erhöhen.",
        "variantB": "Variante B: aggressiv – laufen lassen, Stops enger.",
        "timestampCET": ts_cet(), "eurLevel": eur, "usdRef": usd
    }

def run_portfolio_a(prices):
    cfg = CFG["portfolio_a"]; alerts=[]
    uni = cfg.get("universe",[])
    cg  = cfg["core_growth"]
    # Core/Growth
    for t in uni:
        p = prices.get(t); 
        if not p: continue
        if p["change5d"] <= cg["trim_down_5d"]:
            alerts.append(build_alert("portfolio_a", t, "Trim Alert",
                f"≤ {abs(cg['trim_down_5d'])*100:.0f}% vs 5D",
                f"€{p['eur']:.2f}", f"${p['usd']:.2f}", 45, 5))
        if p["changeIntraday"] >= cg["tp_up_intraday"]:
            alerts.append(build_alert("portfolio_a", t, "Take Profit",
                f"≥ {cg['tp_up_intraday']*100:.0f}% intraday",
                f"€{p['eur']:.2f}", f"${p['usd']:.2f}", 60, 5))
    # Satelliten
    for t, rule in cfg.get("satellites",{}).items():
        p = prices.get(t)
        if p and p["eur"] < rule.get("add_below_eur", -1):
            alerts.append(build_alert("portfolio_a", t, "Add Dip",
                f"< €{rule['add_below_eur']:.2f}",
                f"€{p['eur']:.2f}", f"${p['usd']:.2f}", 70, 5))
    # Moonshots
    m = cfg["moonshots"]
    for t in ["ENVX","CPNG","SE"]:
        p = prices.get(t); 
        if not p: continue
        if (p["changeIntraday"] <= m["intraday_down"] and p["volX"]>=m["volume_x"]) or (p["change5d"]<=m["vs5d_down"]):
            alerts.append(build_alert("portfolio_a", t, "Moonshot Warnung",
                f"intra {p['changeIntraday']*100:.0f}% / 5d {p['change5d']*100:.0f}% / Vol {p['volX']}×",
                f"€{p['eur']:.2f}", f"${p['usd']:.2f}", 40, 5))
    return alerts

def run_portfolio_b(prices):
    cfg = CFG["portfolio_b"]; alerts=[]
    nv = prices.get("NVDA")
    tcfg = cfg["nvda_tranches"]
    if nv:
        t1 = (tcfg["t1_close_low5"] and nv["eur"] < nv["low5"] and nv["volX"]>=1.5) or \
             (nv["changeIntraday"] <= tcfg["t1_intraday"] and nv["volX"]>=1.5)
        if t1:
            alerts.append(build_alert("portfolio_b","NVDA","T1 Trim",
                "Close < LOW5 o. −6% intraday (Vol Spike)",
                f"€{nv['eur']:.2f}", f"${nv['usd']:.2f}", 78, 5))
        if tcfg["t2_close_dma50"] and nv["eur"] < nv["dma50"]:
            alerts.append(build_alert("portfolio_b","NVDA","T2 Trim",
                "Close < DMA50", f"€{nv['eur']:.2f}", f"${nv['usd']:.2f}", 70,5))
    # Restpositionen harte Brüche
    if cfg["restpositions"]["hard_break_only"]:
        for t in cfg["universe_ist"]:
            p = prices.get(t); 
            if not p: continue
            if p["eur"] < p["low5"] and p["volX"]>=1.5:
                alerts.append(build_alert("portfolio_b", t, "Restposition Break",
                    "Close < LOW5 + Vol Spike",
                    f"€{p['eur']:.2f}", f"${p['usd']:.2f}", 50, 5))
    return alerts

def run_alerts(scope="portfolio_a"):
    fx = load_fx()
    if not fx_gate(fx): return []
    prices = load_prices_csv()
    if scope=="portfolio_a":  return run_portfolio_a(prices)
    if scope=="portfolio_b":  return run_portfolio_b(prices)
    if scope=="family":       return []  # (später Family-P&L/Exposure/Korrelation)
    return []

if __name__ == "__main__":
    print(json.dumps({"alerts": run_alerts("portfolio_a")}, ensure_ascii=False))
