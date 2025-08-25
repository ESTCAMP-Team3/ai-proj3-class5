
# run.py - merged entrypoint
from app.app import app as flask_app  # existing app
from app.stream_upload import bp as stream_bp

# Register blueprint at root
flask_app.register_blueprint(stream_bp)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8000, debug=True)
