from flask import jsonify

def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request_error(error):
        return jsonify({"error": "Bad Request", "message": str(error)}), 400

    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"error": "Not Found", "message": "The requested URL was not found on the server."}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal Server Error", "message": "An unexpected error occurred."}), 500
