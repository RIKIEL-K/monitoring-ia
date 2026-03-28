import logging
import time
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def check_connectivity() -> dict:
    """Health check: verify Loki is reachable."""
    url = current_app.config['LOKI_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)
    try:
        response = requests.get(f"{url}/ready", timeout=timeout)
        if response.status_code == 200:
            return {"status": "ok", "url": url}
        return {"status": "degraded", "url": url, "http_code": response.status_code}
    except requests.ConnectionError:
        return {"status": "unreachable", "url": url, "message": "Connection refused — vérifier le Security Group et l'IP privée"}
    except requests.Timeout:
        return {"status": "timeout", "url": url, "message": f"Timeout après {timeout}s"}
    except Exception as e:
        return {"status": "error", "url": url, "message": str(e)}


def get_recent_logs(query: str, limit: int = 50, time_range_minutes: int = 15) -> list:
    """
    Fetch recent logs from Loki via LogQL.
    Uses the private IP of the EC2 Observability instance.
    """
    url = current_app.config['LOKI_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)
    end_time = int(time.time() * 1_000_000_000)
    start_time = end_time - (time_range_minutes * 60 * 1_000_000_000)

    logger.info(f"Querying Loki: {query} (last {time_range_minutes}min, limit={limit})")

    try:
        response = requests.get(
            f"{url}/loki/api/v1/query_range",
            params={
                'query': query,
                'limit': limit,
                'start': start_time,
                'end': end_time
            },
            timeout=timeout
        )
        response.raise_for_status()
        results = response.json().get('data', {}).get('result', [])

        # Flatten logs for easier processing by the LLM
        logs = []
        for stream in results:
            for value in stream.get('values', []):
                if len(value) == 2:
                    logs.append(value[1])

        logger.info(f"Loki returned {len(logs)} log line(s)")
        return logs

    except requests.ConnectionError as e:
        logger.error(f"Loki unreachable at {url} — vérifier le SG et l'IP privée: {e}")
        return [f"Error: Loki unreachable at {url}"]
    except requests.Timeout:
        logger.error(f"Loki timeout after {timeout}s at {url}")
        return [f"Error: Loki timeout after {timeout}s"]
    except requests.RequestException as e:
        logger.error(f"Loki query failed: {e}")
        return [f"Error fetching logs: {str(e)}"]
