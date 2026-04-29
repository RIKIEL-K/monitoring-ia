import logging
from datetime import datetime, timezone
from app.services.prometheus import get_recent_metrics
from app.services.loki import get_recent_logs

logger = logging.getLogger(__name__)

# Seuils pour l'analyse par règles
CPU_WARNING_THRESHOLD = 80
CPU_CRITICAL_THRESHOLD = 95
MEMORY_LOW_THRESHOLD_MB = 200
ERROR_LOG_CRITICAL_THRESHOLD = 20
ERROR_LOG_WARNING_THRESHOLD = 5


def handle_incident(alert_data: dict) -> dict:
    """
    Main orchestrator logic to handle an incoming incident.
    1. Parse the alert
    2. Fetch context from Loki & Prometheus (graceful degradation if unreachable)
    3. Analyze with rule-based logic (thresholds)
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

    # 3. Rule-based diagnosis
    logger.info("Analyzing with rule-based logic...")
    diagnosis = _rule_based_diagnosis(
        alert=primary_alert,
        logs=logs if logs_available else [],
        metrics=metrics if metrics_available else {},
        logs_available=logs_available,
        metrics_available=metrics_available,
    )
    logger.info(f"Diagnosis: severity={diagnosis.get('severity', 'N/A')}")

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


def _rule_based_diagnosis(alert: dict, logs: list, metrics: dict,
                          logs_available: bool, metrics_available: bool) -> dict:
    """
    Generate a diagnosis based on thresholds and log pattern matching.
    No external AI involved — pure rule-based analysis.
    """
    severity = "ok"
    issues = []
    repair_commands = []

    alert_name = alert.get('labels', {}).get('alertname', '')
    alert_severity = alert.get('labels', {}).get('severity', 'warning')

    # Analyze logs for error patterns
    if logs_available and logs:
        error_count = sum(1 for line in logs if 'error' in line.lower())
        if error_count >= ERROR_LOG_CRITICAL_THRESHOLD:
            severity = "critical"
            issues.append(f"{error_count} error log(s) detected in the last 15 minutes")
        elif error_count >= ERROR_LOG_WARNING_THRESHOLD:
            severity = max(severity, "warning", key=_severity_rank)
            issues.append(f"{error_count} error log(s) detected")

        # Check for common patterns
        db_errors = sum(1 for line in logs if 'database' in line.lower() or 'connection' in line.lower())
        if db_errors > 0:
            issues.append(f"{db_errors} database/connection error(s) found")
            repair_commands.append("sudo systemctl restart postgresql")

        timeout_errors = sum(1 for line in logs if 'timeout' in line.lower())
        if timeout_errors > 0:
            issues.append(f"{timeout_errors} timeout error(s) found")

    # Use alert severity as fallback
    if alert_severity == 'critical':
        severity = "critical"
    elif alert_severity == 'warning' and severity == "ok":
        severity = "warning"

    if not issues:
        issues.append(f"Alert '{alert_name}' received — no specific pattern matched")

    if not logs_available:
        issues.append("Logs unavailable — Loki may be unreachable")
    if not metrics_available:
        issues.append("Metrics unavailable — Prometheus may be unreachable")

    return {
        "severity": severity,
        "analysis": "; ".join(issues),
        "cause": alert_name or "Alert triggered",
        "repair_command": " && ".join(repair_commands) if repair_commands else "",
    }


def _severity_rank(s: str) -> int:
    """Return a numeric rank for severity comparison."""
    return {"ok": 0, "warning": 1, "critical": 2}.get(s, -1)
