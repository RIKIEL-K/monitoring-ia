from flask import Flask
from app.core.config import Config

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register blueprints
    from app.api.routes import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # Register error handlers
    from app.api.error_handlers import register_error_handlers
    register_error_handlers(app)

    return app
