import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def check_connectivity() -> dict:
    """Health check: verify Prometheus is reachable."""
    url = current_app.config['PROMETHEUS_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)
    try:
        response = requests.get(f"{url}/-/ready", timeout=timeout)
        if response.status_code == 200:
            return {"status": "ok", "url": url}
        return {"status": "degraded", "url": url, "http_code": response.status_code}
    except requests.ConnectionError:
        return {"status": "unreachable", "url": url, "message": "Connection refused — vérifier le Security Group et l'IP privée"}
    except requests.Timeout:
        return {"status": "timeout", "url": url, "message": f"Timeout après {timeout}s"}
    except Exception as e:
        return {"status": "error", "url": url, "message": str(e)}


def get_recent_metrics(query: str, time_range: str = "5m") -> dict:
    """
    Fetch recent metrics from Prometheus via PromQL.
    Uses the private IP of the EC2 Observability instance.
    """
    url = current_app.config['PROMETHEUS_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)

    logger.info(f"Querying Prometheus: {query}")

    try:
        response = requests.get(
            f"{url}/api/v1/query",
            params={'query': query},
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json().get('data', {})
        logger.info(f"Prometheus returned {len(data.get('result', []))} result(s)")
        return data
    except requests.ConnectionError as e:
        logger.error(f"Prometheus unreachable at {url} — vérifier le SG et l'IP privée: {e}")
        return {"error": f"Connection refused: {url}", "data": []}
    except requests.Timeout:
        logger.error(f"Prometheus timeout after {timeout}s at {url}")
        return {"error": f"Timeout after {timeout}s", "data": []}
    except requests.RequestException as e:
        logger.error(f"Prometheus query failed: {e}")
        return {"error": str(e), "data": []}
