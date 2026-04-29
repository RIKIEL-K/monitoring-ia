#!/usr/bin/env python3
"""
Collecteur de logs Loki → CSV.

Récupère les logs depuis Loki et les stocke fidèlement dans un CSV
incrémental (sans doublons). Les logs JSON sont éclatés en colonnes
pour faciliter l'analyse MLOps.

Usage:
    # Collecte des dernières 24h
    python3 collect_logs.py --loki-url http://10.0.1.XX:3100

    # Collecte de la dernière heure
    python3 collect_logs.py --loki-url http://10.0.1.XX:3100 --hours 1

Cron (toutes les 5 minutes, collecte la dernière heure) :
    */5 * * * * cd ~/monitoring-ia/ML/notebooks && python3 collect_logs.py --hours 1 >> /var/log/ml/collect_logs.log 2>&1
"""

import os
import sys
import csv
import json
import hashlib
import argparse
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

# Charger le .env du dossier ML/
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ============================================================================
# Configuration
# ============================================================================
DEFAULT_LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
LOGQL_QUERY = '{job="dummy_web_app"}'

# CSV à la racine du projet : datasets/logs_dataset.csv
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATASETS_DIR = os.path.join(PROJECT_ROOT, 'datasets')
CSV_PATH = os.path.join(DATASETS_DIR, 'logs_dataset.csv')

# Colonnes du CSV — les champs JSON de l'app sont éclatés en colonnes
CSV_COLUMNS = [
    'timestamp',          # Timestamp du log (ISO 8601, depuis le JSON de l'app)
    'level',              # INFO, WARNING, ERROR
    'service',            # dummy-target-app
    'message',            # Contenu du message
    'endpoint',           # Route HTTP (/api/health, /, etc.)
    'method',             # GET, POST
    'status_code',        # 200, 401, 500, 504
    'response_time_ms',   # Temps de réponse en ms
    'error_type',         # DatabaseConnectionError, AuthFailure, etc.
    'error_detail',       # Détail de l'erreur
    'client_ip',          # IP du client
    'component',          # database, auth, payment, web, system
    'action',             # db_connect, login, health_check, etc.
    'raw_log',            # Ligne JSON brute complète (backup)
    'log_hash',           # Hash MD5 pour dédoublonnage
    'collected_at',       # Quand on a collecté ce log
]


# ============================================================================
# Parsing des logs JSON
# ============================================================================

def parse_log_line(raw_line: str, loki_ts_ns: str, collected_at: str) -> dict:
    """
    Parse une ligne de log. Supporte le format JSON structuré
    et fallback sur le format texte brut pour rétro-compatibilité.

    Args:
        raw_line: Ligne de log brute reçue de Loki
        loki_ts_ns: Timestamp Loki en nanosecondes
        collected_at: Timestamp de collecte ISO 8601

    Returns:
        Dict avec toutes les colonnes CSV remplies
    """
    log_hash = hashlib.md5(f"{loki_ts_ns}_{raw_line}".encode()).hexdigest()

    # Essayer de parser comme JSON (nouveau format)
    try:
        data = json.loads(raw_line)

        return {
            'timestamp':        data.get('timestamp', ''),
            'level':            data.get('level', ''),
            'service':          data.get('service', ''),
            'message':          data.get('message', ''),
            'endpoint':         data.get('endpoint', ''),
            'method':           data.get('method', ''),
            'status_code':      data.get('status_code', ''),
            'response_time_ms': data.get('response_time_ms', ''),
            'error_type':       data.get('error_type', ''),
            'error_detail':     data.get('error_detail', ''),
            'client_ip':        data.get('client_ip', ''),
            'component':        data.get('component', ''),
            'action':           data.get('action', ''),
            'raw_log':          raw_line,
            'log_hash':         log_hash,
            'collected_at':     collected_at,
        }

    except (json.JSONDecodeError, TypeError):
        # Fallback : ancien format texte brut
        # On stocke le message brut, les champs structurés restent vides
        ts_seconds = int(loki_ts_ns) / 1e9
        ts_readable = datetime.fromtimestamp(ts_seconds, tz=timezone.utc).isoformat()

        return {
            'timestamp':        ts_readable,
            'level':            '',
            'service':          '',
            'message':          raw_line,
            'endpoint':         '',
            'method':           '',
            'status_code':      '',
            'response_time_ms': '',
            'error_type':       '',
            'error_detail':     '',
            'client_ip':        '',
            'component':        '',
            'action':           '',
            'raw_log':          raw_line,
            'log_hash':         log_hash,
            'collected_at':     collected_at,
        }


# ============================================================================
# Interaction Loki
# ============================================================================

def fetch_logs_from_loki(loki_url: str, query: str = LOGQL_QUERY,
                         hours: int = 24, limit: int = 5000) -> list[dict]:
    """
    Récupère les logs depuis Loki via l'API query_range.

    Returns:
        Liste de dicts prêts pour le CSV
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    now_iso = datetime.now().isoformat()

    params = {
        'query': query,
        'limit': limit,
        'start': int(start.timestamp() * 1e9),
        'end': int(end.timestamp() * 1e9),
        'direction': 'forward',
    }

    print(f"[{now_iso}] Requete Loki: {loki_url}")
    print(f"  Query: {query}")
    print(f"  Periode: {start.strftime('%Y-%m-%d %H:%M')} -> {end.strftime('%Y-%m-%d %H:%M')} UTC")

    try:
        resp = requests.get(
            f"{loki_url}/loki/api/v1/query_range",
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        records = []
        json_count = 0
        text_count = 0

        for stream in data.get('data', {}).get('result', []):
            for value in stream.get('values', []):
                ts_ns = value[0]
                raw_log = value[1]

                record = parse_log_line(raw_log, ts_ns, now_iso)
                records.append(record)

                if record['level']:  # JSON parsé avec succès
                    json_count += 1
                else:
                    text_count += 1

        print(f"  {len(records)} logs recuperes ({json_count} JSON, {text_count} texte brut)")
        return records

    except requests.exceptions.ConnectionError:
        print(f"  ERREUR: Impossible de se connecter a Loki sur {loki_url}")
        return []
    except requests.exceptions.HTTPError as e:
        print(f"  ERREUR HTTP Loki: {e}")
        return []
    except Exception as e:
        print(f"  ERREUR: {e}")
        return []


# ============================================================================
# Gestion du CSV incrémental
# ============================================================================

def load_existing_hashes(csv_path: str) -> set:
    """Charge les hashes existants pour éviter les doublons."""
    if not os.path.exists(csv_path):
        return set()
    try:
        hashes = set()
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                hashes.add(row['log_hash'])
        return hashes
    except Exception:
        return set()


def append_to_csv(records: list[dict], csv_path: str) -> int:
    """
    Ajoute des enregistrements au CSV en évitant les doublons.

    Returns:
        Nombre de nouvelles lignes ajoutées
    """
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    existing_hashes = load_existing_hashes(csv_path)
    new_records = [r for r in records if r['log_hash'] not in existing_hashes]

    if not new_records:
        return 0

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_records)

    return len(new_records)


# ============================================================================
# Workflow principal
# ============================================================================

def collect(loki_url: str, hours: int = 24, limit: int = 5000):
    """Exécute une collecte Loki → CSV."""

    # 1. Fetch depuis Loki
    records = fetch_logs_from_loki(loki_url, hours=hours, limit=limit)

    if not records:
        print("  Aucun log recupere. CSV inchange.")
        return

    # 2. Append au CSV (avec dédoublonnage)
    new_count = append_to_csv(records, CSV_PATH)

    # 3. Stats
    total = 0
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            total = sum(1 for _ in f) - 1  # -1 pour le header

    size_kb = os.path.getsize(CSV_PATH) / 1024 if os.path.exists(CSV_PATH) else 0

    print(f"  +{new_count} nouveaux logs (total: {total}, {size_kb:.1f} KB)")
    print(f"  CSV: {CSV_PATH}")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Collecteur Loki -> CSV')
    parser.add_argument('--loki-url', type=str, default=DEFAULT_LOKI_URL,
                        help=f'URL Loki (defaut: {DEFAULT_LOKI_URL})')
    parser.add_argument('--hours', type=int, default=24,
                        help='Heures d\'historique (defaut: 24)')
    parser.add_argument('--limit', type=int, default=5000,
                        help='Max logs par requete (defaut: 5000)')
    args = parser.parse_args()

    collect(args.loki_url, hours=args.hours, limit=args.limit)


if __name__ == '__main__':
    main()
