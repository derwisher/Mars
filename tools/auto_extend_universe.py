#!/usr/bin/env python3
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
P_CORE  = DATA / "universe_core.txt"
P_WATCH = DATA / "universe_watch.txt"
P_PORTF = DATA / "portfolios.json"
P_CFG   = DATA / "alerts_config.json"

def load_txt(p: Path) -> list[str]:
    if not p.exists(): return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out

def dump_txt(p: Path, lines: list[str]):
    p.write_text("\n".join(sorted(set(lines))) + "\n", encoding="utf-8")

def tickers_from_cfg(cfg: dict) -> set[str]:
    out = set()
    def add_all(v):
        if isinstance(v, list):
            for x in v: out.add(str(x).strip().upper())
        elif isinstance(v, str):
            out.add(v.strip().upper())
    # mars
    m = cfg.get("mars", {})
    add_all((m.get("core_growth") or {}).get("tickers", []))
    add_all((m.get("moonshots")   or {}).get("tickers", []))
    for k in (m.get("satellites") or {}):
        out.add(k.upper()); 
        # ggf. explizite Kürzel (SU, VRT) → echte Ticker aus Schwellen nicht ableitbar
    # venus
    v = cfg.get("venus", {})
    add_all((v.get("sparplan")    or {}).get("tickers", []))
    add_all((v.get("add_on_dips") or {}).get("tickers", []))
    add_all((v.get("restpositions") or {}).get("tickers", []))
    # family – keine Einzelticker
    # Filter: plausible Ticker (Buchstaben, Punkt, Bindestrich)
    return {t for t in out if re.fullmatch(r"[A-Z0-9\.\-=]+", t)}

def tickers_from_portfolios(obj: dict) -> set[str]:
    out = set()
    for acc in obj.values():
        if not isinstance(acc, dict): continue
        for bucket in acc.values():
            if isinstance(bucket, dict):
                for t, _w in bucket.items():
                    out.add(str(t).strip().upper())
            elif isinstance(bucket, list):
                for t in bucket:
                    out.add(str(t).strip().upper())
    return out

def main():
    core  = set(load_txt(P_CORE))
    watch = set(load_txt(P_WATCH))

    # portfolios.json (falls vorhanden)
    port = {}
    if P_PORTF.exists():
        try: port = json.loads(P_PORTF.read_text(encoding="utf-8"))
        except: pass
    port_tickers = tickers_from_portfolios(port)

    # alerts_config.json
    cfg = {}
    if P_CFG.exists():
        try: cfg = json.loads(P_CFG.read_text(encoding="utf-8"))
        except: pass
    cfg_tickers = tickers_from_cfg(cfg)

    # Merge: Depot-nahe ins CORE, Rest ins WATCH (ohne Duplikate)
    new_core  = core  | port_tickers
    new_watch = (watch | cfg_tickers) - new_core

    changes = (new_core != core) or (new_watch != watch)
    dump_txt(P_CORE,  list(new_core))
    dump_txt(P_WATCH, list(new_watch))
    print(f"[auto-extend] core={len(new_core)} watch={len(new_watch)} changes={changes}")
    # Exit-Code 0 immer ok
if __name__ == "__main__":
    main()
