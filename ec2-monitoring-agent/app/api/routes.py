from flask import Blueprint, request, jsonify
from app.services.orchestrator import handle_incident

bp = Blueprint('api', __name__)

@bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Intervention Agent is running."}), 200

@bp.route('/alerts', methods=['POST'])
def receive_alert():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400
    
    # Delegate to the orchestrator
    result = handle_incident(data)
    
    return jsonify(result), 200

@bp.route('/simulate', methods=['POST'])
def simulate_incident():
    """
    Endpoint dedicated to testing the whole Agent orchestration
    without needing a real Prometheus/Alertmanager trigger.
    """
    # Dummy alert payload with enough context to trigger the whole flow
    dummy_alert = {
        "status": "firing",
        "alerts": [
            {
                "labels": {
                    "alertname": "HighErrorRate",
                    "service": "frontend-web",
                    "severity": "critical"
                },
                "annotations": {
                    "description": "The frontend-web service is seeing 5xx errors > 5%."
                }
            }
        ]
    }
    
    result = handle_incident(dummy_alert)
    return jsonify({"message": "Simulation executed", "result": result}), 200
