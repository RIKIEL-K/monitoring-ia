"""
Agent Loop — Boucle autonome de monitoring MLOps.

Exécute un cycle de monitoring basé sur des règles :
  - Collecte de métriques système via Prometheus
  - Collecte de logs via Loki
  - Analyse par seuils (CPU, mémoire, disque, erreurs)
  - Génération d'un rapport d'incident structuré
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory incident history
_incident_history = []

# Thresholds for rule-based analysis
CPU_WARNING_THRESHOLD = 80.0
CPU_CRITICAL_THRESHOLD = 95.0
MEMORY_WARNING_MB = 500
MEMORY_CRITICAL_MB = 200
DISK_WARNING_PERCENT = 80.0
DISK_CRITICAL_PERCENT = 95.0
LOAD_WARNING_THRESHOLD = 2.0
LOAD_CRITICAL_THRESHOLD = 5.0


def run_agent_cycle(app) -> dict:
    """
    Execute one full MLOps monitoring cycle.

    Steps:
      1. Collect system metrics from Prometheus
      2. Collect recent logs from Loki
      3. Check target app health
      4. Apply rule-based analysis (thresholds)
      5. Return structured diagnosis

    Args:
        app: Flask application instance (needed to read config)

    Returns:
        dict with the cycle result and diagnosis
    """
    from app.agent.tools import (
        configure_tools,
        query_prometheus,
        query_loki,
        check_service_health,
        get_system_overview,
    )

    with app.app_context():
        # Inject service URLs into tools
        configure_tools(
            prometheus_url=app.config['PROMETHEUS_URL'],
            loki_url=app.config['LOKI_URL'],
            request_timeout=app.config.get('REQUEST_TIMEOUT', 10)
        )

        cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        logger.info(f"=== Monitoring Cycle {cycle_id} START ===")

        try:
            # 1. Get system overview
            overview_result = get_system_overview()
            overview = overview_result.get("overview", {})
            logger.info(f"Cycle {cycle_id} — system overview collected")

            # 2. Check for error logs
            log_result = query_loki(query='{job="dummy_web_app"} |= "error"', limit=20)
            error_logs = log_result.get("logs", [])
            error_count = log_result.get("log_count", 0)
            logger.info(f"Cycle {cycle_id} — {error_count} error log(s) found")

            # 3. Check target app health
            target_url = app.config.get('TARGET_APP_URL', 'http://localhost:8080')
            health_result = check_service_health(url=f"{target_url}/api/health")
            logger.info(f"Cycle {cycle_id} — target app: {health_result.get('status', 'unknown')}")

            # 4. Apply rule-based analysis
            diagnosis = _analyze_metrics(overview, error_logs, error_count, health_result)

            result = {
                "cycle_id": cycle_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": diagnosis["severity"],
                "diagnosis": diagnosis,
            }

        except Exception as e:
            logger.error(f"Monitoring Cycle {cycle_id} failed: {e}")
            result = _create_error_result(cycle_id, str(e))

        _incident_history.append(result)
        logger.info(f"=== Monitoring Cycle {cycle_id} END — severity: {result.get('severity', 'unknown')} ===")
        return result


def _analyze_metrics(overview: dict, error_logs: list, error_count: int,
                     health_result: dict) -> dict:
    """
    Rule-based analysis of collected metrics.
    Returns a structured diagnosis with severity, analysis, and optional repair command.
    """
    severity = "ok"
    issues = []
    repair_commands = []
    metrics_checked = []

    # --- CPU Analysis ---
    cpu_raw = overview.get("cpu_usage_percent")
    if cpu_raw and cpu_raw not in ("no_data",) and not str(cpu_raw).startswith("error"):
        try:
            cpu = float(cpu_raw)
            metrics_checked.append("cpu_usage")
            if cpu >= CPU_CRITICAL_THRESHOLD:
                severity = "critical"
                issues.append(f"CPU usage critical: {cpu:.1f}%")
                repair_commands.append("top -b -n 1 | head -20")
            elif cpu >= CPU_WARNING_THRESHOLD:
                severity = _max_severity(severity, "warning")
                issues.append(f"CPU usage elevated: {cpu:.1f}%")
        except (ValueError, TypeError):
            pass

    # --- Memory Analysis ---
    mem_avail_raw = overview.get("memory_available_bytes")
    if mem_avail_raw and mem_avail_raw not in ("no_data",) and not str(mem_avail_raw).startswith("error"):
        try:
            mem_avail_mb = float(mem_avail_raw) / (1024 * 1024)
            metrics_checked.append("memory_available")
            if mem_avail_mb < MEMORY_CRITICAL_MB:
                severity = _max_severity(severity, "critical")
                issues.append(f"Memory critically low: {mem_avail_mb:.0f} MB available")
            elif mem_avail_mb < MEMORY_WARNING_MB:
                severity = _max_severity(severity, "warning")
                issues.append(f"Memory low: {mem_avail_mb:.0f} MB available")
        except (ValueError, TypeError):
            pass

    # --- Disk Analysis ---
    disk_raw = overview.get("disk_available_bytes")
    disk_total_raw = overview.get("disk_total_bytes", None)
    if disk_raw and disk_raw not in ("no_data",) and not str(disk_raw).startswith("error"):
        try:
            disk_avail_gb = float(disk_raw) / (1024 ** 3)
            metrics_checked.append("disk_available")
            if disk_avail_gb < 1.0:
                severity = _max_severity(severity, "critical")
                issues.append(f"Disk space critically low: {disk_avail_gb:.2f} GB available")
                repair_commands.append("df -h && du -sh /var/log/*")
            elif disk_avail_gb < 5.0:
                severity = _max_severity(severity, "warning")
                issues.append(f"Disk space low: {disk_avail_gb:.2f} GB available")
        except (ValueError, TypeError):
            pass

    # --- Load Average Analysis ---
    load_raw = overview.get("load_average_5m")
    if load_raw and load_raw not in ("no_data",) and not str(load_raw).startswith("error"):
        try:
            load_avg = float(load_raw)
            metrics_checked.append("load_average")
            if load_avg >= LOAD_CRITICAL_THRESHOLD:
                severity = _max_severity(severity, "critical")
                issues.append(f"Load average critical: {load_avg:.2f}")
            elif load_avg >= LOAD_WARNING_THRESHOLD:
                severity = _max_severity(severity, "warning")
                issues.append(f"Load average elevated: {load_avg:.2f}")
        except (ValueError, TypeError):
            pass

    # --- Error Logs Analysis ---
    if error_count > 0:
        metrics_checked.append("error_logs")
        if error_count >= 20:
            severity = _max_severity(severity, "critical")
            issues.append(f"{error_count} error logs in last 15 minutes")
        elif error_count >= 5:
            severity = _max_severity(severity, "warning")
            issues.append(f"{error_count} error logs in last 15 minutes")

        # Check for common patterns in logs
        db_errors = sum(1 for log in error_logs if 'database' in log.lower() or 'connection' in log.lower())
        if db_errors > 0:
            issues.append(f"{db_errors} database/connection error(s)")
            repair_commands.append("sudo systemctl restart postgresql")

    # --- Target App Health ---
    app_status = health_result.get("status", "unknown")
    metrics_checked.append("service_health")
    if app_status in ("unreachable", "timeout"):
        severity = _max_severity(severity, "critical")
        issues.append(f"Target application is {app_status}")
    elif app_status == "unhealthy":
        severity = _max_severity(severity, "warning")
        issues.append("Target application returned non-200 status")

    # Final summary
    if not issues:
        analysis = "All systems healthy — no issues detected"
        cause = "System healthy"
    else:
        analysis = "; ".join(issues)
        cause = issues[0] if issues else "Unknown"

    return {
        "severity": severity,
        "analysis": analysis,
        "cause": cause,
        "repair_command": " && ".join(repair_commands) if repair_commands else "",
        "metrics_checked": metrics_checked,
    }


def _max_severity(current: str, new: str) -> str:
    """Return the highest severity between current and new."""
    ranks = {"ok": 0, "warning": 1, "critical": 2}
    if ranks.get(new, -1) > ranks.get(current, -1):
        return new
    return current


def _create_error_result(cycle_id: str, error: str) -> dict:
    """Create an error result when the monitoring cycle fails."""
    return {
        "cycle_id": cycle_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "error",
        "diagnosis": {
            "analysis": f"Monitoring cycle failed: {error}",
            "cause": "Cycle error",
            "repair_command": "",
        },
    }


def get_incident_history(limit: int = 50) -> list:
    """Return the most recent incidents."""
    return list(reversed(_incident_history[-limit:]))


def clear_incident_history():
    """Clear the incident history."""
    _incident_history.clear()
