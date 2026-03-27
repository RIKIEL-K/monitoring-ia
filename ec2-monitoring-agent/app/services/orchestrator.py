from app.services.prometheus import get_recent_metrics
from app.services.loki import get_recent_logs
from app.services.bedrock import generate_diagnosis

def handle_incident(alert_data: dict) -> dict:
    """
    Main orchestrator logic to handle an incoming incident.
    1. Parse the alert
    2. Fetch context from Loki/Prometheus
    3. Query AWS Bedrock for diagnosis
    4. Return the formulated response
    """
    alerts = alert_data.get('alerts', [])
    if not alerts:
        return {"error": "No alerts found in payload"}
        
    primary_alert = alerts[0]
    incident_name = primary_alert.get('labels', {}).get('alertname', 'Unknown Alert')
    service_name = primary_alert.get('labels', {}).get('service', 'unknown-service')
    
    # 1. Gather context from Loki
    # We query logs for the specific service mentioned in the alert
    log_query = f'{{service="{service_name}"}} |= "error"'
    logs = get_recent_logs(query=log_query, limit=20)
    
    # 2. Gather context from Prometheus
    # e.g., CPU load or Memory usage for the service
    cpu_query = f'rate(process_cpu_seconds_total{{service="{service_name}"}}[5m])'
    metrics = get_recent_metrics(query=cpu_query)
    
    # 3. Prepare Context for Bedrock
    incident_context = {
        "alert": primary_alert,
        "recent_logs": logs,
        "recent_metrics": metrics
    }
    
    # 4. Generate Diagnosis using Bedrock
    diagnosis = generate_diagnosis(incident_context)
    
    return {
        "status": "processed",
        "incident": incident_name,
        "service": service_name,
        "diagnosis": diagnosis
    }
