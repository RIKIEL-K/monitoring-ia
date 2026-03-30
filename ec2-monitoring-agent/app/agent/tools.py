"""
Agent Tools — Outils que l'agent Strands peut appeler.

Chaque fonction est décorée avec @tool. Strands génère automatiquement
le schéma JSON à partir des type hints et de la docstring.
"""
import logging
import time as _time
import requests
from strands import tool

logger = logging.getLogger(__name__)

# Les URLs sont injectées au démarrage depuis la config Flask
_PROMETHEUS_URL: str = "http://localhost:9090"
_LOKI_URL: str = "http://localhost:3100"
_REQUEST_TIMEOUT: int = 10


def configure_tools(prometheus_url: str, loki_url: str, request_timeout: int = 10):
    """Initialise les URLs des services externes. Appelé au démarrage de l'app."""
    global _PROMETHEUS_URL, _LOKI_URL, _REQUEST_TIMEOUT
    _PROMETHEUS_URL = prometheus_url
    _LOKI_URL = loki_url
    _REQUEST_TIMEOUT = request_timeout
    logger.info(f"Tools configured — Prometheus: {prometheus_url}, Loki: {loki_url}")


# =============================================================================
# TOOL DEFINITIONS (décorées @tool — Strands génère le toolSpec automatiquement)
# =============================================================================

@tool
def query_prometheus(query: str) -> dict:
    """
    Execute a PromQL query against Prometheus to get system metrics.
    Use this to check CPU usage, memory, disk, network, or any metric
    exposed by node-exporter or the application.
    Examples: 'node_memory_MemAvailable_bytes',
    'rate(node_cpu_seconds_total{mode="idle"}[5m])',
    'node_filesystem_avail_bytes'.
    """
    logger.info(f"[tool] query_prometheus: {query}")
    try:
        response = requests.get(
            f"{_PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=_REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("data", {}).get("result", [])

        simplified = []
        for r in results[:10]:
            metric = r.get("metric", {})
            value = r.get("value", [None, None])
            simplified.append({
                "metric": metric,
                "value": value[1] if len(value) > 1 else None,
                "timestamp": value[0] if len(value) > 0 else None
            })

        return {
            "status": "success",
            "query": query,
            "result_count": len(results),
            "results": simplified
        }
    except requests.ConnectionError:
        return {"status": "error", "message": f"Prometheus unreachable at {_PROMETHEUS_URL}"}
    except requests.Timeout:
        return {"status": "error", "message": f"Prometheus timeout after {_REQUEST_TIMEOUT}s"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@tool
def query_loki(query: str, limit: int = 20) -> dict:
    """
    Execute a LogQL query against Loki to fetch recent application logs.
    Use this to search for errors, warnings, or specific patterns in logs.
    The application logs use job="app_logs" as the stream selector.
    System logs use job="system_logs".
    Examples: '{job="app_logs"} |= "error"',
    '{job="app_logs"} |= "INFO"',
    '{job="app_logs"} | logfmt | level="error"'.
    """
    logger.info(f"[tool] query_loki: {query} (limit={limit})")
    end_time = int(_time.time() * 1_000_000_000)
    start_time = end_time - (15 * 60 * 1_000_000_000)  # Last 15 minutes

    try:
        response = requests.get(
            f"{_LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": query,
                "limit": limit,
                "start": start_time,
                "end": end_time
            },
            timeout=_REQUEST_TIMEOUT
        )
        response.raise_for_status()
        results = response.json().get("data", {}).get("result", [])

        logs = []
        for stream in results:
            for value in stream.get("values", []):
                if len(value) == 2:
                    logs.append(value[1])

        return {
            "status": "success",
            "query": query,
            "log_count": len(logs),
            "logs": logs[:limit]
        }
    except requests.ConnectionError:
        return {"status": "error", "message": f"Loki unreachable at {_LOKI_URL}"}
    except requests.Timeout:
        return {"status": "error", "message": f"Loki timeout after {_REQUEST_TIMEOUT}s"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@tool
def check_service_health(url: str) -> dict:
    """
    Check if a service endpoint is healthy by making an HTTP GET request.
    Returns the HTTP status code and response time.
    Use this to verify if the target application, Prometheus, or Loki are running.
    Common endpoints: the target app health endpoint, Prometheus ready endpoint, Loki ready endpoint.
    """
    logger.info(f"[tool] check_service_health: {url}")
    start = _time.time()
    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT)
        elapsed = round(_time.time() - start, 3)
        return {
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "url": url,
            "http_status": response.status_code,
            "response_time_seconds": elapsed
        }
    except requests.ConnectionError:
        return {"status": "unreachable", "url": url, "message": "Connection refused"}
    except requests.Timeout:
        return {"status": "timeout", "url": url, "message": f"No response after {_REQUEST_TIMEOUT}s"}
    except Exception as e:
        return {"status": "error", "url": url, "message": str(e)}


@tool
def get_system_overview() -> dict:
    """
    Get a comprehensive snapshot of the target server's health:
    CPU usage, available memory, disk space, and load average.
    This queries multiple Prometheus metrics at once.
    Call this first during routine checks to get a quick overview.
    """
    logger.info("[tool] get_system_overview")
    queries = {
        "cpu_usage_percent": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
        "memory_available_bytes": "node_memory_MemAvailable_bytes",
        "memory_total_bytes": "node_memory_MemTotal_bytes",
        "disk_available_bytes": 'node_filesystem_avail_bytes{mountpoint="/"}',
        "load_average_1m": "node_load1",
        "load_average_5m": "node_load5",
    }

    overview = {}
    for name, query in queries.items():
        try:
            response = requests.get(
                f"{_PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            results = response.json().get("data", {}).get("result", [])
            if results:
                value = results[0].get("value", [None, None])
                overview[name] = value[1] if len(value) > 1 else None
            else:
                overview[name] = "no_data"
        except Exception as e:
            overview[name] = f"error: {str(e)}"

    return {"status": "success", "overview": overview}
