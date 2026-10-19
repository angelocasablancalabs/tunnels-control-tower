import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

def main():
    try:
        with open("public/traffic_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        last_str = data.get("last_updated", "")
        last_dt = datetime.strptime(last_str, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Rome"))
        now_dt = datetime.now(ZoneInfo("Europe/Rome"))
        diff_min = (now_dt - last_dt).total_seconds() / 60
        print(f"Ultimo aggiornamento: {last_str} (fuso Roma), {diff_min:.1f} min fa")

        if diff_min < 100:
            print("Slot corrente già aggiornato (< 100 min fa). Salto recovery tick.")
            proceed = "false"
        else:
            print("Dati più vecchi di 100 min. Procedo con l'aggiornamento.")
            proceed = "true"
    except Exception as err:
        print(f"Attenzione lettura last_updated: {err}. Procedo per sicurezza.")
        proceed = "true"

    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"proceed={proceed}\n")
    print(f"Decisione gate: proceed={proceed}")

if __name__ == "__main__":
    main()
