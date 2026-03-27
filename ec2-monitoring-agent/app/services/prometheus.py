import requests
from flask import current_app

def get_recent_metrics(query: str, time_range: str = "5m") -> dict:
    """
    Fetch recent metrics from Prometheus.
    query: PromQL query
    time_range: Optional time range constraint (e.g., '5m')
    """
    url = current_app.config['PROMETHEUS_URL']
    
    try:
        response = requests.get(
            f"{url}/api/v1/query",
            params={'query': f"{query}[{time_range}]"}
        )
        response.raise_for_status()
        return response.json().get('data', {})
    except requests.RequestException as e:
        current_app.logger.error(f"Prometheus query failed: {e}")
        return {"error": str(e), "data": []}
