import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-please-change')

    # --- Connectivité EC2 Observabilité (utiliser l'IP privée dans le même VPC) ---
    LOKI_URL = os.environ.get('LOKI_URL', 'http://localhost:3100')
    PROMETHEUS_URL = os.environ.get('PROMETHEUS_URL', 'http://localhost:9090')
    REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', '10'))  # secondes

    # --- AWS Bedrock ---
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
    BEDROCK_MAX_TOKENS = int(os.environ.get('BEDROCK_MAX_TOKENS', '1024'))
    BEDROCK_RETRY_MAX_ATTEMPTS = int(os.environ.get('BEDROCK_RETRY_MAX_ATTEMPTS', '3'))

    # --- Bedrock Agent (optionnel, si utilisation d'un Agent dédié) ---
    BEDROCK_AGENT_ID = os.environ.get('BEDROCK_AGENT_ID')
    BEDROCK_AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID')

    # --- Agent Autonome ---
    MONITORING_INTERVAL_MINUTES = int(os.environ.get('MONITORING_INTERVAL_MINUTES', '5'))
    AGENT_MAX_ITERATIONS = int(os.environ.get('AGENT_MAX_ITERATIONS', '10'))
    AGENT_AUTO_START = os.environ.get('AGENT_AUTO_START', 'false').lower() == 'true'

    # --- Target App (pour les health checks) ---
    TARGET_APP_URL = os.environ.get('TARGET_APP_URL', 'http://localhost:8080')
