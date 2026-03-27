import logging
import os
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# Assure que le dossier de logs existe
os.makedirs('/app/logs', exist_ok=True)

# Configuration du logging pour écrire physiquement dans un fichier .log
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('/app/logs/dummy-app.log')
file_handler.setFormatter(log_formatter)

logger = logging.getLogger("dummy-target-app")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

# On garde la console pour docker logs (optionnel)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Test App</title></head>
<body>
    <h1>Application de Test SRE</h1>
    <p>Cette application écrit physiquement ses logs dans un fichier .log pour Promtail.</p>
    <ul>
        <li><button onclick="fetch('/api/generate-error').then(r=>r.json()).then(console.log).then(()=>alert('Erreur critique ajoutée au .log'))">Erreur Critique DB</button></li>
        <li><button onclick="fetch('/api/login-failed').then(r=>r.json()).then(console.log).then(()=>alert('Alerte de connexion ajoutée au .log'))">Échec Connexion</button></li>
        <li><button onclick="fetch('/api/payment-timeout').then(r=>r.json()).then(console.log).then(()=>alert('Erreur timeout ajoutée au .log'))">Timeout Paiement</button></li>
    </ul>
</body>
</html>
"""

@app.route('/')
def index():
    logger.info("Page d'accueil visitée avec succès")
    return render_template_string(HTML_PAGE)

@app.route('/api/generate-error')
def generate_error():
    logger.error("DatabaseConnectionError: impossible de se connecter à la base de données (timeout). IP 10.0.0.5 injoignable.")
    logger.error("Stacktrace: \n  File 'app.py', line 42, in connect_db\n  raise ConnectionTimeout('DB Down')")
    return jsonify({"status": "error_generated", "file": "dummy-app.log"}), 500

@app.route('/api/login-failed')
def login_failed():
    logger.warning("AuthFailure: tentative de connexion échouée pour l'utilisateur admin@company.com")
    return jsonify({"status": "warning_generated", "file": "dummy-app.log"}), 401

@app.route('/api/payment-timeout')
def payment_timeout():
    logger.error("PaymentGatewayTimeout: Stripe API n'a pas répondu dans les 5 secondes.")
    return jsonify({"status": "error_generated", "file": "dummy-app.log"}), 504

@app.route('/api/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
