import logging
from flask import Flask
from app.core.config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure structured logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Register blueprints
    from app.api.routes import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # Register error handlers
    from app.api.error_handlers import register_error_handlers
    register_error_handlers(app)

    # Initialize the agent scheduler
    from app.agent.scheduler import init_scheduler, start_scheduler
    init_scheduler(app)

    # Auto-start monitoring if configured
    if app.config.get('AGENT_AUTO_START', False):
        start_scheduler()
        app.logger.info("Agent auto-started — proactive monitoring is ON")
    else:
        app.logger.info("Agent initialized but NOT auto-started — use POST /api/v1/agent/start")

    app.logger.info("=== Monitoring Agent Ready ===")
    app.logger.info(f"  Prometheus: {app.config['PROMETHEUS_URL']}")
    app.logger.info(f"  Loki: {app.config['LOKI_URL']}")
    app.logger.info(f"  Target App: {app.config.get('TARGET_APP_URL', 'N/A')}")
    app.logger.info(f"  Bedrock model: {app.config.get('BEDROCK_MODEL_ID', 'N/A')}")
    app.logger.info(f"  Monitoring interval: {app.config.get('MONITORING_INTERVAL_MINUTES', 5)} min")

    return app
