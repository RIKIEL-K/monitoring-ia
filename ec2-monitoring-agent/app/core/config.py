import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-please-change')
    LOKI_URL = os.environ.get('LOKI_URL', 'http://localhost:3100')
    PROMETHEUS_URL = os.environ.get('PROMETHEUS_URL', 'http://localhost:9090')
    AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-1')
