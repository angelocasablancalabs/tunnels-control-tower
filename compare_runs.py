#!/usr/bin/env python3
"""Confronto A/B shadow test — Grounding (A) vs Whitelist (B).

Legge i due snapshot prodotti dalle pipeline parallele e confronta, giorno per
giorno e per entrambi gli assi, stato, micro-stop tecnici e testo:

    A: public/traffic_data.json            (fetch_traffic.py, Google Search Grounding)
    B: public/traffic_data_whitelist.json  (fetch_traffic_whitelist.py, whitelist ufficiale)

Legenda:
    🟢 MATCH        stato identico e nessuna differenza testuale rilevante
    🟡 DIFF         stato identico, ma micro-stop o testo divergono
    ⚠️  DIVERGENCE  stato diverso tra le due fonti (l'informazione operativa cambia)

Uso:
    python compare_runs.py                # report completo
    python compare_runs.py --summary      # solo il riepilogo finale

Il confronto è informativo: l'exit code è 0 anche in presenza di divergenze, e
diventa 2 se uno dei due snapshot manca o non è leggibile.
"""

import argparse
import json
import re
import sys
import textwrap
from difflib import SequenceMatcher
from pathlib import Path

SOURCE_A = Path("public") / "traffic_data.json"
SOURCE_B = Path("public") / "traffic_data_whitelist.json"

LABEL_A = "A · Grounding"
LABEL_B = "B · Whitelist"

CORRIDORS = (("frejus", "FRÉJUS"), ("monte_bianco", "MONTE BIANCO"))

# Stesse finestre orarie riconosciute dalla UI (src/App.jsx: parseMicroStops).
TIME_RANGE_RE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-\u2013\u2014]\s*(\d{1,2})[:.](\d{2})")

TITLE_SIMILARITY_TARGET = 0.80
DETAILS_SIMILARITY_TARGET = 0.75
WIDTH = 78
INDENT = "      "

GREEN = "🟢 MATCH"
YELLOW = "🟡 DIFF"
RED = "⚠️  DIVERGENCE"


# ---------------------------------------------------------------------------
# Caricamento
# ---------------------------------------------------------------------------
def load_json(path):
    """Ritorna (dati, errore)."""
    if not path.exists():
        return None, f"file non trovato: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as err:
        return None, f"{path}: {err}"


def index_days(data):
    days = {}
    for day in (data or {}).get("days") or []:
        if isinstance(day, dict) and isinstance(day.get("date"), str) and day["date"].strip():
            days[day["date"].strip()] = day
    return days


# ---------------------------------------------------------------------------
# Normalizzazioni e metriche
# ---------------------------------------------------------------------------
def extract_ranges(text):
    """Estrae le fasce orarie 'HH:MM-HH:MM' (i micro-stop visti dalla timeline)."""
    ranges = []
    for match in TIME_RANGE_RE.finditer(text or ""):
        start_h, start_m = int(match.group(1)), int(match.group(2))
        end_h, end_m = int(match.group(3)), int(match.group(4))
        if (end_h, end_m) <= (start_h, start_m):
            continue
        ranges.append(f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}")
    return sorted(set(ranges))


def similarity(left, right):
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def corridor_payload(day, key):
    section = (day or {}).get(key) if day else None
    return section if isinstance(section, dict) else {}


def compare_corridor(day_a, day_b, key):
    a = corridor_payload(day_a, key)
    b = corridor_payload(day_b, key)

    status_a = str(a.get("status") or "").strip()
    status_b = str(b.get("status") or "").strip()
    micro_a = str(a.get("micro_stops") or "").strip()
    micro_b = str(b.get("micro_stops") or "").strip()
    title_a = str(a.get("title") or "").strip()
    title_b = str(b.get("title") or "").strip()
    details_a = str(a.get("details") or "").strip()
    details_b = str(b.get("details") or "").strip()

    ranges_a = extract_ranges(micro_a)
    ranges_b = extract_ranges(micro_b)
    title_ratio = similarity(title_a, title_b)
    details_ratio = similarity(details_a, details_b)

    status_match = status_a == status_b
    micro_match = ranges_a == ranges_b
    title_match = title_ratio >= TITLE_SIMILARITY_TARGET
    details_match = details_ratio >= DETAILS_SIMILARITY_TARGET

    if not status_match:
        verdict = RED
    elif not micro_match or not title_match or not details_match:
        verdict = YELLOW
    else:
        verdict = GREEN

    return {
        "verdict": verdict,
        "status_match": status_match,
        "status_a": status_a or "—",
        "status_b": status_b or "—",
        "micro_match": micro_match,
        "micro_a": micro_a,
        "micro_b": micro_b,
        "ranges_a": ranges_a,
        "ranges_b": ranges_b,
        "title_a": title_a,
        "title_b": title_b,
        "title_ratio": title_ratio,
        "details_a": details_a,
        "details_b": details_b,
        "details_ratio": details_ratio,
        "title_match": title_match,
        "details_match": details_match,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def wrap_block(label, text, indent=INDENT):
    """Rende un'etichetta + testo andando a capo con rientro allineato."""
    if not text:
        return f"{indent}{label}: —"
    available = WIDTH - len(indent) - len(label) - 2
    wrapped = textwrap.wrap(text, width=max(available, 24)) or [""]
    lines = [f"{indent}{label}: {wrapped[0]}"]
    padding = " " * (len(indent) + len(label) + 2)
    lines.extend(f"{padding}{line}" for line in wrapped[1:])
    return "\n".join(lines)


def render_corridor(name, result):
    status_note = (
        f"status {result['status_a']}"
        if result["status_match"]
        else f"status A:{result['status_a']} ≠ B:{result['status_b']}"
    )
    lines = [f"   {name:<13} {result['verdict']} · {status_note}"]

    if result["verdict"] == GREEN:
        return lines

    if not result["micro_match"]:
        lines.append(wrap_block("micro-stop A", result["micro_a"] or "—"))
        lines.append(wrap_block("micro-stop B", result["micro_b"] or "—"))
        if result["ranges_a"] or result["ranges_b"]:
            lines.append(
                f"{INDENT}fasce       A: {', '.join(result['ranges_a']) or '—'}"
                f"   B: {', '.join(result['ranges_b']) or '—'}"
            )

    if not result["title_match"]:
        lines.append(f"{INDENT}titolo      similarità {result['title_ratio']:.0%}")
        lines.append(wrap_block("A", result["title_a"]))
        lines.append(wrap_block("B", result["title_b"]))

    if not result["details_match"]:
        lines.append(f"{INDENT}dettagli    similarità {result['details_ratio']:.0%}")
        lines.append(wrap_block("A", result["details_a"]))
        lines.append(wrap_block("B", result["details_b"]))

    return lines


def day_heading(day_date, day_a, day_b):
    weekday = ""
    for day in (day_a, day_b):
        if isinstance(day, dict) and day.get("day_name"):
            weekday = str(day["day_name"]).strip()
            break
    label = f"── {day_date}"
    if weekday:
        label += f" ({weekday})"
    label += " "
    return label + "─" * max(WIDTH - len(label), 3)


def collect_rows(days, days_a, days_b):
    """Costruisce una riga di confronto per giorno; result=None se il giorno manca."""
    rows = []
    for day_date in days:
        day_a = days_a.get(day_date)
        day_b = days_b.get(day_date)
        corridors = []
        for key, name in CORRIDORS:
            result = None
            if day_a is not None and day_b is not None:
                result = compare_corridor(day_a, day_b, key)
            corridors.append({"key": key, "name": name, "result": result})
        rows.append({"date": day_date, "day_a": day_a, "day_b": day_b, "corridors": corridors})
    return rows


def accumulate(summary, rows):
    for row in rows:
        for corridor in row["corridors"]:
            stats = summary[corridor["key"]]
            stats["total"] += 1
            result = corridor["result"]
            if result is None:
                # Giorno presente in un solo snapshot: non è un match.
                stats["verdicts"][RED] += 1
                continue
            stats["status"] += 1 if result["status_match"] else 0
            stats["micro"] += 1 if result["micro_match"] else 0
            stats["title"] += 1 if result["title_match"] else 0
            stats["verdicts"][result["verdict"]] += 1


def render_day(row, show_details=True):
    lines = [day_heading(row["date"], row["day_a"], row["day_b"])]
    if row["day_a"] is None:
        lines.append(f"   ⚠️  giorno assente in {LABEL_A}: nessun confronto possibile")
    if row["day_b"] is None:
        lines.append(f"   ⚠️  giorno assente in {LABEL_B}: nessun confronto possibile")
    if not show_details:
        return lines

    for corridor in row["corridors"]:
        if corridor["result"] is None:
            lines.append(f"   {corridor['name']:<13} {RED} · snapshot incompleto")
        else:
            lines.extend(render_corridor(corridor["name"], corridor["result"]))
    return lines


def render_header(data_a, data_b, days):
    return [
        "═" * WIDTH,
        "  A/B SHADOW TEST — Google Search Grounding (A) vs Whitelist ufficiale (B)",
        "═" * WIDTH,
        f"  {LABEL_A:<22} {SOURCE_A}",
        f"  {LABEL_B:<22} {SOURCE_B}",
        f"  ultimo aggiornamento    A: {(data_a or {}).get('last_updated') or '—'}"
        f"   B: {(data_b or {}).get('last_updated') or '—'}",
        f"  giorni confrontati      {len(days)}",
        "",
        f"  legenda  {GREEN} = allineati · {YELLOW} = stesso stato, testo/micro-stop diversi"
        f" · {RED} = stato diverso",
        "",
    ]


def render_summary(summary, days_count):
    lines = ["", "═" * WIDTH, "  RIEPILOGO", "═" * WIDTH]

    for key, name in CORRIDORS:
        stats = summary[key]
        total = stats["total"] or 1
        lines.append(
            f"  {name:<13} status {stats['status']}/{stats['total']} · "
            f"micro-stop {stats['micro']}/{stats['total']} · "
            f"titoli allineati {stats['title']}/{stats['total']} "
            f"({stats['title'] / total:.0%})"
        )
        lines.append(
            f"  {'':<13} 🟢 {stats['verdicts'][GREEN]} · "
            f"🟡 {stats['verdicts'][YELLOW]} · ⚠️  {stats['verdicts'][RED]}"
        )

    lines.append("")
    for key, name in CORRIDORS:
        stats = summary[key]
        lines.append(
            f"  {stats['status']}/{stats['total']} giorni con stato identico su {name.title()}"
        )

    differences = sum(
        summary[key]["verdicts"][YELLOW] + summary[key]["verdicts"][RED]
        for key, _ in CORRIDORS
    )
    if differences:
        unit = "divergenza" if differences == 1 else "divergenze"
        lines.append(
            f"\n  Nota: {differences} {unit} su {days_count * 2} celle corridoio-giorno."
        )
        lines.append("  Le divergenze sono informative: la decisione di switch resta manuale.")
    else:
        lines.append(f"\n  Nessuna divergenza su {days_count * 2} celle corridoio-giorno.")

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Confronto giorno per giorno tra traffic_data.json (grounding) e "
        "traffic_data_whitelist.json (whitelist)."
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="stampa solo il riepilogo finale, senza il dettaglio giorno per giorno",
    )
    return parser.parse_args(argv)


def run(argv=None):
    args = parse_args(argv)

    data_a, error_a = load_json(SOURCE_A)
    data_b, error_b = load_json(SOURCE_B)

    for error in (error_a, error_b):
        if error:
            print(f"❌ {error}", file=sys.stderr)

    if data_a is None or data_b is None:
        print(
            "\nServono entrambi gli snapshot:\n"
            f"  python fetch_traffic.py            → {SOURCE_A}\n"
            f"  python fetch_traffic_whitelist.py  → {SOURCE_B}",
            file=sys.stderr,
        )
        return 2

    days_a = index_days(data_a)
    days_b = index_days(data_b)
    days = sorted(set(days_a) | set(days_b))

    if not days:
        print("❌ Nessun giorno trovato nei due snapshot.", file=sys.stderr)
        return 2

    rows = collect_rows(days, days_a, days_b)

    summary = {
        key: {
            "total": 0,
            "status": 0,
            "micro": 0,
            "title": 0,
            "verdicts": {GREEN: 0, YELLOW: 0, RED: 0},
        }
        for key, _ in CORRIDORS
    }
    accumulate(summary, rows)

    print("\n".join(render_header(data_a, data_b, days)))

    if args.summary:
        for row in rows:
            print("\n".join(render_day(row, show_details=False)))
    else:
        for row in rows:
            print("\n".join(render_day(row)))
            print()

    print("\n".join(render_summary(summary, len(days))))
    return 0


if __name__ == "__main__":
    sys.exit(run())
