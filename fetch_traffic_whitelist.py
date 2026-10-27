#!/usr/bin/env python3
"""Pipeline "whitelist" per i dati di traffico transalpino (A/B shadow test).

Gemella sperimentale di ``fetch_traffic.py``: invece di delegare la ricerca a
Google Search Grounding, scarica direttamente le fonti ufficiali in whitelist
(pagine HTML dei concessionari + PDF dei programmi di chiusura), le invia in
un'unica richiesta multimodale a Gemini 3.8 Flash e scrive un contratto JSON
identico a quello di produzione.

Nessun tool di ricerca viene abilitato: il modello vede esclusivamente i
documenti allegati. Nessun file di produzione viene toccato.

Uso:
    python fetch_traffic_whitelist.py             # pipeline completa
    python fetch_traffic_whitelist.py --dry-run   # solo ingestione fonti (nessuna chiamata API)

Output:
    public/traffic_data_whitelist.json   (letto dal dev server: .env.local -> VITE_DATA_FILE)
    traffic_data_whitelist.json          (copia di backup in root)

La chiamata al modello usa la superficie **Interactions API** (AGENTS.md §4.9):
``client.interactions.create(...)`` + ``.output_text``, non ``generate_content``.
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from google import genai
from google.genai import interactions

# Windows: la console usa cp1252 per default, e gli emoji dei messaggi di stato
# sollevano UnicodeEncodeError. Forziamo UTF-8 su stdout/stderr quando possibile.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and getattr(_stream, "encoding", "").lower() != "utf-8":
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

load_dotenv()

MODEL_ID = "gemini-3.8-flash"
DAYS_COUNT = 10
STATUSES = ("REGOLARE", "BLOCCO_TOTALE", "RESTRIZIONE")

OUTPUT_PUBLIC = Path("public") / "traffic_data_whitelist.json"
OUTPUT_ROOT = Path("traffic_data_whitelist.json")

HTTP_TIMEOUT = 30
# Limiti di sicurezza: il testo HTML viene troncato per fonte, i PDF sono capiti
# sia singolarmente sia nel totale per non sfondare il payload della richiesta.
MAX_TEXT_CHARS = 20_000
MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_TOTAL_PDF_BYTES = 24 * 1024 * 1024
MAX_PDFS = 6
MAX_PDFS_PER_SOURCE = 2

TRUNCATION_MARK = "\n[... testo troncato ...]"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Whitelist delle fonti ufficiali (nessuna ricerca web, nessun dominio terzo).
#   kind="html" -> si estrae il testo della pagina
#   kind="pdf"  -> la pagina è un hub: si estraggono i link ai PDF del periodo
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "key": "sftrf_t4",
        "label": "SFTRF — Traforo del Fréjus (T4): alternat e fermetures",
        "url": "https://www.sftrf.fr/le-tunnel/alternat-et-fermetures/",
        "kind": "html",
    },
    {
        "key": "sftrf_a43",
        "label": "SFTRF — A43 Maurienne: travaux et fermetures",
        "url": "https://www.sftrf.fr/autoroute/travaux-et-fermetures/",
        "kind": "html",
    },
    {
        "key": "sitaf_t4",
        "label": "SITAF — T4 Fréjus: chiusure programmate (PDF mensile)",
        "url": "https://www.sitaf.it/chiusure-programmate/",
        "kind": "pdf",
        "pdf_pattern": r"programma[-_ ]?chiusure[^/]*\.pdf",
    },
    {
        "key": "sitaf_a32",
        "label": "SITAF — A32 Autostrada: chiusure programmate (PDF mensile)",
        "url": "https://www.sitaf.it/chiusure-programmate-a32/",
        "kind": "pdf",
        "pdf_pattern": r"(?:aggiornamento[-_ ]?)?chiusure[^/]*\.pdf",
    },
    {
        "key": "tmb_geie",
        "label": "TMB-GEIE — Monte Bianco: interruzioni e previsioni (PDF)",
        "url": "https://www.tunnelmb.net/it-IT/interruzioni-e-previsioni",
        "kind": "pdf",
        "pdf_pattern": r"(?:chiusur|programmat|calendario)[^/]*\.pdf",
    },
    {
        "key": "atmb",
        "label": "ATMB — A40 / RN205: calendario notti di chiusura",
        "url": (
            "https://www.atmb.com/info-trafic-a40-rn205/"
            "calendrier-des-nuits-de-fermeture-sur-la40-et-la-rn205/"
        ),
        "kind": "html",
    },
    {
        "key": "sav_a5",
        "label": "SAV — A5: chiusure programmate",
        "url": "https://www.sav-a5.it/chiusure-programmate/",
        "kind": "html",
    },
]


# ---------------------------------------------------------------------------
# Rete / decodifica
# ---------------------------------------------------------------------------
def _headers(accept):
    return {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "it-IT,it;q=0.9,fr-FR;q=0.8,fr;q=0.8,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def fetch_bytes(url, *, accept=None, max_bytes=MAX_PDF_BYTES):
    """Scarica ``url`` in memoria. Ritorna (bytes, content_type, final_url, truncated)."""
    accept = accept or (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    )
    request = Request(url, headers=_headers(accept))
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(max_bytes + 1)
        content_type = response.headers.get("Content-Type", "") or ""
        final_url = response.geturl() or url
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    return raw, content_type, final_url, truncated


def decode_html(raw, content_type):
    charset = ""
    match = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
    if match:
        charset = match.group(1)
    for candidate in (charset, "utf-8", "latin-1"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# HTML -> testo pulito
# ---------------------------------------------------------------------------
class _HtmlTextExtractor(HTMLParser):
    """Estrae testo leggibile scartando script, style, navigazione e footer."""

    _SKIP = {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "nav",
        "header",
        "footer",
        "form",
        "iframe",
        "canvas",
        "aside",
    }
    _BREAK = {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "tr",
        "td",
        "th",
        "table",
        "section",
        "article",
        "main",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "dt",
        "dd",
        "blockquote",
        "pre",
        "hr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self._chunks.append("\n")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._BREAK and not self._skip_depth:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._SKIP:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag in self._BREAK and not self._skip_depth:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth or not data.strip():
            return
        self._chunks.append(data)

    def text(self):
        return "".join(self._chunks)


class _LinkCollector(HTMLParser):
    """Raccoglie le coppie (href, testo ancora) dalla pagina hub."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a" or self._href is not None:
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def html_to_text(markup):
    """Converte markup HTML in testo normalizzato, riga per riga."""
    parser = _HtmlTextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        # HTML malformato: teniamo il testo raccolto fin qui.
        pass

    lines = []
    for line in parser.text().splitlines():
        collapsed = re.sub(r"[ \t\u00a0\u2007\u202f]+", " ", line).strip()
        if collapsed:
            lines.append(collapsed)

    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return "\n".join(deduped)


def truncate_text(text, limit=MAX_TEXT_CHARS):
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + TRUNCATION_MARK, True


# ---------------------------------------------------------------------------
# Selezione dei PDF del periodo corrente
# ---------------------------------------------------------------------------
_MONTH_TOKENS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "decembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _detect_year(text):
    years = [int(year) for year in re.findall(r"(20\d{2})", text)]
    return max(years) if years else 0


def _recency_score(text):
    """Punteggio grossolano anno*100+mese per ordinare i PDF dal più recente."""
    score = _detect_year(text) * 100
    months = [index for token, index in _MONTH_TOKENS.items() if token in text]
    for match in re.finditer(r"(20\d{2})[-_/](\d{1,2})", text):
        months.append(int(match.group(2)))
    if months:
        score += min(max(months), 12)
    return score


def select_pdf_links(anchors, base_url, pattern=None, limit=MAX_PDFS_PER_SOURCE):
    """Filtra i link PDF dell'hub: si scartano i documenti di anni passati.

    Ordine di priorità: prima i PDF che rispettano il pattern della fonte, poi i
    più recenti per anno/mese. Ritorna (url selezionati, note di log).
    """
    candidates = []
    notes = []
    seen = set()

    for href, label in anchors:
        href = (href or "").strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "#")):
            continue
        target = urljoin(base_url, href)
        if target in seen:
            continue

        parsed = urlparse(target)
        haystack = f"{parsed.path} {parsed.query} {label}".lower()
        if ".pdf" not in haystack:
            continue
        seen.add(target)

        candidates.append(
            {
                "url": target,
                "year": _detect_year(haystack),
                "score": _recency_score(haystack),
                "matches_pattern": bool(pattern and re.search(pattern, haystack)),
            }
        )

    if not candidates:
        return [], notes

    # Un PDF datato 2025 su un hub aggiornato al 2026 è rumore: si scarta, a meno
    # che l'hub non offra esclusivamente documenti degli anni precedenti.
    current_year = datetime.now().year
    fresh = [item for item in candidates if item["year"] >= current_year]
    if fresh:
        for item in candidates:
            if item["year"] < current_year:
                notes.append(f"PDF di un anno precedente ignorato: {item['url']}")
        candidates = fresh

    candidates.sort(key=lambda item: (not item["matches_pattern"], -item["score"]))
    return [item["url"] for item in candidates[:limit]], notes


# ---------------------------------------------------------------------------
# Ingestione
# ---------------------------------------------------------------------------
def ingest_source(source):
    """Scarica una fonte. Ritorna (testo_html | None, [pdf_bytes], note di log)."""
    notes = []
    url = source["url"]
    raw, content_type, final_url, truncated = fetch_bytes(url)
    markup = decode_html(raw, content_type)
    if truncated:
        notes.append(f"{source['key']}: HTML troncato a {MAX_PDF_BYTES} byte")

    text, cut = truncate_text(html_to_text(markup))
    if cut:
        notes.append(f"{source['key']}: testo troncato a {MAX_TEXT_CHARS} caratteri")

    if source["kind"] != "pdf":
        return text, [], notes

    collector = _LinkCollector()
    try:
        collector.feed(markup)
        collector.close()
    except Exception:
        pass

    links, link_notes = select_pdf_links(collector.anchors, final_url, source.get("pdf_pattern"))
    notes.extend(link_notes)
    if not links:
        notes.append(f"{source['key']}: nessun link PDF trovato, uso il testo dell'hub")
        return text, [], notes

    documents = []
    for link in links:
        try:
            pdf_raw, _, _, pdf_truncated = fetch_bytes(
                link,
                accept="application/pdf,*/*;q=0.8",
                max_bytes=MAX_PDF_BYTES,
            )
        except (HTTPError, URLError, OSError, ValueError) as err:
            notes.append(f"{source['key']}: PDF non scaricato ({link}): {err}")
            continue

        if not pdf_raw.lstrip()[:5].startswith(b"%PDF"):
            notes.append(f"{source['key']}: risposta non PDF, scartata ({link})")
            continue
        if pdf_truncated:
            notes.append(f"{source['key']}: PDF troncato a {MAX_PDF_BYTES} byte ({link})")

        documents.append(pdf_raw)
        notes.append(f"{source['key']}: PDF acquisito {len(pdf_raw) // 1024} kB da {link}")

    return text, documents, notes


def ingest_sources():
    """Ingerisce tutte le fonti, proseguendo sulle altre in caso di errore."""
    html_blocks = []
    pdf_documents = []
    total_pdf_bytes = 0

    for source in SOURCES:
        print(f"📥 {source['label']}")
        try:
            text, documents, notes = ingest_source(source)
        except (HTTPError, URLError, OSError, ValueError) as err:
            print(f"   ⚠️ Fonte non disponibile: {err}")
            continue
        except Exception as err:  # rete/parsing imprevisti: si prosegue
            print(f"   ⚠️ Fonte non disponibile: {type(err).__name__}: {err}")
            continue

        for note in notes:
            print(f"   · {note}")

        if text and text.strip():
            html_blocks.append({"label": source["label"], "url": source["url"], "text": text})
            print(f"   ✓ testo utile: {len(text)} caratteri")
        elif source["kind"] == "html":
            print("   ⚠️ Nessun testo utile estratto dalla pagina")

        for document in documents:
            if len(pdf_documents) >= MAX_PDFS:
                print(f"   ⚠️ Limite di {MAX_PDFS} PDF raggiunto, documento ignorato")
                break
            if total_pdf_bytes + len(document) > MAX_TOTAL_PDF_BYTES:
                print("   ⚠️ Limite totale byte PDF raggiunto, documento ignorato")
                break
            pdf_documents.append({"label": source["label"], "url": source["url"], "data": document})
            total_pdf_bytes += len(document)

    return html_blocks, pdf_documents


# ---------------------------------------------------------------------------
# Prompt operativo (stessa logica di dispatch e stesso contratto JSON di produzione)
# ---------------------------------------------------------------------------
def build_prompt(today_str, last_updated):
    return f"""
    Sei il Direttore di Centrale Operativa Logistica per il trasporto pesante transalpino Italia - Francia.
    Oggi è: {today_str}.

    PROFILO MEZZO ESCLUSIVO:
    - Veicolo Pesante / Bilico 5 assi standard 40-44t (Frigo, Telonato, Box - H=4.00m, L=16.5m).
    - Merci ordinarie e deperibili (ESCLUSO ADR, ESCLUSO convogli/trasporti eccezionali, NO furgoni <3.5t).
    - Standard Euro 6.

    FONTI UFFICIALI IN WHITELIST — SOLO I DOCUMENTI ALLEGATI:
    In questa richiesta NON hai alcuno strumento di ricerca web. Analizza esclusivamente i documenti
    allegati qui sotto, scaricati dai portali ufficiali dei concessionari (ogni blocco riporta la fonte
    e l'URL di provenienza). Non citare informazioni che non compaiano nei documenti.
    - SFTRF / APRR (Traforo Fréjus, A43 & T4): sftrf.fr, aprr.fr.
      Cerca ESPLICITAMENTE le chiusure programmate per manutenzione sulla tratta A43 Maurienne
      (Orelle, Saint-Michel-de-Maurienne, Le Freney, viaduc du Charmaix) e, per OGNI chiusura trovata,
      VERIFICA se la deviazione accompagnatoria (tipicamente RD 1006 o rete locale) è aperta ai mezzi
      pesanti 40-44t oppure è interdetta ai PL (limite >3.5t / 7.5t).
    - SITAF (A32 / T4): sitaf.it.
      Cerca le chiusure notturne delle tratte Susa-Oulx, Bussoleno e delle gallerie, e VERIFICA se le
      deviazioni su SS24 / SS335 ammettono mezzi da 44t o impongono limiti di peso/sagoma.
    - TMB-GEIE & ATMB (Monte Bianco, A40, RN205): tunnelmb.net, atmb.com.
      Cerca chiusure notturne, calendari di senso unico alternato e cantieri su Tunnel du Vuache,
      Rampa Égratz, Les Chavants.
    - Asse A5: sav-a5.it (Viadotto Arnad, raccordo Gran San Bernardo).
      NOTA: le fonti di emergenza nazionale (Bison Futé, CCISS) non fanno parte della whitelist e non
      sono allegate: non ipotizzare eventi non documentati.

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

    COSA CERCARE ED ESTRARRE PER I PROSSIMI 10 GIORNI (da oggi {today_str} ai successivi 9 giorni, esattamente 10 giorni consecutivi a scorrimento):
    0. NON limitarti a cercare "blocchi": un cantiere con deviazione PL aperta è un evento da pubblicare
       come RESTRIZIONE, non da omettere. Ometterlo è un errore operativo grave.
    1. Tutte le chiusure notturne e diurne dei Trafori (Monte Bianco TMB e Fréjus T4).
    2. Tutti i cantieri e le chiusure autostradali di adduzione: A43 (Orelle, Charmaix,
       Saint-Michel-de-Maurienne, Le Freney), A40 (Vuache), A32 (tratte Susa-Oulx, Bussoleno), RN205,
       A5 (Arnad) — con valutazione della deviazione: aperta ai PL = RESTRIZIONE; interdetta ai PL o
       assente = BLOCCO_TOTALE.
    3. TUTTE le micro-chiusure tecniche del Fréjus (stop di 45 min per posa cantiere Tube 1 dalle 22:30 alle 23:15 e dalle 04:30 alle 05:15).
    4. Se un giorno non presenta NESSUN evento (né blocchi, né deviazioni, né senso unico alternato, né micro-stop), imposta lo status su 'REGOLARE'.

    VINCOLO DI VERIDICITÀ: se una fonte attesa non è presente tra gli allegati, NON inventare eventi e
    NON dedurre chiusure non documentate. Se un documento è in lingua francese, riporta comunque i campi
    testuali in italiano.

    Restituisci ESCLUSIVAMENTE un blocco JSON valido con questa struttura esatta:
    {{
      "last_updated": "{last_updated}",
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


def build_input_parts(prompt, html_blocks, pdf_documents):
    """Costruisce l'input multimodale: prompt + PDF binari + testi HTML consolidati."""
    parts = [interactions.TextContent(text=prompt)]

    for index, document in enumerate(pdf_documents, start=1):
        parts.append(
            interactions.TextContent(
                text=(
                    f"### DOCUMENTO PDF {index}/{len(pdf_documents)} — {document['label']}\n"
                    f"URL: {document['url']}\n"
                    "Il contenuto del PDF è allegato subito dopo questo blocco."
                )
            )
        )
        parts.append(
            interactions.DocumentContent(
                data=base64.b64encode(document["data"]).decode("ascii"),
                mime_type="application/pdf",
            )
        )

    if html_blocks:
        parts.append(
            interactions.TextContent(
                text=(
                    "### TESTI HTML CONSOLIDATI — ESTRATTI DELLE PAGINE UFFICIALI\n"
                    f"({len(html_blocks)} pagine, testo pulito da script/style/navigazione/footer)"
                )
            )
        )
        for block in html_blocks:
            parts.append(
                interactions.TextContent(
                    text=f"### FONTE: {block['label']}\nURL: {block['url']}\n\n{block['text']}"
                )
            )

    return parts


# ---------------------------------------------------------------------------
# Chiamata al modello (Interactions API, nessun tool di ricerca)
# ---------------------------------------------------------------------------
def describe_input(parts):
    text_chars = 0
    documents = 0
    document_bytes = 0
    for part in parts:
        if isinstance(part, interactions.TextContent):
            text_chars += len(part.text or "")
        elif isinstance(part, interactions.DocumentContent):
            documents += 1
            document_bytes += len(base64.b64decode(part.data or ""))
    return text_chars, documents, document_bytes


def call_model(parts):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY non trovata! Inseriscila nel file .env")

    client = genai.Client(api_key=api_key)

    # Nessun tools=: la whitelist non usa Google Search Grounding (solo documenti allegati).
    interaction = client.interactions.create(
        model=MODEL_ID,
        input=parts,
        generation_config=interactions.GenerationConfig(temperature=0.1),
    )

    text = getattr(interaction, "output_text", None)
    if not text:
        raise ValueError("Risposta del modello priva di output_text")
    return text


# ---------------------------------------------------------------------------
# Parsing e validazione del contratto
# ---------------------------------------------------------------------------
def strip_code_fences(raw_text):
    text = (raw_text or "").strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()
    return text


def validate_payload(data):
    """Valida il contratto: 10 giorni, due corridoi, tassonomia di stato ammessa."""
    if not isinstance(data, dict):
        raise ValueError("Il JSON radice non è un oggetto")

    days = data.get("days")
    if not isinstance(days, list):
        raise ValueError("Risposta JSON priva della chiave 'days'")
    if len(days) != DAYS_COUNT:
        raise ValueError(f"'days' contiene {len(days)} giorni invece di {DAYS_COUNT}")

    for index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            raise ValueError(f"Giorno {index}: elemento non oggetto")
        if not isinstance(day.get("date"), str) or not day["date"].strip():
            raise ValueError(f"Giorno {index}: campo 'date' mancante")
        for corridor in ("frejus", "monte_bianco"):
            section = day.get(corridor)
            if not isinstance(section, dict):
                raise ValueError(f"Giorno {index}: sezione '{corridor}' assente")
            status = section.get("status")
            if status not in STATUSES:
                raise ValueError(
                    f"Giorno {index}/{corridor}: status '{status}' fuori tassonomia {STATUSES}"
                )
            for field in ("title", "details", "micro_stops"):
                if not isinstance(section.get(field, ""), str):
                    raise ValueError(f"Giorno {index}/{corridor}: campo '{field}' non testuale")

    quick_status = data.get("quick_status")
    if not isinstance(quick_status, dict) or not all(
        isinstance(quick_status.get(key), str)
        for key in ("frejus_next_block", "monte_bianco_next_block")
    ):
        print("   ⚠️ 'quick_status' assente o incompleto: il flag resta vuoto")
        data["quick_status"] = {
            "frejus_next_block": str((quick_status or {}).get("frejus_next_block", "") or ""),
            "monte_bianco_next_block": str((quick_status or {}).get("monte_bianco_next_block", "") or ""),
        }

    if not isinstance(data.get("last_updated"), str) or not data["last_updated"].strip():
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    return data


def parse_payload(raw_text):
    text = strip_code_fences(raw_text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ValueError(f"JSON non valido: {err}") from err
    return validate_payload(data)


# ---------------------------------------------------------------------------
# Scrittura
# ---------------------------------------------------------------------------
def write_payload(data):
    """Scrive l'output in public/ e la copia di backup in root, in modo atomico."""
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    OUTPUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)

    for target in (OUTPUT_PUBLIC, OUTPUT_ROOT):
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)
        print(f"   ✓ scritto {target} ({len(payload.encode('utf-8')) // 1024} kB)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def request_payload(parts):
    max_retries = 3
    retry_delay = 10

    for attempt in range(1, max_retries + 1):
        try:
            print(f"📡 Chiamata Gemini 3.8 Flash (tentativo {attempt}/{max_retries})...")
            raw_text = call_model(parts)
            return parse_payload(raw_text)
        except Exception as err:
            print(f"⚠️ Tentativo {attempt} non riuscito: {err}")
            if attempt < max_retries:
                print(f"⏳ Attesa {retry_delay}s prima del nuovo tentativo...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

    raise RuntimeError("Chiamata al modello non riuscita")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Pipeline whitelist (senza Google Search Grounding) per "
            "public/traffic_data_whitelist.json"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scarica e riassume le fonti senza chiamare l'API né scrivere file",
    )
    return parser.parse_args(argv)


def run(argv=None):
    args = parse_args(argv)
    today_str = datetime.now().strftime("%Y-%m-%d")
    last_updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    mode = "DRY-RUN (solo ingestione fonti)" if args.dry_run else "pipeline completa"
    print(f"🚦 Avvio pipeline whitelist — {mode} (Data: {today_str})...")
    print(f"🔗 Fonti ufficiali in whitelist: {len(SOURCES)} (HTML + PDF, nessuna ricerca web)")

    html_blocks, pdf_documents = ingest_sources()

    text_chars = sum(len(block["text"]) for block in html_blocks)
    pdf_bytes = sum(len(document["data"]) for document in pdf_documents)
    print("\n📊 Corpus acquisito:")
    print(f"   · pagine HTML utili: {len(html_blocks)}/{len(SOURCES)} ({text_chars} caratteri)")
    print(f"   · documenti PDF: {len(pdf_documents)} ({pdf_bytes // 1024} kB)")

    if not html_blocks and not pdf_documents:
        print("\n❌ Nessuna fonte disponibile: pipeline interrotta senza chiamare il modello.")
        return 1

    if args.dry_run:
        print("\n✅ Dry-run completato: nessuna chiamata API, nessun file scritto.")
        return 0

    prompt = build_prompt(today_str, last_updated)
    parts = build_input_parts(prompt, html_blocks, pdf_documents)
    prompt_chars, documents, documents_bytes = describe_input(parts)
    print(f"   · input multimodale: {prompt_chars} caratteri di testo, {documents} PDF ({documents_bytes // 1024} kB)")

    try:
        data = request_payload(parts)
    except Exception as err:  # credenziali, rete o contratto non valido
        first_line = str(err).strip().splitlines()[0] if str(err).strip() else "errore sconosciuto"
        print(f"\n❌ Pipeline interrotta: {type(err).__name__}: {first_line[:300]}")
        print("   Controlla GEMINI_API_KEY nel file .env e riprova.")
        return 1

    write_payload(data)

    print("\n✅ SUCCESSO! Aggiornato 'public/traffic_data_whitelist.json' dai documenti ufficiali in whitelist.")
    print(f"Giorni generati: {len(data['days'])}")
    print(f"Quick Status Fréjus: {data['quick_status']['frejus_next_block']}")
    print(f"Quick Status M.Bianco: {data['quick_status']['monte_bianco_next_block']}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
