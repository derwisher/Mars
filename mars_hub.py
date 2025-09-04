#!/usr/bin/env python3
import os
import json
import random
from datetime import datetime
from pathlib import Path

# === Konfiguration ===
DATA_DIR = Path("data")
TOPPRIOR_FILE = DATA_DIR / "universe_topprior.txt"
CORE_FILE = DATA_DIR / "universe_core.txt"
WATCH_FILE = DATA_DIR / "universe_watch.txt"
IGNORE_FILE = DATA_DIR / "universe_ignore.txt"

# === Hilfsfunktion: Universen laden ===
def load_universe(file_path):
    tickers = []
    if file_path.exists():
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tickers.append(line.split()[0])  # nur Ticker nehmen
    return tickers

# === Rotation ===
def rotate_universe(universe, slots=4, max_n=200):
    """Teilt Universe in Slots und zieht max. n Ticker"""
    if not universe:
        return []
    random.shuffle(universe)
    slot_size = max(1, len(universe) // slots)
    chosen = universe[:slots * slot_size]
    return chosen[:max_n]

# === Umgebungsvariablen laden ===
SLOTS = int(os.getenv("ROTATION_SLOTS", "6"))
MAX_N = int(os.getenv("MAX_UNIVERSE", "200"))

# === Universe laden ===
tickers_top = load_universe(TOPPRIOR_FILE)
tickers_core = load_universe(CORE_FILE)
tickers_watch = load_universe(WATCH_FILE)
tickers_ignore = load_universe(IGNORE_FILE)

# Merge + Dedupe, aber Ignorierte raus
universe = list(set(tickers_top + tickers_core + tickers_watch) - set(tickers_ignore))

# === Rotation anwenden ===
selected = rotate_universe(universe, slots=SLOTS, max_n=MAX_N)

# === Dummy-Scores (Platzhalter für echte Analyse) ===
alerts = []
for t in selected:
    alerts.append({
        "ticker": t,
        "score": round(random.uniform(0.2, 0.9), 4),
        "as_of": datetime.utcnow().isoformat() + "Z"
    })

# === Output als JSON ===
print(json.dumps({"alerts_today": alerts}, indent=2))
