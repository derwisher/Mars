#!/usr/bin/env python3
import os
import json
from datetime import datetime
from pathlib import Path
import random

# === Konfiguration ===
DATA_DIR = Path("data")
TOPPRIOR_FILE = DATA_DIR / "universe_topprior.txt"
CORE_FILE = DATA_DIR / "universe_core.txt"

# === Hilfsfunktionen ===
def load_universe(file_path):
    tickers = []
    if file_path.exists():
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # nur Ticker, Kommentare hinten abschneiden
                tickers.append(line.split()[0])
    return tickers

def rotate_universe(universe, slots=4, max_n=200):
    """Teilt Universe in Slots und zieht max. n Ticker pro Lauf"""
    if not universe:
        return []

    # Shuffle für Rotation
    random.shuffle(universe)

    # Slots: gleichmäßige Aufteilung
    slot_size = max(1, len(universe) // slots)
    chosen = universe[:slots * slot_size]

    # Begrenzung max_n
    return chosen[:max_n]

# === Umgebungsvariablen ===
SLOTS = int(os.getenv("ROTATION_SLOTS", "4"))
MAX_N = int(os.getenv("MAX_UNIVERSE", "200"))

# === Universe laden ===
tickers_top = load_universe(TOPPRIOR_FILE)
tickers_core = load_universe(CORE_FILE)

universe = tickers_top + tickers_core
universe = list(set(universe))  # Duplikate entfernen

# === Rotation anwenden ===
selected = rotate_universe(universe, slots=SLOTS, max_n=MAX_N)

# === Dummy-Scores (Platzhalter für echte Analyse/Scoring) ===
alerts = []
for t in selected:
    alerts.append({
        "ticker": t,
        "score": round(random.uniform(0.2, 0.9), 4),
        "as_of": datetime.utcnow().isoformat() + "Z"
    })

# === Output als JSON ===
print(json.dumps({"alerts_today": alerts}, indent=2))
