# tools/auto_extend.py
import pathlib, json

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def read_lines(p):
    try:
        return [ln.strip().upper() for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []

def main(max_n=5000):
    # Portfolios (JSON)
    ports = json.loads((DATA/"portfolios.json").read_text(encoding="utf-8"))
    mars  = ports.get("mars",{})
    venus = ports.get("venus",{})
    ticks = set(mars.get("active",[]) + mars.get("inactive",[]) +
                venus.get("active",[]) + venus.get("inactive",[]))

    # # Seeds & Radarlisten (NEU: ex130.txt)
    for fname in ["universe_core.txt","universe_watch.txt","universe_all.txt","extended_universe.txt, "ex130.txt"    # <--- Ex-130 wird automatisch gemerged"]:
        ticks.update(read_lines(DATA/fname))

    # Ignore
    ignore = set(read_lines(DATA/"universe_ignore.txt"))
    final = [t for t in sorted(ticks) if t not in ignore][:max_n]

    out = DATA/"extended_universe.txt"
    out.write_text("\n".join(final)+"\n", encoding="utf-8")
    print(f"extended_universe.txt rebuilt with {len(final)} tickers")

if __name__ == "__main__":
    main()
