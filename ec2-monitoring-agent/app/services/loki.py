import requests
from flask import current_app
import time

def get_recent_logs(query: str, limit: int = 50, time_range_minutes: int = 15) -> list:
    """
    Fetch recent logs from Loki/Promtail.
    query: LogQL query (e.g., '{app="my-website"} |= "error"')
    """
    url = current_app.config['LOKI_URL']
    end_time = int(time.time() * 1000000000)
    start_time = end_time - (time_range_minutes * 60 * 1000000000)
    
    try:
        response = requests.get(
            f"{url}/loki/api/v1/query_range",
            params={
                'query': query,
                'limit': limit,
                'start': start_time,
                'end': end_time
            }
        )
        response.raise_for_status()
        results = response.json().get('data', {}).get('result', [])
        
        # Flatten logs for easier processing by the LLM
        logs = []
        for stream in results:
            for value in stream.get('values', []):
                # value is usually [timestamp, log_line]
                if len(value) == 2:
                    logs.append(value[1])
        return logs
    except requests.RequestException as e:
        current_app.logger.error(f"Loki query failed: {e}")
        return [f"Error fetching logs: {str(e)}"]
