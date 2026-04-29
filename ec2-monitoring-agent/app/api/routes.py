from flask import Blueprint, request, jsonify
from app.services.orchestrator import handle_incident
from app.services.prometheus import check_connectivity as check_prometheus
from app.services.loki import check_connectivity as check_loki

bp = Blueprint('api', __name__)


# =============================================================================
# Health & Status
# =============================================================================

@bp.route('/health', methods=['GET'])
def health_check():
    """Basic health check — confirms the agent process is running."""
    return jsonify({"status": "ok", "message": "Monitoring Agent is running."}), 200


@bp.route('/status', methods=['GET'])
def status_check():
    """
    Deep health check — verifies connectivity to all dependencies.
    Use this to debug EC2 Security Group / VPC connectivity issues.
    """
    prometheus_status = check_prometheus()
    loki_status = check_loki()

    all_ok = all(
        s.get('status') == 'ok'
        for s in [prometheus_status, loki_status]
    )

    return jsonify({
        "status": "ok" if all_ok else "degraded",
        "dependencies": {
            "prometheus": prometheus_status,
            "loki": loki_status
        }
    }), 200 if all_ok else 503


# =============================================================================
# Agent Control — Start / Stop / Run Now / Status
# =============================================================================

@bp.route('/agent/status', methods=['GET'])
def agent_status():
    """Get the current agent scheduler status."""
    from app.agent.scheduler import get_scheduler_status
    return jsonify(get_scheduler_status()), 200


@bp.route('/agent/start', methods=['POST'])
def agent_start():
    """Start the proactive monitoring scheduler."""
    from app.agent.scheduler import start_scheduler
    started = start_scheduler()
    if started:
        return jsonify({"message": "Agent monitoring started"}), 200
    return jsonify({"message": "Agent already running or not initialized"}), 409


@bp.route('/agent/stop', methods=['POST'])
def agent_stop():
    """Stop the proactive monitoring scheduler."""
    from app.agent.scheduler import stop_scheduler
    stopped = stop_scheduler()
    if stopped:
        return jsonify({"message": "Agent monitoring stopped"}), 200
    return jsonify({"message": "Agent already stopped or not initialized"}), 409


@bp.route('/agent/run-now', methods=['POST'])
def agent_run_now():
    """Force an immediate monitoring cycle."""
    from app.agent.scheduler import run_now
    result = run_now()
    if result:
        return jsonify({"message": "Cycle completed", "result": result}), 200
    return jsonify({"error": "Cycle failed — check logs"}), 500


# =============================================================================
# Incidents — View detected incidents
# =============================================================================

@bp.route('/incidents', methods=['GET'])
def list_incidents():
    """List incidents detected by the monitoring agent."""
    from app.agent.loop import get_incident_history
    limit = request.args.get('limit', 50, type=int)
    incidents = get_incident_history(limit=limit)
    return jsonify({
        "count": len(incidents),
        "incidents": incidents
    }), 200


@bp.route('/incidents/clear', methods=['POST'])
def clear_incidents():
    """Clear the incident history."""
    from app.agent.loop import clear_incident_history
    clear_incident_history()
    return jsonify({"message": "Incident history cleared"}), 200


# =============================================================================
# Legacy — Alert reception (from Alertmanager)
# =============================================================================

@bp.route('/alerts', methods=['POST'])
def receive_alert():
    """
    Receive an alert from Alertmanager (or manual POST).
    Uses the rule-based orchestrator for analysis.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400

    result = handle_incident(data)
    return jsonify(result), 200
