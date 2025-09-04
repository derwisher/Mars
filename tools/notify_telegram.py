# tools/notify_telegram.py
import os, json, pathlib, sys, time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERTS = ROOT / "data" / "alerts_out.json"

BOT  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

def has_secrets():
    return bool(BOT and CHAT)

def load_json(p: pathlib.Path):
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def short_lines(section_name, items):
    """
    Baut kurze 6-Zeilen-Snippets:
    Zeile 1: Section
    Zeile 2-? pro Alert komprimiert
    """
    out = []
    out.append(f"*{section_name}*")
    for a in items[:4]:  # max. 4 Stück pro Nachricht
        tkr   = a.get("ticker","?")
        topic = a.get("topic", tkr)
        score = a.get("score", 0)
        conf  = a.get("confidence", 1)
        ab    = a.get("variants","")
        # A/B sehr knapp:
        if isinstance(ab, dict):
            varA = ab.get("A","")
            varB = ab.get("B","")
            abtxt = ""
            if varA:
                abtxt += f"A:{varA} "
            if varB:
                abtxt += f"B:{varB}"
        else:
            abtxt = ""
        line = f"• {topic} — Score {score} | Conf {conf}"
        if abtxt:
            line += f"\n  {abtxt}"
        out.append(line)
    return "\n".join(out)

def send(text):
    if not has_secrets():
        return
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    data = {
        "chat_id": CHAT,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    payload = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()

def main():
    data = load_json(ALERTS)
    if not data:
        return  # nichts zu senden

    # Struktur aus run_alerts.py: {"Mars":{"alerts":[...]}, "Venus":{"alerts":[...]}, "family":{"alerts":[...]}}
    sections = []
    for key in ("Mars","Venus","family"):
        sec = data.get(key, {})
        items = sec.get("alerts", [])
        if items:
            title = "Family" if key == "family" else key
            sections.append((title, items))

    if not sections or not has_secrets():
        return

    # Für jede Section eine kurze Nachricht (max. 6 Zeilen)
    for title, items in sections:
        msg = f"🚨 *Execution Alert* — {time.strftime('%Y-%m-%d %H:%M', time.gmtime())} UTC\n"
        msg += short_lines(title, items)
        # Kürzen falls überlang (Telegram Limit)
        if len(msg) > 3900:
            msg = msg[:3900] + " …"
        try:
            send(msg)
            time.sleep(0.7)
        except Exception:
            # niemals den Workflow hart fehlschlagen lassen
            continue

if __name__ == "__main__":
    main()
