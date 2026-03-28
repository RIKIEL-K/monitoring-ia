import logging
from datetime import datetime, timezone
from app.services.prometheus import get_recent_metrics
from app.services.loki import get_recent_logs
from app.services.bedrock import generate_diagnosis

logger = logging.getLogger(__name__)


def handle_incident(alert_data: dict) -> dict:
    """
    Main orchestrator logic to handle an incoming incident.
    1. Parse the alert
    2. Fetch context from Loki & Prometheus (graceful degradation if unreachable)
    3. Query AWS Bedrock for diagnosis
    4. Return the formulated response
    """
    alerts = alert_data.get('alerts', [])
    if not alerts:
        return {"error": "No alerts found in payload"}

    primary_alert = alerts[0]
    incident_name = primary_alert.get('labels', {}).get('alertname', 'Unknown Alert')
    service_name = primary_alert.get('labels', {}).get('service', 'unknown-service')

    logger.info(f"=== Handling incident: {incident_name} (service: {service_name}) ===")

    # 1. Gather context from Loki (graceful degradation)
    log_query = f'{{job="dummy_web_app"}} |= "error"'
    logger.info(f"Fetching logs from Loki: {log_query}")
    logs = get_recent_logs(query=log_query, limit=20)
    logs_available = not any(line.startswith("Error:") for line in logs) if logs else False
    logger.info(f"Logs collected: {len(logs)} lines (available: {logs_available})")

    # 2. Gather context from Prometheus (graceful degradation)
    cpu_query = 'rate(node_cpu_seconds_total{mode="idle"}[5m])'
    logger.info(f"Fetching metrics from Prometheus: {cpu_query}")
    metrics = get_recent_metrics(query=cpu_query)
    metrics_available = "error" not in metrics
    logger.info(f"Metrics collected (available: {metrics_available})")

    # 3. Prepare context for Bedrock
    incident_context = {
        "alert": primary_alert,
        "recent_logs": logs if logs_available else ["Logs unavailable — Loki may be unreachable"],
        "recent_metrics": metrics if metrics_available else {"note": "Metrics unavailable — Prometheus may be unreachable"},
        "data_quality": {
            "logs_available": logs_available,
            "metrics_available": metrics_available
        }
    }

    # 4. Generate Diagnosis using Bedrock
    logger.info("Sending context to AWS Bedrock for diagnosis...")
    diagnosis = generate_diagnosis(incident_context)
    logger.info(f"Diagnosis received: {diagnosis.get('analysis', 'N/A')[:100]}...")

    return {
        "status": "processed",
        "incident": incident_name,
        "service": service_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_quality": {
            "logs_available": logs_available,
            "metrics_available": metrics_available
        },
        "diagnosis": diagnosis
    }
