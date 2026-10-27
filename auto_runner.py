#!/usr/bin/env python3
"""Runner periodico del shadow test A/B — whitelist (B) contro grounding (A).

Esegue in sequenza, ogni intervallo configurabile:

    1. fetch_traffic_whitelist.py  → public/traffic_data_whitelist.json   (sorgente B)
    2. compare_runs.py             → confronto giorno per giorno con public/traffic_data.json (sorgente A)

L'output dei due script è mostrato in diretta nel terminale; un riepilogo
conciso (esiti, durate, messaggi chiave e blocco RIEPILOGO del comparatore)
viene accodato in ``logs/shadow_test.log``, così i run passati restano
consultabili anche dopo essere stati lontani dal terminale.

Uso:
    .venv\\Scripts\\python auto_runner.py               # ogni 3 ore (default)
    .venv\\Scripts\\python auto_runner.py --hours 6     # ogni 6 ore
    .venv\\Scripts\\python auto_runner.py --minutes 5   # ogni 5 minuti (test rapido)
    .venv\\Scripts\\python auto_runner.py --once        # un solo ciclo ed esce

Note operative:
    - I figli sono lanciati con ``sys.executable`` e con la radice del progetto
      come cwd: entrambi gli script usano percorsi relativi (``public/...``) e
      ``load_dotenv()``, quindi la cwd deve essere quella del repository.
    - Un passo fallito (per esempio la chiave API non valida) non interrompe il
      ciclo: il confronto gira comunque sull'ultimo snapshot B disponibile e
      l'anomalia finisce nel log.
    - ``--once`` esce con 0 solo se entrambi i passi riescono (utile in CI o
      come verifica a secco); in modalità loop l'uscita è 0 e avviene con Ctrl+C.
"""

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Windows: la console usa cp1252 per default e i caratteri di riquadro/emoji
# sollevano UnicodeEncodeError. Forziamo UTF-8 su stdout/stderr quando possibile
# (stesso accorgimento già adottato da fetch_traffic_whitelist.py).
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and getattr(_stream, "encoding", "").lower() != "utf-8":
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

BASE_DIR = Path(__file__).resolve().parent
FETCH_SCRIPT = BASE_DIR / "fetch_traffic_whitelist.py"
COMPARE_SCRIPT = BASE_DIR / "compare_runs.py"

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "shadow_test.log"

DEFAULT_HOURS = 3
WIDTH = 78

SOURCE_A = "public/traffic_data.json"
SOURCE_B = "public/traffic_data_whitelist.json"


@dataclass
class StepResult:
    """Esito di un singolo script figlio."""

    name: str
    code: int
    duration: float
    output: list


# ---------------------------------------------------------------------------
# Formattazione
# ---------------------------------------------------------------------------
def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rule(char="═"):
    return char * WIDTH


def format_duration(seconds):
    return f"{seconds:.1f}s"


def format_interval(seconds):
    """10800 → '3h', 300 → '5m', 90 → '1m 30s'."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Log storico
# ---------------------------------------------------------------------------
def append_log(lines):
    """Accoda righe già formattate al log, senza mai interrompere il ciclo."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as err:
        print(f"⚠️  Log non scrivibile ({LOG_FILE}): {err}", flush=True)


def extract_diff_summary(output):
    """Estrae il blocco RIEPILOGO prodotto da compare_runs.py (righe vuote escluse)."""
    for index, line in enumerate(output):
        if line.strip() == "RIEPILOGO":
            start = max(index - 1, 0)
            return [line for line in output[start:] if line.strip()]
    return []


def extract_highlights(output, limit=4):
    """Righe di errore/avviso degli script figli, per un log leggibile a distanza."""
    found = [line.strip() for line in output if line.strip().startswith(("❌", "⚠️"))]
    return found[:limit]


# ---------------------------------------------------------------------------
# Esecuzione di un singolo passo
# ---------------------------------------------------------------------------
def run_step(name, script):
    """Esegue lo script mostrandone l'output in diretta e ne restituisce l'esito."""
    started = time.monotonic()

    print(f"\n{rule()}")
    print(f"  ▶ {now_stamp()} · {name}")
    print(rule(), flush=True)

    if not script.exists():
        message = f"script non trovato: {script}"
        print(f"  ❌ {message}", flush=True)
        return StepResult(name, 1, 0.0, [f"❌ {message}"])

    env = os.environ.copy()
    # Senza questi due, l'output del figlio su pipe resta bufferizzato a blocchi
    # e la "diretta" nel terminale diventerebbe a scatti.
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    popen_kwargs = {
        "cwd": str(BASE_DIR),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "env": env,
    }
    # Gruppo di processi separato: con Ctrl+C il runner resta padrone della
    # chiusura e termina il figlio da sé, senza far stampare traceback a metà.
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen([sys.executable, str(script)], **popen_kwargs)
    except OSError as err:
        message = f"avvio non riuscito: {err}"
        print(f"  ❌ {message}", flush=True)
        return StepResult(name, 1, time.monotonic() - started, [f"❌ {message}"])

    output = []
    code = 1
    try:
        for raw in process.stdout:
            line = raw.rstrip("\r\n")
            output.append(line)
            print(line, flush=True)
        code = process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        if process.stdout is not None and not process.stdout.closed:
            process.stdout.close()

    duration = time.monotonic() - started
    status = "✅ ok" if code == 0 else f"❌ exit {code}"
    print(rule("─"))
    print(f"  ⏹ {now_stamp()} · {name} · {status} · {format_duration(duration)}")
    print(rule("─"), flush=True)

    return StepResult(name, code, duration, output)


# ---------------------------------------------------------------------------
# Ciclo completo
# ---------------------------------------------------------------------------
def write_run_log(run_index, fetch, compare, diff_block, total, ok):
    stamp = now_stamp()
    lines = [
        "",
        f"[{stamp}] ═══ RUN #{run_index} ═══",
        f"[{stamp}] {fetch.name} → exit {fetch.code} · {format_duration(fetch.duration)}",
        f"[{stamp}] {compare.name} → exit {compare.code} · {format_duration(compare.duration)}",
        f"[{stamp}] esito: {'OK' if ok else 'ANOMALIE'} · durata totale {format_duration(total)}",
    ]

    if fetch.code != 0:
        lines.append(
            f"[{stamp}] nota: fetch non riuscito, il confronto usa l'ultimo snapshot B disponibile"
        )
        highlights = extract_highlights(fetch.output)
        if highlights:
            lines.append(f"[{stamp}] messaggi chiave fetch:")
            lines.extend(f"    {highlight}" for highlight in highlights)

    if compare.code != 0:
        highlights = extract_highlights(compare.output)
        if highlights:
            lines.append(f"[{stamp}] messaggi chiave confronto:")
            lines.extend(f"    {highlight}" for highlight in highlights)

    if diff_block:
        lines.append(f"[{stamp}] riepilogo confronto (A = grounding · B = whitelist):")
        lines.extend(f"    {line}" for line in diff_block)
    else:
        lines.append(f"[{stamp}] riepilogo confronto: assente (nessun RIEPILOGO prodotto)")

    append_log(lines)


def run_cycle(run_index):
    """Esegue fetch + compare una volta. Ritorna True se entrambi i passi riescono."""
    started = time.monotonic()

    print(f"\n{rule()}")
    print(f"  SHADOW TEST A/B · RUN #{run_index} · {now_stamp()}")
    print(f"  A = {SOURCE_A}   (grounding)")
    print(f"  B = {SOURCE_B}   (whitelist)")
    print(rule(), flush=True)

    fetch = run_step(FETCH_SCRIPT.name, FETCH_SCRIPT)
    compare = run_step(COMPARE_SCRIPT.name, COMPARE_SCRIPT)

    total = time.monotonic() - started
    ok = fetch.code == 0 and compare.code == 0
    diff_block = extract_diff_summary(compare.output)

    verdict = "✅ CICLO OK" if ok else "⚠️  CICLO CON ANOMALIE"
    print(f"\n{rule()}")
    print(f"  {verdict} · run #{run_index} · {format_duration(total)}")
    if not ok:
        print(f"  ↳ exit fetch {fetch.code} · exit compare {compare.code}")
        if fetch.code != 0:
            print("  ↳ fetch fallito: snapshot B invariato, differenze riferite all'ultimo run utile")
        if compare.code == 2:
            print("  ↳ confronto impossibile: manca uno dei due snapshot (vedi messaggi sopra)")
    print(f"  ↳ log: {LOG_FILE}")
    print(rule(), flush=True)

    write_run_log(run_index, fetch, compare, diff_block, total, ok)
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    """Ritorna (once, intervallo_in_secondi) oppure esce con l'help di argparse."""
    parser = argparse.ArgumentParser(
        description=(
            "Esegue periodicamente fetch_traffic_whitelist.py seguito da compare_runs.py, "
            "mostrando l'output in diretta e registrando un riepilogo in logs/shadow_test.log."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Esempi:\n"
            "  python auto_runner.py               # ogni 3 ore, fino a Ctrl+C\n"
            "  python auto_runner.py --hours 6     # ogni 6 ore\n"
            "  python auto_runner.py --minutes 5   # ogni 5 minuti (test rapido)\n"
            "  python auto_runner.py --once        # un solo ciclo ed esce\n"
        ),
    )
    interval = parser.add_mutually_exclusive_group()
    interval.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        metavar="N",
        help=f"intervallo in ore tra due cicli (default: {DEFAULT_HOURS})",
    )
    interval.add_argument(
        "--minutes",
        type=int,
        metavar="N",
        help="intervallo in minuti tra due cicli, utile per test rapidi",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="esegue un solo ciclo ed esce (exit 0 solo se entrambi i passi riescono)",
    )
    args = parser.parse_args(argv)

    if args.minutes is not None:
        if args.minutes <= 0:
            parser.error("--minutes deve essere un intero positivo")
        seconds = args.minutes * 60
    else:
        if args.hours <= 0:
            parser.error("--hours deve essere un intero positivo")
        seconds = args.hours * 3600

    return args.once, seconds


def main(argv=None):
    once, interval = parse_args(argv)

    print(rule())
    print("  AUTO RUNNER · SHADOW TEST A/B (whitelist vs grounding)")
    print(rule())
    print(f"  avvio        {now_stamp()}")
    print(f"  interprete   {sys.executable}")
    print(f"  modalità     {'singolo ciclo (--once)' if once else 'loop periodico'}")
    if not once:
        print(f"  intervallo   {format_interval(interval)}")
    print(f"  log          {LOG_FILE}")
    print("  Ctrl+C       interruzione pulita, senza traceback")
    print(rule(), flush=True)

    run_index = 0
    completed = 0
    exit_code = 0
    try:
        while True:
            run_index += 1
            ok = run_cycle(run_index)
            completed = run_index

            if once:
                exit_code = 0 if ok else 1
                break

            next_at = datetime.now() + timedelta(seconds=interval)
            next_stamp = next_at.strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"\n⏳ Prossimo ciclo: {next_stamp} (fra {format_interval(interval)})"
                " · Ctrl+C per uscire",
                flush=True,
            )
            append_log(
                [f"[{now_stamp()}] prossimo ciclo: {next_stamp} (fra {format_interval(interval)})"]
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        if completed == run_index:
            detail = f"ultimo run completato: #{completed}"
        else:
            detail = f"run #{run_index} interrotto durante l'esecuzione"
        print(f"\n\n{rule('─')}")
        print(f"  👋 Interruzione richiesta ({now_stamp()}) — {detail}.")
        if completed:
            print(f"  Storico disponibile in {LOG_FILE}")
        print("  Alla prossima!")
        print(rule("─"), flush=True)
        append_log([f"[{now_stamp()}] 👋 interruzione manuale (Ctrl+C) · {detail}"])
        exit_code = 0

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
