from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from flask_socketio import SocketIO, join_room
from dotenv import load_dotenv
from pathlib import Path
from LLM_chat import generate_stage_payload, verify_user_answer, determine_stage_from_d

from user_service import validate_user, create_user, create_user_session, insert_state_history, get_active_sessions, get_latest_state_for_session
from user_state import get_user_state, stage_from_D, stage_from_level
from state_watcher import StateDBWatcher
from stream_service import register_stream_service

import time
import os
from werkzeug.utils import secure_filename
from flask_sock import Sock  # pip install flask-sock

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "supersecret"   # 환경변수로 관리 권장
app.secret_key = "my-very-secret-key-1234"
socketio = SocketIO(app, cors_allowed_origins="*")

# ----------------------
# 스트림 서비스 설정
# ----------------------
#
app.config.update(
    STREAM_DATA_DIR="./data",           # 절대경로 가능: "/var/lib/camstream"
    STREAM_PROCESSING_MODE="outbox",    # "none"으로 두면 저장만
)

# 블루프린트 등록 (엔드포인트: /stream/...)
register_stream_service(app, url_prefix="/stream")

# Flask-Sock 설정
sock = Sock(app)

# 저장 폴더 준비
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STREAM_DIR = os.path.join(BASE_DIR, 'uploads', 'streams')
os.makedirs(STREAM_DIR, exist_ok=True)

# app.py (메인앱에 추가)
@app.get("/drowny_service")
def drowny_service():
    return render_template("drowny_service.html")
    
# ----------------------
# 로그인/로그아웃
# ----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = validate_user(username, password)
        if user:
            # Flask 세션에 사용자 정보 저장
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            # DB 세션 기록
            session_token = create_user_session(user["id"])
            session["session_token"] = session_token  # Flask 세션에 토큰도 추가

            # ✅ 최초 로그인 시 초기 상태 30(정상) 기록
            initial_level = 30
            initial_stage = stage_from_level(initial_level)
            insert_state_history(user["id"], session_token, initial_level, initial_stage)

            return redirect(url_for("index"))
        else:
            return "로그인 실패", 401
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        name = request.form.get("name")
        email = request.form.get("email")

        try:
            create_user(username, password, name, email)
            return redirect(url_for("login"))
        except Exception as e:
            return f"등록 실패: {str(e)}", 400

    return render_template("register.html")

# ----------------------
# 메인 화면
# ----------------------
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("stream_service.html", username=session["username"])

@app.get('/healthz')
def healthz():
    return 'ok'


@app.route("/ingest", methods=["POST"])
def ingest():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session["user_id"]
    state = get_user_state(user_id)

    payload = request.get_json(force=True) or {}
    D = payload.get("D")
    ts = payload.get("ts", time.time())
    now = time.time()

    # 프런트엔드에 D값 전달 (자기 세션 room 으로만)
    socketio.emit("d_update", {"D": D, "ts": ts}, room=session["username"])

    # Stage 계산 (기존 stage_from_D 활용)
    stage = stage_from_D(D)
    if stage is None:
        return jsonify({"error": "invalid D"}), 400

    # 안정화/쿨다운 로직 (간략 버전)
    if stage == state["last_stage"]:
        state["pending_stage"] = None
        state["pending_since"] = 0.0
        return jsonify({"ok": True, "stage": stage, "emitted": False})

    if state["pending_stage"] != stage:
        state["pending_stage"] = stage
        state["pending_since"] = now
        return jsonify({"ok": True, "stage": stage, "pending": True})

    if now - state["pending_since"] < 2:  # STABILITY_SECONDS
        return jsonify({"ok": True, "stage": stage, "pending": True})

    # 확정: 사용자 room 으로 상태 이벤트 전달
    msg_id = hashlib.sha1((str(user_id) + "|" + stage + "|" + str(time.time())).encode()).hexdigest()
    ts_iso = datetime.utcnow().isoformat() + "Z"

    socketio.emit("state_prompt",
                  {"stage": stage, "announcement": f"{stage} 상태입니다.", "question": "", "msg_id": msg_id},
                  room=session["username"])

    state["last_stage"] = stage
    state["last_emit_ts"] = now
    state["pending_stage"] = None
    state["pending_since"] = 0.0

    return jsonify({"ok": True, "stage": stage, "emitted": True})

@app.route("/api/state/latest", methods=["GET"])
def api_state_latest():
    # 세션 확인 (브라우저는 자동으로 session 쿠키 전송)
    if "user_id" not in session or "session_token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    sess_token = session["session_token"]
    row = get_latest_state_for_session(sess_token)
    if not row:
        # 로그인 직후 초기값(정상=30)을 못 넣은 경우를 대비
        return jsonify({"has_state": False}), 200

    return jsonify({
        "has_state": True,
        "level_code": int(row["level_code"]),
        "stage": row["stage"],
        "ts": row["created_at"].isoformat() + "Z"
    }), 200

# ----------------------
# Socket.IO 연결시 사용자 room join
# ----------------------
@socketio.on("connect")
def on_connect():
    if "username" in session:
        join_room(session["username"])
        print(f"{session['username']} joined room")

if __name__ == "__main__":
    # 의존성: pip install gevent gevent-websocket
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler

    # ✅ 워처 인스턴스 생성 및 시작
    watcher = StateDBWatcher(
        socketio=socketio,
        get_active_sessions=get_active_sessions,
        get_latest_state_for_session=get_latest_state_for_session,
        get_user_state=get_user_state,
        stage_from_level=stage_from_level,
        # stability_seconds=2.0,   # 필요 시 override
        # cooldown_seconds=30.0,   # 필요 시 override
    )
    watcher.start(interval_sec=1.0)

    server = pywsgi.WSGIServer(
        ("0.0.0.0", 8000),
        app,
        handler_class=WebSocketHandler,   # WS 업그레이드 처리
    )
    print("Serving HTTP/WS on :8000")
    server.serve_forever()

"""
if __name__ == "__main__":
#    socketio.run(app, host="0.0.0.0", port=8000, debug=True)
#    ssl_context = ("server.crt", "server.key")   # 순서 (cert, key)
    import ssl
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    
#    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)  # ✅ PROTOCOL_TLS 대신 SERVER 전용
    ssl_context.load_cert_chain("server.crt", "server.key")
    # Flask-SocketIO https 실행
    server = pywsgi.WSGIServer(
        ("0.0.0.0", 8443),
        app,                           # flask app (flask-sock 포함)
        handler_class=WebSocketHandler,
        ssl_context=ssl_context,
    )
    print("Serving HTTPS/WSS on :8443")
    server.serve_forever()

"""    
