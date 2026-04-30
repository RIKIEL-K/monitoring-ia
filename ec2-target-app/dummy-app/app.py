import logging
import json
import os
import time
import traceback
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# ============================================================================
# Logging JSON structuré — lisible par Grafana/Loki
# ============================================================================

os.makedirs('/app/logs', exist_ok=True)


class JSONFormatter(logging.Formatter):
    """
    Formatter qui produit une ligne JSON par log.
    Chaque ligne contient des champs structurés que Grafana/Loki
    peut parser et indexer automatiquement.
    """

    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "dummy-target-app",
            "message": record.getMessage(),
        }

        # Ajouter les champs extra s'ils existent
        for key in ['endpoint', 'method', 'status_code', 'response_time_ms',
                     'error_type', 'error_detail', 'client_ip', 'user',
                     'component', 'action']:
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        # Ajouter le traceback si présent
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["traceback"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


# File handler — écrit dans le fichier .log (lu par Grafana Alloy)
json_formatter = JSONFormatter()
file_handler = logging.FileHandler('/app/logs/dummy-app.log')
file_handler.setFormatter(json_formatter)

# Console handler — pour docker logs
console_handler = logging.StreamHandler()
console_handler.setFormatter(json_formatter)

logger = logging.getLogger("dummy-target-app")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Désactiver les logs par défaut de Flask/Werkzeug pour éviter le bruit
logging.getLogger('werkzeug').setLevel(logging.WARNING)


# ============================================================================
# Page HTML
# ============================================================================

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Test App — SRE</title></head>
<body>
    <h1>Application de Test SRE</h1>
    <p>Cette application génère des logs JSON structurés pour Loki/Grafana.</p>
    <ul>
        <li><button onclick="fetch('/api/generate-error').then(r=>r.json()).then(console.log).then(()=>alert('Erreur DB ajoutée'))">Erreur Critique DB</button></li>
        <li><button onclick="fetch('/api/login-failed').then(r=>r.json()).then(console.log).then(()=>alert('Échec connexion ajouté'))">Échec Connexion</button></li>
        <li><button onclick="fetch('/api/payment-timeout').then(r=>r.json()).then(console.log).then(()=>alert('Timeout paiement ajouté'))">Timeout Paiement</button></li>
        <li><button onclick="fetch('/api/health').then(r=>r.json()).then(d=>alert('Health: '+d.status))">Health Check</button></li>
    </ul>
</body>
</html>
"""


# ============================================================================
# Routes
# ============================================================================

@app.route('/')
def index():
    start = time.time()
    logger.info(
        "Page d'accueil visitée avec succès",
        extra={
            "endpoint": "/",
            "method": "GET",
            "status_code": 200,
            "response_time_ms": round((time.time() - start) * 1000, 2),
            "client_ip": request.remote_addr,
            "component": "web",
            "action": "page_visit",
        }
    )
    return render_template_string(HTML_PAGE)


@app.route('/api/generate-error')
def generate_error():
    start = time.time()

    logger.error(
        "DatabaseConnectionError: impossible de se connecter à la base de données (timeout)",
        extra={
            "endpoint": "/api/generate-error",
            "method": "GET",
            "status_code": 500,
            "response_time_ms": round((time.time() - start) * 1000, 2),
            "client_ip": request.remote_addr,
            "error_type": "DatabaseConnectionError",
            "error_detail": "IP 10.0.0.5 injoignable, timeout après 5s",
            "component": "database",
            "action": "db_connect",
        }
    )

    logger.error(
        "Stacktrace: connexion DB échouée",
        extra={
            "endpoint": "/api/generate-error",
            "method": "GET",
            "status_code": 500,
            "client_ip": request.remote_addr,
            "error_type": "ConnectionTimeout",
            "error_detail": "File 'app.py', line 42, in connect_db → raise ConnectionTimeout('DB Down')",
            "component": "database",
            "action": "db_connect",
        }
    )

    return jsonify({"status": "error_generated", "file": "dummy-app.log"}), 500


@app.route('/api/login-failed')
def login_failed():
    start = time.time()

    logger.warning(
        "AuthFailure: tentative de connexion échouée",
        extra={
            "endpoint": "/api/login-failed",
            "method": "GET",
            "status_code": 401,
            "response_time_ms": round((time.time() - start) * 1000, 2),
            "client_ip": request.remote_addr,
            "error_type": "AuthFailure",
            "error_detail": "Identifiants invalides pour admin@company.com",
            "user": "admin@company.com",
            "component": "auth",
            "action": "login",
        }
    )

    return jsonify({"status": "warning_generated", "file": "dummy-app.log"}), 401


@app.route('/api/payment-timeout')
def payment_timeout():
    start = time.time()

    logger.error(
        "PaymentGatewayTimeout: Stripe API n'a pas répondu dans les 5 secondes",
        extra={
            "endpoint": "/api/payment-timeout",
            "method": "GET",
            "status_code": 504,
            "response_time_ms": round((time.time() - start) * 1000, 2),
            "client_ip": request.remote_addr,
            "error_type": "PaymentGatewayTimeout",
            "error_detail": "Stripe API timeout après 5000ms",
            "component": "payment",
            "action": "payment_process",
        }
    )

    return jsonify({"status": "error_generated", "file": "dummy-app.log"}), 504


@app.route('/api/health')
def health():
    start = time.time()

    logger.info(
        "Health check OK",
        extra={
            "endpoint": "/api/health",
            "method": "GET",
            "status_code": 200,
            "response_time_ms": round((time.time() - start) * 1000, 2),
            "client_ip": request.remote_addr,
            "component": "system",
            "action": "health_check",
        }
    )

    return jsonify({"status": "ok"})


if __name__ == '__main__':
    logger.info(
        "Application démarrée",
        extra={
            "component": "system",
            "action": "startup",
            "endpoint": None,
            "method": None,
            "status_code": None,
        }
    )
    app.run(host='0.0.0.0', port=8080)
