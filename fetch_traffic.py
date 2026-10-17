import os
import json
import re
import sys
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Windows: la console usa cp1252 per default, e gli emoji dei messaggi di stato
# sollevano UnicodeEncodeError. Forziamo UTF-8 su stdout/stderr quando possibile.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and getattr(_stream, "encoding", "").lower() != "utf-8":
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY non trovata! Inseriscila nel file .env")

def run():
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"🚦 Avvio scansione con Google Search Grounding attivo (Data: {today_str})...")
    print("🔍 Ricerca approfondita su SITAF, SFTRF, TMB-GEIE, ATMB, SAV A5, Bison Futé...")

    prompt = f"""
    Sei il Direttore di Centrale Operativa Logistica per il trasporto pesante transalpino Italia - Francia.
    Oggi è: {today_str}.

    PROFILO MEZZO ESCLUSIVO:
    - Veicolo Pesante / Bilico 5 assi standard 40-44t (Frigo, Telonato, Box - H=4.00m, L=16.5m).
    - Merci ordinarie e deperibili (ESCLUSO ADR, ESCLUSO convogli/trasporti eccezionali, NO furgoni <3.5t).
    - Standard Euro 6.

    FONTI UFFICIALI DA ISPEZIONARE TRAMITE GOOGLE SEARCH (verifica mirata, non generica):
    - SFTRF / APRR (Traforo Fréjus, A43 & T4): sftrf.fr, aprr.fr.
      Cerca ESPLICITAMENTE le chiusure programmate per manutenzione sulla tratta A43 Maurienne
      (Orelle, Saint-Michel-de-Maurienne, Le Freney, viaduc du Charmaix) e, per OGNI chiusura trovata,
      VERIFICA se la deviazione accompagnatoria (tipicamente RD 1006 o rete locale) è aperta ai mezzi
      pesanti 40-44t oppure è interdetta ai PL (limite >3.5t / 7.5t).
    - SITAF (A32 / T4): sitaf.it.
      Cerca le chiusure notturne delle tratte Susa-Oulx, Bussoleno e delle gallerie, e VERIFICA se le
      deviazioni su SS24 / SS335 ammettono mezzi da 44t o impongono limiti di peso/sagoma.
    - TMB-GEIE & ATMB (Monte Bianco, A40, RN205): tunnelmb.net/it-IT/interruzioni-e-previsioni
      (calendari trimestrali ufficiali, chiusure totali notturne e sensi unici alternati TMB-GEIE), atmb.com.
      Cerca chiusure notturne, calendari di senso unico alternato e cantieri su Tunnel du Vuache,
      Rampa Égratz, Les Chavants.
    - Asse A5: sav-a5.it, ravspa.it (Viadotto Arnad, raccordo Gran San Bernardo)
    - Emergenze: bison-fute.gouv.fr, cciss.it

    TASSONOMIA OPERATIVA DI DISPATCH — CLASSIFICAZIONE OBBLIGATORIA PER IMPATTO SUL MEZZO:
    Il criterio NON è l'esistenza di un cantiere o di una chiusura fisica, ma la possibilità per un bilico
    frigo 5 assi 40-44t di completare il transito alpino.

    - BLOCCO_TOTALE: SOLO quando il transito transalpino è completamente impraticabile per i 40-44t.
      Esempi: chiusura totale del traforo senza alcun itinerario alternativo; chiusura autostradale in cui
      la deviazione è ESPLICITAMENTE vietata ai mezzi pesanti ("déviation interdite aux PL > 3.5t / 7.5t",
      passi alpini stretti non compatibili con 44t); sosta obbligatoria dei camion nelle aree di
      stoccaggio/regolazione (es. Rieu Sec) senza possibilità di proseguire.

    - RESTRIZIONE: OGNI VOLTA che il corridoio resta transitabile per i 40-44t, ma con penalità
      operative, ritardi o itinerari non standard. Esempi:
      * Tratta autostradale o galleria chiusa CON deviazione attiva autorizzata ai mezzi pesanti
        (es. "Chiusura notturna A43 galleria Orelle 21:00-06:00 con deviazione su RD 1006 aperta ai
        mezzi pesanti, +45/60 min"). Una chiusura fisica con detour PL aperto NON è mai un blocco totale.
      * Senso unico alternato.
      * Micro-stop tecnici (es. finestre posa/smontaggio cantiere Tube 1 Fréjus: 22:30-23:15 / 04:30-05:15).
      * Riduzioni di corsia o cantieri rilevanti che causano rallentamenti al transito pesante.
      In title e details indica SEMPRE esplicitamente la strada di deviazione (es. RD 1006, SS24, SS335)
      e il ritardo stimato (es. "+45/60 min").
      Per gli eventi RESTRIZIONE con deviazione attiva non usare formule a orario singolo tipo
      "fino alle 06:00" o "riapertura ore 06:00": scrivi sempre la fascia completa "HH:MM-HH:MM".

    FORMATO OBBLIGATORIO DELLA DURATA (in title e details):
      Quando indichi la durata totale di una chiusura o restrizione, NON usare MAI forme abbreviate
      ambigue come "(9h)" o "(8h)": a colpo d'occhio sembrano un orario di inizio ("alle 9:00").
      Scrivi SEMPRE la durata in forma esplicita in italiano: "(durata: X ore)" oppure
      "(durata: X ore e Y min)" quando ci sono i minuti.
      Esempi corretti:
      - "Blocco Mezzi Pesanti A43 Charmaix 03:30-12:30 (durata: 9 ore)"
      - "Blocco Notturno TMB 22:00-06:00 (durata: 8 ore)"

    - REGOLARE: SOLO quando autostrada e traforo scorrono normalmente, senza deviazioni obbligatorie,
      senza restrizioni di peso/velocità e senza micro-stop programmati.

    COSA CERCARE ED ESTRARRE PER I PROSSIMI 30 GIORNI (da oggi {today_str} a 30 giorni in avanti):
    0. NON limitarti a cercare "blocchi": un cantiere con deviazione PL aperta è un evento da pubblicare
       come RESTRIZIONE, non da omettere. Ometterlo è un errore operativo grave.
    1. Tutte le chiusure notturne e diurne dei Trafori (Monte Bianco TMB e Fréjus T4).
    2. Tutti i cantieri e le chiusure autostradali di adduzione: A43 (Orelle, Charmaix,
       Saint-Michel-de-Maurienne, Le Freney), A40 (Vuache), A32 (tratte Susa-Oulx, Bussoleno), RN205,
       A5 (Arnad) — con valutazione della deviazione: aperta ai PL = RESTRIZIONE; interdetta ai PL o
       assente = BLOCCO_TOTALE.
    3. TUTTE le micro-chiusure tecniche del Fréjus (stop di 45 min per posa cantiere Tube 1 dalle 22:30 alle 23:15 e dalle 04:30 alle 05:15).
    4. Se un giorno non presenta NESSUN evento (né blocchi, né deviazioni, né senso unico alternato, né micro-stop), imposta lo status su 'REGOLARE'.

    Restituisci ESCLUSIVAMENTE un blocco JSON valido con questa struttura esatta:
    {{
      "last_updated": "{datetime.now().strftime('%Y-%m-%d %H:%M')}",
      "quick_status": {{
        "frejus_next_block": "Sintesi del prossimo blocco imminente Asse Fréjus",
        "monte_bianco_next_block": "Sintesi del prossimo blocco imminente Asse Monte Bianco"
      }},
      "days": [
        {{
          "date": "YYYY-MM-DD",
          "day_name": "Lunedì / Martedì / ecc.",
          "is_today": true/false,
          "frejus": {{
            "status": "REGOLARE" | "BLOCCO_TOTALE" | "RESTRIZIONE",
            "title": "es. Transito Regolare | Chiusura notturna A43 Orelle 21:00-06:00 con deviazione RD 1006 aperta ai PL (+45/60 min) | Blocco Totale Rampa T4 03:30-12:30 (durata: 9 ore)",
            "details": "Dettaglio dell'evento: se RESTRIZIONE indicare sempre la deviazione (es. RD 1006, SS24, SS335), la sua praticabilità per i 40-44t e il ritardo stimato; se BLOCCO_TOTALE indicare il divieto ai PL o l'assenza di itinerario alternativo (es. Lavori viadotto Charmaix, stoccaggio obbligatorio Rieu Sec)",
            "micro_stops": "es. Stop tecnico 45m posa cantiere: 22:30-23:15 (oppure stringa vuota)"
          }},
          "monte_bianco": {{
            "status": "REGOLARE" | "BLOCCO_TOTALE" | "RESTRIZIONE",
            "title": "es. Transito Regolare | Chiusura notturna TMB 22:00-06:00 con deviazione PL aperta (+30/45 min) | Blocco Totale notturno 22:00-06:00 (durata: 8 ore)",
            "details": "Dettaglio (es. Manutenzione ordinaria volta TMB oppure Chiusura A40 Tunnel Vuache 20:30-06:00): indicare sempre se la deviazione ammette i 40-44t",
            "micro_stops": "es. Nessuno (oppure stringa vuota)"
          }}
        }}
      ]
    }}
    """

    client = genai.Client(api_key=API_KEY)

    # Abilitiamo Google Search Grounding ufficiale nell'SDK
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1
    )

    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
        config=config
    )

    raw_text = response.text.strip()
    
    # Pulizia sicura del JSON da eventuali marcatori markdown ```json ... ```
    if "```" in raw_text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        if match:
            raw_text = match.group(1)

    data = json.loads(raw_text)

    # Salviamo sia in public/ che nella root per sicurezza
    os.makedirs("public", exist_ok=True)
    with open("public/traffic_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ SUCCESSO! Aggiornato 'public/traffic_data.json' con dati completi da Google Search!")
    print(f"Giorni generati: {len(data['days'])}")
    print(f"Quick Status Fréjus: {data['quick_status']['frejus_next_block']}")
    print(f"Quick Status M.Bianco: {data['quick_status']['monte_bianco_next_block']}")

if __name__ == "__main__":
    run()