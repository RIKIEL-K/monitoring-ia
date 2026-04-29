#!/usr/bin/env python3
"""
Log Collector — Récupération de logs depuis Loki pour constituer un dataset CSV

Ce script se connecte à Loki (via son API HTTP), récupère les logs du dummy-app
en temps réel, et les transforme en un fichier dataset.csv exploitable pour
l'entraînement d'un modèle de Log Clustering (TF-IDF + K-Means).

Modes :
  --mode batch   : Récupère les logs d'une plage de temps puis quitte
  --mode stream  : Tourne en boucle, enrichit le CSV toutes les N secondes

Usage :
  python3 log_collector.py --mode batch --hours 24
  python3 log_collector.py --mode stream --interval 60
  python3 log_collector.py --mode batch --hours 168 --output weekly_dataset.csv
"""

import os
import sys
import csv
import re
import time
import argparse
import warnings
from datetime import datetime, timedelta

import requests
import pandas as pd

from dotenv import load_dotenv

# Suppress warnings
warnings.filterwarnings('ignore')

# Load .env from the ML/ directory
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
LOKI_URL = os.getenv("LOKI_URL", "http://10.0.1.XX:3100")
LOKI_QUERY = os.getenv("LOKI_QUERY", '{job="app_logs"}')
DEFAULT_OUTPUT = os.getenv("LOG_DATASET_PATH",
                           os.path.join(os.path.dirname(__file__), "datasets", "log_dataset.csv"))

# Log line regex — format: "2026-04-29 17:00:00,123 - dummy-target-app - INFO - message"
LOG_PATTERN = re.compile(
    r'^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.]?\d*)'
    r'\s*-\s*(?P<logger>[^\s]+)'
    r'\s*-\s*(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)'
    r'\s*-\s*(?P<message>.+)$'
)

# Dataset CSV columns
CSV_COLUMNS = [
    'timestamp',
    'level',
    'logger',
    'message',
    'message_raw',      # ligne complète (compatibilité notebook)
    'hour',             # feature temporelle
    'day_of_week',      # feature temporelle
    'minute',           # feature temporelle
    'log_length',       # feature numérique
    'word_count',       # feature numérique
]


def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(step_num, text):
    """Print a formatted step"""
    print(f"\n[Step {step_num}] {text}")


# ─────────────────────────────────────────────────────────────────────────────
# Loki API
# ─────────────────────────────────────────────────────────────────────────────

def query_loki(start_time: datetime, end_time: datetime,
               limit: int = 5000) -> list:
    """
    Query Loki API for log entries within a time range.

    Args:
        start_time: Start of the query window
        end_time:   End of the query window
        limit:      Max number of log entries per request

    Returns:
        List of raw log line strings
    """
    # Loki expects nanosecond Unix timestamps
    start_ns = int(start_time.timestamp() * 1e9)
    end_ns = int(end_time.timestamp() * 1e9)

    url = f"{LOKI_URL}/loki/api/v1/query_range"
    params = {
        "query": LOKI_QUERY,
        "start": start_ns,
        "end": end_ns,
        "limit": limit,
        "direction": "forward",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Cannot connect to Loki at {LOKI_URL}")
        print("      Check LOKI_URL in your .env file.")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ Loki returned an error: {e}")
        return []

    data = resp.json()

    if data.get("status") != "success":
        print(f"   ❌ Loki query failed: {data}")
        return []

    # Extract log lines from all streams
    lines = []
    results = data.get("data", {}).get("result", [])
    for stream in results:
        for value in stream.get("values", []):
            # value = [nanosecond_timestamp, log_line]
            lines.append(value[1])

    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Log Parsing
# ─────────────────────────────────────────────────────────────────────────────

def parse_log_line(raw_line: str) -> dict | None:
    """
    Parse a single log line into a structured dict.

    Supports format: "2026-04-29 17:00:00,123 - logger - LEVEL - message"
    Falls back to raw extraction if regex doesn't match.

    Args:
        raw_line: Raw log line string

    Returns:
        Dict with parsed fields, or None if line is empty/unparseable
    """
    raw_line = raw_line.strip()
    if not raw_line:
        return None

    match = LOG_PATTERN.match(raw_line)

    if match:
        ts_str = match.group('timestamp')
        logger_name = match.group('logger')
        level = match.group('level')
        message = match.group('message').strip()

        # Parse timestamp
        try:
            # Handle comma or dot in milliseconds
            ts_str_clean = ts_str.replace(',', '.')
            if '.' in ts_str_clean:
                ts = datetime.strptime(ts_str_clean, '%Y-%m-%d %H:%M:%S.%f')
            else:
                ts = datetime.strptime(ts_str_clean, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            ts = datetime.now()
    else:
        # Fallback: treat entire line as the message
        ts = datetime.now()
        logger_name = "unknown"
        level = "INFO"
        message = raw_line

    return {
        'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S'),
        'level': level,
        'logger': logger_name,
        'message': message,
        'message_raw': raw_line,
        'hour': ts.hour,
        'day_of_week': ts.weekday(),
        'minute': ts.minute,
        'log_length': len(raw_line),
        'word_count': len(raw_line.split()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CSV Export
# ─────────────────────────────────────────────────────────────────────────────

def load_existing_timestamps(output_path: str) -> set:
    """
    Load existing timestamps from CSV to avoid duplicates.

    Args:
        output_path: Path to existing CSV file

    Returns:
        Set of (timestamp, message_raw) tuples already in the CSV
    """
    existing = set()
    if os.path.exists(output_path):
        try:
            df = pd.read_csv(output_path, usecols=['timestamp', 'message_raw'])
            for _, row in df.iterrows():
                existing.add((str(row['timestamp']), str(row['message_raw'])))
        except Exception:
            pass
    return existing


def save_to_csv(records: list, output_path: str, deduplicate: bool = True):
    """
    Append parsed log records to a CSV file with deduplication.

    Args:
        records:     List of parsed log dicts
        output_path: Path to the output CSV file
        deduplicate: If True, skip records already present in the file
    """
    if not records:
        print("   ⚠️  No records to save.")
        return 0

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Deduplication
    new_records = records
    if deduplicate:
        existing = load_existing_timestamps(output_path)
        new_records = [
            r for r in records
            if (r['timestamp'], r['message_raw']) not in existing
        ]

    if not new_records:
        print("   ℹ️  All records already exist in CSV (deduplicated).")
        return 0

    # Check if file exists (to decide whether to write header)
    file_exists = os.path.exists(output_path) and os.path.getsize(output_path) > 0

    with open(output_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_records)

    return len(new_records)


# ─────────────────────────────────────────────────────────────────────────────
# Main Workflows
# ─────────────────────────────────────────────────────────────────────────────

def run_batch(hours: float, output_path: str, limit: int = 5000):
    """
    Batch mode: fetch logs from the last N hours and save to CSV.

    Args:
        hours:       Number of hours to look back
        output_path: Path to the output CSV file
        limit:       Max log entries to fetch
    """
    print_header("📋 Log Collector — Batch Mode")

    # Step 1: Connect to Loki
    print_step(1, f"Querying Loki at {LOKI_URL}")
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    print(f"   Time range: {start_time.strftime('%Y-%m-%d %H:%M:%S')} → {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Query: {LOKI_QUERY}")

    raw_lines = query_loki(start_time, end_time, limit=limit)
    print(f"   ✓ Retrieved {len(raw_lines)} log lines from Loki")

    if not raw_lines:
        print("\n❌ No logs found. Check:")
        print(f"   - Loki is running at {LOKI_URL}")
        print(f"   - The query '{LOKI_QUERY}' matches your log streams")
        print(f"   - There are logs within the last {hours} hour(s)")
        return 1

    # Step 2: Parse logs
    print_step(2, "Parsing log lines")
    records = []
    parse_failures = 0
    for line in raw_lines:
        parsed = parse_log_line(line)
        if parsed:
            records.append(parsed)
        else:
            parse_failures += 1

    print(f"   ✓ Parsed {len(records)} records ({parse_failures} lines skipped)")

    # Step 3: Log level distribution
    print_step(3, "Analyzing log level distribution")
    level_counts = {}
    for r in records:
        lvl = r['level']
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    for lvl in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        count = level_counts.get(lvl, 0)
        if count > 0:
            pct = count / len(records) * 100
            print(f"   {lvl:>10}: {count:>6} ({pct:5.1f}%)")

    # Step 4: Save to CSV
    print_step(4, f"Saving to {output_path}")
    saved = save_to_csv(records, output_path, deduplicate=True)
    print(f"   ✓ {saved} new records appended to CSV")

    # Step 5: Summary
    total = 0
    if os.path.exists(output_path):
        df = pd.read_csv(output_path)
        total = len(df)

    print(f"\n✅ Batch complete — {saved} new / {total} total records in {output_path}")
    print(f"   Dataset ready for TF-IDF + K-Means clustering pipeline.")

    return 0


def run_stream(interval: int, output_path: str, limit: int = 5000):
    """
    Stream mode: continuously poll Loki and append new logs to CSV.

    Args:
        interval:    Seconds between each poll
        output_path: Path to the output CSV file
        limit:       Max log entries per poll
    """
    print_header("🔄 Log Collector — Stream Mode")
    print(f"\n⏱️  Polling Loki every {interval} seconds")
    print(f"📁 Output: {output_path}")
    print(f"🔍 Query: {LOKI_QUERY}")
    print("\nPress Ctrl+C to stop\n")

    poll_count = 0
    total_collected = 0

    try:
        while True:
            poll_count += 1
            now = datetime.now()

            print(f"{'─' * 50}")
            print(f"Poll #{poll_count} at {now.strftime('%H:%M:%S')}")

            # Fetch logs from the last interval window (with 10s overlap)
            window = timedelta(seconds=interval + 10)
            start_time = now - window

            raw_lines = query_loki(start_time, now, limit=limit)
            print(f"   Retrieved {len(raw_lines)} lines")

            # Parse
            records = []
            for line in raw_lines:
                parsed = parse_log_line(line)
                if parsed:
                    records.append(parsed)

            # Save (with dedup to handle overlap)
            saved = save_to_csv(records, output_path, deduplicate=True)
            total_collected += saved
            print(f"   ✓ +{saved} new records (total: {total_collected})")

            # Wait
            print(f"   ⏳ Next poll in {interval}s...")
            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\n⏹️  Stream stopped — {total_collected} records collected in {poll_count} polls")
        if os.path.exists(output_path):
            df = pd.read_csv(output_path)
            print(f"   Total dataset size: {len(df)} records")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Collecte les logs depuis Loki et crée un dataset CSV pour ML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python3 log_collector.py --mode batch --hours 24
  python3 log_collector.py --mode batch --hours 168 --output weekly.csv
  python3 log_collector.py --mode stream --interval 60
        """
    )

    parser.add_argument(
        '--mode', choices=['batch', 'stream'], default='batch',
        help='Mode de collecte: batch (ponctuel) ou stream (continu)'
    )
    parser.add_argument(
        '--hours', type=float, default=24,
        help='Fenêtre de collecte en heures (mode batch, défaut: 24)'
    )
    parser.add_argument(
        '--interval', type=int, default=60,
        help='Intervalle de poll en secondes (mode stream, défaut: 60)'
    )
    parser.add_argument(
        '--output', type=str, default=DEFAULT_OUTPUT,
        help=f'Chemin du fichier CSV de sortie (défaut: {DEFAULT_OUTPUT})'
    )
    parser.add_argument(
        '--limit', type=int, default=5000,
        help='Nombre max de lignes de log par requête Loki (défaut: 5000)'
    )

    args = parser.parse_args()

    if args.mode == 'batch':
        return run_batch(args.hours, args.output, args.limit)
    else:
        run_stream(args.interval, args.output, args.limit)
        return 0


if __name__ == "__main__":
    sys.exit(main())
