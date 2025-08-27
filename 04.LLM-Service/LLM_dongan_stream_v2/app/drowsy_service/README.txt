# Drowsy Driving LLM Service (minimal)
Files:
- run.py : Flask-SocketIO server (entrypoint)
- LLM_service.py : LLM/TTS prompt logic

Quickstart
1) Python 3.9+ recommended.
2) pip install flask flask-socketio eventlet flask-cors python-dotenv requests pymongo
3) Create .env next to run.py with at least:
   OPENAI_API_KEY=sk-...
   PORT=8000
   # optional: MONGO_URI=...
4) Run:
   python run.py