"""
Agent Tools — Définitions et implémentations des outils que l'agent IA peut appeler.

Chaque outil a :
- Une toolSpec (envoyée à Bedrock pour que le LLM sache quoi appeler)
- Une fonction Python qui exécute l'outil
"""
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL SPECIFICATIONS (envoyées à Bedrock Converse API)
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "toolSpec": {
            "name": "query_prometheus",
            "description": (
                "Execute a PromQL query against Prometheus to get system metrics. "
                "Use this to check CPU usage, memory, disk, network, or any metric "
                "exposed by node-exporter or the application. "
                "Examples: 'node_memory_MemAvailable_bytes', "
                "'rate(node_cpu_seconds_total{mode=\"idle\"}[5m])', "
                "'node_filesystem_avail_bytes'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The PromQL query to execute"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "query_loki",
            "description": (
                "Execute a LogQL query against Loki to fetch recent application logs. "
                "Use this to search for errors, warnings, or specific patterns in logs. "
                "The logs come from the dummy-app service. "
                "Examples: '{job=\"dummy_web_app\"} |= \"error\"', "
                "'{job=\"dummy_web_app\"} |= \"timeout\"', "
                "'{job=\"dummy_web_app\"} | json | level=\"error\"'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The LogQL query to execute"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log lines to return (default: 20)"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "check_service_health",
            "description": (
                "Check if a service endpoint is healthy by making an HTTP GET request. "
                "Returns the HTTP status code and response time. "
                "Use this to verify if the target application, Prometheus, or Loki are running. "
                "Common endpoints: the target app health endpoint, Prometheus ready endpoint, Loki ready endpoint."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL to check (e.g., 'http://10.0.1.5:8080/api/health')"
                        }
                    },
                    "required": ["url"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "get_system_overview",
            "description": (
                "Get a comprehensive snapshot of the target server's health: "
                "CPU usage, available memory, disk space, and load average. "
                "This queries multiple Prometheus metrics at once. "
                "Call this first during routine checks to get a quick overview."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    }
]


# =============================================================================
# TOOL IMPLEMENTATIONS (exécutées par l'application)
# =============================================================================

def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Route a tool call to its implementation.
    Returns the result as a dict.
    """
    logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

    implementations = {
        "query_prometheus": _tool_query_prometheus,
        "query_loki": _tool_query_loki,
        "check_service_health": _tool_check_service_health,
        "get_system_overview": _tool_get_system_overview,
    }

    func = implementations.get(tool_name)
    if not func:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        result = func(**tool_input)
        logger.info(f"Tool {tool_name} returned successfully")
        return result
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return {"error": f"Tool execution failed: {str(e)}"}


def _tool_query_prometheus(query: str) -> dict:
    """Execute a PromQL query and return results."""
    url = current_app.config['PROMETHEUS_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)

    try:
        response = requests.get(
            f"{url}/api/v1/query",
            params={"query": query},
            timeout=timeout
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("data", {}).get("result", [])

        # Simplify results for the LLM
        simplified = []
        for r in results[:10]:  # Limit to 10 results
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
        return {"status": "error", "message": f"Prometheus unreachable at {url}"}
    except requests.Timeout:
        return {"status": "error", "message": f"Prometheus timeout after {timeout}s"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _tool_query_loki(query: str, limit: int = 20) -> dict:
    """Execute a LogQL query and return recent logs."""
    import time as _time
    url = current_app.config['LOKI_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)

    end_time = int(_time.time() * 1_000_000_000)
    start_time = end_time - (15 * 60 * 1_000_000_000)  # Last 15 minutes

    try:
        response = requests.get(
            f"{url}/loki/api/v1/query_range",
            params={
                "query": query,
                "limit": limit,
                "start": start_time,
                "end": end_time
            },
            timeout=timeout
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
            "logs": logs[:limit]  # Respect limit
        }
    except requests.ConnectionError:
        return {"status": "error", "message": f"Loki unreachable at {url}"}
    except requests.Timeout:
        return {"status": "error", "message": f"Loki timeout after {timeout}s"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _tool_check_service_health(url: str) -> dict:
    """Check if a service endpoint responds."""
    import time as _time
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)

    start = _time.time()
    try:
        response = requests.get(url, timeout=timeout)
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
        return {"status": "timeout", "url": url, "message": f"No response after {timeout}s"}
    except Exception as e:
        return {"status": "error", "url": url, "message": str(e)}


def _tool_get_system_overview() -> dict:
    """Get a comprehensive system health snapshot from Prometheus."""
    url = current_app.config['PROMETHEUS_URL']
    timeout = current_app.config.get('REQUEST_TIMEOUT', 10)

    queries = {
        "cpu_idle_percent": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
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
                f"{url}/api/v1/query",
                params={"query": query},
                timeout=timeout
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
