# run_commented.py
# 원본 run.py 파일에 대한 주석을 자세히 추가한 버전입니다.
# **주의**: 코드 로직 자체는 변경하지 않았으며, 오직 한글 주석만 추가했습니다.
# 이 주석은 사용자가 이해하기 쉽도록 블록별(기능별)로 정리되어 있습니다.

# ----------------------
# 파일 헤더: 이벤트릿 패치 / 기본 import
# ----------------------
# 설명:
# - eventlet.monkey_patch()는 네트워크/스레드 관련 동작을 패치하여
#   eventlet 기반 비동기 동작을 가능하게 합니다. **반드시** 다른 모듈
#   import 전에 호출해야 합니다 (특히 윈도우에서 greendns 문제 회피).
# - 이후 표준 라이브러리와 Flask, Flask-SocketIO, requests 등을 import 합니다.

import os
os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")  # Windows greendns 회피(선택)
import eventlet
eventlet.monkey_patch()

import json
import time
import re
import requests
import threading
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO
from LLM_chat import generate_stage_payload, verify_user_answer, determine_stage_from_d

# ----------------------
# 환경변수 로드 / 상수 설정
# ----------------------
# 설명:
# - .env 또는 .env.example에서 OPENAI_API_KEY, OPENAI_MODEL, PORT, MONGO_URI
#   등 환경변수를 읽습니다. 개발 시 기본값을 사용하도록 안전장치를 넣었습니다.

# EXAMPLE_PATH = ".env.example"
# if os.path.exists(EXAMPLE_PATH):
#     load_dotenv(EXAMPLE_PATH, override=False)
# else:
#     load_dotenv()

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# PORT = int(os.getenv("PORT", "8000"))
# MONGO_URI = os.getenv("MONGO_URI", "")
# EMIT_CHAT_MESSAGE = os.getenv("EMIT_CHAT_MESSAGE", "0") == "1"

# dotenv 로드(권장 패턴: .env 우선, .env.example은 defaults)

here = Path(__file__).parent.resolve()
env_path = here / ".env"
example_path = here / ".env.example"

# 실제 .env가 있으면 우선 로드 (override=True)
if env_path.exists():
    load_dotenv(env_path, override=True)

# 예제 파일을 로드하되 이미 있는 값은 덮어쓰지 않음
if example_path.exists():
    load_dotenv(example_path, override=False)

# 환경변수 읽기
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
PORT = int(os.getenv("PORT", "8000"))
MONGO_URI = os.getenv("MONGO_URI", "")
EMIT_CHAT_MESSAGE = os.getenv("EMIT_CHAT_MESSAGE", "0") == "1"

# 디버그: 키가 로드됐는지 확인 (운영 시에는 제거)
print("DEBUG: OPENAI_API_KEY loaded?:", bool(OPENAI_API_KEY))
print("DEBUG: EMIT_CHAT_MESSAGE:", EMIT_CHAT_MESSAGE, "PORT:", PORT, "OPENAI_MODEL:", OPENAI_MODEL)


# ----------------------
# 비동기 모드 선택 및 Flask/SocketIO 초기화
# ----------------------
# 설명:
# - 기본적으로 eventlet async_mode를 사용하도록 시도합니다. 실패하면
#   threading으로 폴백하며, 개발/디버그 환경에서는 여전히 동작합니다.
async_mode = "eventlet"
try:
    # eventlet 이미 위에서 monkey-patch 함
    pass
except Exception:
    async_mode = "threading"
    print("eventlet not available — using threading (dev only).")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "devsecret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# ----------------------
# MongoDB 선택적 연결 및 로컬 저장 대체
# ----------------------
# 설명:
# - MONGO_URI가 설정되어 있으면 pymongo로 DB 연결을 시도합니다.
# - 실패하거나 URI가 없다면 로컬 JSON 파일(chats_local.json)에 메시지를 저장합니다.
msg_col = None
try:
    if MONGO_URI:
        from pymongo import MongoClient
        mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = mongo.get_database("drowsy_db")
        msg_col = db.get_collection("chat_messages")
        mongo.server_info()
        print("MongoDB connected.")
    else:
        print("MONGO_URI not provided — using local JSON.")
except Exception as e:
    print("MongoDB connection warning:", e)
    msg_col = None

LOCAL_CHAT_FILE = "chats_local.json"

# ----------------------
# save_chat 함수: DB 또는 로컬 파일에 메시지 저장
# ----------------------
# 설명:
# - 메시지(doc)를 MongoDB에 넣거나(가능한 경우), 그렇지 않으면 로컬 JSON에 append합니다.
# - 에러 발생 시 콘솔에 로깅합니다.
def save_chat(doc: dict):
    """Save chat doc to MongoDB if available otherwise to local JSON file."""
    try:
        if msg_col:
            msg_col.insert_one(doc)
        else:
            arr = []
            if os.path.exists(LOCAL_CHAT_FILE):
                try:
                    with open(LOCAL_CHAT_FILE, "r", encoding="utf-8") as f:
                        arr = json.load(f)
                except Exception:
                    arr = []
            arr.append(doc)
            with open(LOCAL_CHAT_FILE, "w", encoding="utf-8") as f:
                json.dump(arr, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_chat err:", e)

# ----------------------
# 유틸리티 함수들: LLM 응답 정리 및 JSON 추출
# ----------------------
# strip_code_fence: LLM이 보내는 코드펜스/따옴표 제거
# extract_json_from_text: 텍스트 내부의 JSON 블록(중괄호)을 찾아 파싱 시도
# clean_llm_text: 전처리 래퍼

def strip_code_fence(text: str) -> str:
    if not text:
        return text
    t = text.replace('\r\n', '\n').replace('\r', '\n')
    t = re.sub(r"(?ms)```[ \t]*[a-zA-Z0-9+\-]*\n", "", t)
    t = re.sub(r"(?m)```[ \t]*\n?", "", t)
    t = re.sub(r"`+", "", t)
    lines = []
    for ln in t.splitlines():
        if ln.strip().lower() in ('json','yaml','text',''):
            continue
        lines.append(ln)
    t = "\n".join(lines).strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    return t


def extract_json_from_text(text: str):
    if not text:
        return None
    try:
        m = re.search(r"\{(?:[^{}]*|\{.*\})*\}", text, flags=re.S)
        if not m:
            m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            candidate = m.group(0)
            try:
                return json.loads(candidate)
            except Exception:
                fixed = candidate.replace("'", '"')
                fixed = re.sub(r",\s*}", "}", fixed)
                fixed = re.sub(r",\s*]", "]", fixed)
                try:
                    return json.loads(fixed)
                except Exception:
                    return None
    except Exception:
        return None
    return None


def clean_llm_text(raw: str) -> str:
    if raw is None:
        return raw
    return strip_code_fence(raw).strip()

# ----------------------
# 졸음 지수 -> 단계 변환 (stage mapping)
# ----------------------
# 설명:
# - D(0~100)를 받아서 상태 문자열을 반환합니다.
# - 임계값은 코드에 하드코딩되어 있으며, 필요 시 환경변수/설정파일로 옮길 수 있습니다.
def stage_from_D(D):
    try:
        D = float(D)
    except Exception:
        return None
    if D <= 30: return "정상"
    if D <= 40: return "의심경고"
    if D <= 50: return "집중모니터링"
    if D <= 60: return "개선"
    if D <= 70: return "L1"
    if D <= 80: return "L2"
    if D <= 90: return "L3"
    return "FAILSAFE"

# ----------------------
# LLM 관련 기본 프롬프트 및 generate_stage_message 함수
# ----------------------
# 설명:
# - OPENAI_API_KEY가 있으면 OpenAI Chat Completions API를 호출하여
#   단계별 announcement와 question JSON을 얻으려 시도합니다.
# - 실패 시 fallback_map에 정의된 기본 문구를 반환합니다.
SYSTEM_PROMPT = "You are 졸지마 Assistant. Respond in Korean concisely."
if os.path.exists("prompt_guidelines.md"):
    try:
        with open("prompt_guidelines.md", "r", encoding="utf-8") as f:
            SYSTEM_PROMPT = f.read()
    except Exception:
        pass


def generate_stage_message(stage_name: str):
    fallback_map = {
        "정상": ("정상 상태입니다.", ""),
        "의심경고": ("주의! 졸음 신호 감지 - 집중해주세요.", ""),
        "집중모니터링": ("상태 확인 중입니다.", ""),
        "개선": ("좋아요. 상태가 나아졌어요.", ""),
        "L1": ("졸음이 지속됩니다. 휴식을 권장해요.", "집중 확인: 지금 날짜가 몇 일이죠?"),
        "L2": ("강한 졸음신호입니다. 창문을 열어보세요.", "서울 다음 도시는?"),
        "L3": ("고위험 졸음 상태입니다. 가까운 휴게소로 안내할까요?", "10에서 1까지 거꾸로 말해보세요."),
        "FAILSAFE": ("고위험 상태입니다.즉시 정차하세요.", "")
    }
    if not OPENAI_API_KEY:
        return fallback_map.get(stage_name, ("주의: 상태 변경", ""))
    prompt = (
        f"Stage: {stage_name}. Return JSON "
        '{"announcement":"short TTS text","question":"short question or empty"} in Korean. Keep announcement <=30 chars.'
    )
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": OPENAI_MODEL, "messages": [{"role":"system","content":SYSTEM_PROMPT}, {"role":"user","content":prompt}], "temperature":0.1, "max_tokens":120}
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=10)
        if r.status_code != 200:
            print("OpenAI API error:", r.status_code, r.text)
            return fallback_map.get(stage_name, ("주의: 상태 변경", ""))
        j = r.json()
        raw = j.get("choices",[{}])[0].get("message",{}).get("content",
                                                                 "")
        cleaned = clean_llm_text(raw)
        parsed = extract_json_from_text(cleaned)
        if parsed:
            ann = clean_llm_text(parsed.get("announcement","") or "")
            q = clean_llm_text(parsed.get("question","") or "")
            return (ann, q)
        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
        if len(lines) == 0:
            return fallback_map.get(stage_name, ("주의: 상태 변경", ""))
        if len(lines) == 1:
            return (lines[0], "")
        return (lines[0], " ".join(lines[1:]))
    except Exception as e:
        print("generate_stage_message OpenAI call err:", e)
        return fallback_map.get(stage_name, ("주의: 상태 변경", ""))

# ----------------------
# 안정화(stability) 및 쿨다운(cooldown) 설정
# ----------------------
# 설명:
# - STABILITY_SECONDS: 새로 관찰된 stage가 안정적으로 지속되어야 emit을 실행합니다.
# - COOLDOWN_SECONDS: 동일 단계에 대한 재전송을 방지하는 최소 시간 간격입니다.
STABILITY_SECONDS = float(os.getenv("STABILITY_SECONDS", "2"))
COOLDOWN_SECONDS = float(os.getenv("COOLDOWN_SECONDS", "30"))

_last_stage = None
_last_emit_ts = 0.0
_pending_stage = None
_pending_since = 0.0

# 동시성 제어용 락
emit_lock = threading.Lock()

# repeater 관련 전역변수
stage_repeater_thread = None
stage_repeater_stop = None
stage_repeater_stage = None
REPEATER_INTERVAL = int(os.getenv("REPEATER_INTERVAL", "10"))  # seconds

# ----------------------
# Repeater(주기적 알림) 제어 함수들
# ----------------------
# 설명:
# - start_stage_repeater: 즉시 한 번 emit하고 interval 간격으로 계속 emit하는 데몬 스레드 생성.
# - stop_stage_repeater: 기존 스레드를 안전히 종료.

def stop_stage_repeater():
    global stage_repeater_thread, stage_repeater_stop, stage_repeater_stage
    try:
        if stage_repeater_stop:
            stage_repeater_stop.set()
        if stage_repeater_thread and stage_repeater_thread.is_alive():
            stage_repeater_thread.join(timeout=0.5)
    except Exception:
        pass
    stage_repeater_thread = None
    stage_repeater_stop = None
    stage_repeater_stage = None


def start_stage_repeater(stage_name, ann_text, q_text, interval=REPEATER_INTERVAL, max_repeats=None):
    """
    Start (or restart) a background thread that emits the announcement immediately
    and then every `interval` seconds until stopped (or until max_repeats).
    Each emit creates a unique msg_id so client treats each tick as distinct.
    """
    global stage_repeater_thread, stage_repeater_stop, stage_repeater_stage
    # ensure previous stopped
    stop_stage_repeater()

    stop_event = threading.Event()
    stage_repeater_stage = stage_name

    def repeater():
        i = 0
        while not stop_event.is_set():
            try:
                with emit_lock:
                    chat_text = ann_text + ("\n" + q_text if q_text else "")
                    # unique per emission (includes timestamp/index)
                    msg_id = hashlib.sha1((str(stage_name) + "|" + chat_text + "|" + str(time.time()) + "|" + str(i)).encode("utf-8")).hexdigest()
                    ts_iso = datetime.utcnow().isoformat() + "Z"

                    # debug log
                    print(f"[REPEATER] emit #{i} stage={stage_name!r} time={ts_iso} preview={chat_text[:40]!r}")

                    # save and emit
                    save_chat({"ts": ts_iso, "user": "assistant", "text": chat_text, "stage": stage_name, "msg_id": msg_id})
                    socketio.emit("state_prompt", {"stage": stage_name, "announcement": ann_text, "question": q_text, "msg_id": msg_id, "repeat": i})
                    if EMIT_CHAT_MESSAGE:
                        socketio.emit("chat_message", {"user": "assistant", "text": chat_text, "msg_id": msg_id, "repeat": i})
            except Exception as e:
                import traceback
                print("Stage repeater emit err:", e)
                traceback.print_exc()
            i += 1
            if max_repeats and i >= max_repeats:
                break
            stop_event.wait(interval)

    t = threading.Thread(target=repeater, daemon=True)
    stage_repeater_thread = t
    stage_repeater_stop = stop_event
    t.start()

# ----------------------
# Flask 엔드포인트들
# ----------------------
# 주요 엔드포인트 요약:
# - / : UI index 반환 (templates/index.html 또는 static/index.html 우선)
# - /ingest : D값 수신 → 상태전이/안정화/emit 처리 핵심 로직
# - /test_emit : 수동으로 특정 stage에 대해 테스트 emit
# - /save_msg : 메시지 저장 + emit
# - /chat_send : 사용자가 보낸 텍스트를 LLM으로 보내고 respond 저장/emit
# - /health : 헬스체크

@app.route("/")
def index():
    tpath = os.path.join("templates","index.html")
    spath = os.path.join("static","index.html")
    if os.path.exists(tpath):
        return render_template("index.html")
    if os.path.exists(spath):
        return send_file(spath)
    if os.path.exists("index.html"):
        return send_file("index.html")
    return "<h1>Index not found</h1>", 404


@app.route("/ingest", methods=["POST"])
def ingest():
    """
    핵심 플로우:
    - POST JSON 수신: {D, ts}
    - 즉시 socketio.emit("d_update")로 클라이언트에 D값을 브로드캐스트(숫자 실시간 표시용)
    - stage 계산(stage_from_D)
    - 히스테리시스: 새 단계가 관찰되면 _pending_stage에 기록 후 STABILITY_SECONDS 동안 관찰
    - 안정화되면 emit_lock으로 보호하며 중복/쿨다운/텍스트 중복 체크 후 repeater 시작
    """
    global _last_stage, _last_emit_ts, _pending_stage, _pending_since
    payload = request.get_json(force=True) or {}
    D = payload.get("D")
    ts = payload.get("ts", time.time())
    now = time.time()

    # always broadcast D for UI numeric display
    try:
        socketio.emit("d_update", {"D": D, "ts": ts})
    except Exception:
        pass

    stage = stage_from_D(D)
    if stage is None:
        return jsonify({"error":"invalid D"}), 400

    # If same as confirmed stage -> reset pending and do nothing
    if stage == _last_stage:
        _pending_stage = None
        _pending_since = 0.0
        return jsonify({"ok":True, "stage":stage, "emitted":False}), 200

    # If observed new stage differs from current pending -> start pending timer
    if _pending_stage != stage:
        _pending_stage = stage
        _pending_since = now
        print(f"Observed new pending stage: {_pending_stage} at {datetime.utcfromtimestamp(now).isoformat()}Z")
        return jsonify({"ok":True, "stage":stage, "pending":True}), 200

    # If pending but not yet stable -> wait
    if now - _pending_since < STABILITY_SECONDS:
        return jsonify({"ok":True, "stage":stage, "pending":True}), 200

    # pending stable -> attempt to emit, but guard with lock
    with emit_lock:
        # double-check last_stage in case another thread emitted already
        if stage == _last_stage:
            _pending_stage = None
            _pending_since = 0.0
            print("Skipping emit: stage already emitted by another thread.")
            return jsonify({"ok":True, "stage":stage, "emitted":False, "reason":"already_emitted"}), 200

        # cooldown check
        if _last_stage == stage and (now - _last_emit_ts) < COOLDOWN_SECONDS:
            _pending_stage = None
            _pending_since = 0.0
            print("Skipping emit due to cooldown for stage:", stage)
            return jsonify({"ok":True, "stage":stage, "emitted":False, "reason":"cooldown"}), 200

        # generate announcement/question
        print(f"Stage change confirmed (will emit): {_last_stage} -> {stage} (D={D})")
        try:
            payload = generate_stage_payload(stage, D, prefer_llm=True)
            ann = payload.get("announcement", "") or ""
            q = payload.get("question", "") or ""
        except Exception as e:
            print("generate_stage_payload error:", e)
            # fallback to previous function if present
            try:
                ann, q = generate_stage_message(stage)
            except Exception:
                ann, q = ("주의: 상태 변경", "")


        # avoid emitting same announcement text repeatedly (additional dedupe)
        if ann and _last_emit_ts > 0:
            try:
                # load last saved assistant message if available to compare text
                last_text = None
                if msg_col:
                    last_doc = msg_col.find_one(sort=[("ts",-1)])  # may be None
                    last_text = last_doc.get("text") if last_doc else None
                else:
                    # read from local file end
                    if os.path.exists(LOCAL_CHAT_FILE):
                        with open(LOCAL_CHAT_FILE, "r", encoding="utf-8") as f:
                            arr = json.load(f)
                            if arr:
                                last_text = arr[-1].get("text")
                if last_text and ann.strip() == last_text.strip():
                    # duplicate text -> skip emit
                    _pending_stage = None
                    _pending_since = 0.0
                    print("Skipping emit: announcement equals last saved message.")
                    return jsonify({"ok":True, "stage":stage, "emitted":False, "reason":"duplicate_text"}), 200
            except Exception as e:
                print("Dedup check failed:", e)

        # At this point, we will start a repeater that emits immediately and then every interval
        # Stop any existing repeater and start a new one for this stage
        stop_stage_repeater()
        # Start repeater - it emits immediately (i=0) and every REPEATER_INTERVAL seconds
        start_stage_repeater(stage, ann, q, interval=REPEATER_INTERVAL, max_repeats=None)

        # update state so ingest logic won't re-trigger immediately
        _last_stage = stage
        _last_emit_ts = now
        _pending_stage = None
        _pending_since = 0.0

        print("Emit/repeater started for stage:", stage)
        return jsonify({"ok":True, "stage":stage, "emitted":True}), 200


@app.route("/test_emit")
def test_emit():
    # useful for manual testing
    stage = request.args.get('stage', 'L2')
    ann, q = generate_stage_message(stage)
    # use start_stage_repeater for consistent behavior
    stop_stage_repeater()
    start_stage_repeater(stage, ann, q, interval=REPEATER_INTERVAL, max_repeats=3)
    return "ok"


@app.route("/save_msg", methods=["POST"])
def save_msg():
    payload = request.get_json(force=True) or {}
    user = payload.get("user","assistant")
    text = payload.get("text",
                       "")
    ts_iso = datetime.utcnow().isoformat() + "Z"
    msg_id = hashlib.sha1((user + "|" + text).encode("utf-8")).hexdigest()

    # save_chat({"ts": ts_iso, "user": user, "text": text, "msg_id": msg_id})
    # socketio.emit("chat_message", {"user": user, "text": text, "msg_id": msg_id})
    return jsonify({"ok": True}), 200


@app.route("/chat_send", methods=["POST"])
def chat_send():
    payload = request.get_json(force=True) or {}
    text = (payload.get("text") or "").strip()
    user = payload.get("user","driver")
    ts_iso = datetime.utcnow().isoformat() + "Z"

    assistant_text = None
    if OPENAI_API_KEY and text:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        body = {"model": OPENAI_MODEL, "messages": [{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":text}], "temperature":0.3, "max_tokens":300}
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=12)
            if r.status_code == 200:
                jr = r.json()
                raw = jr.get("choices",[{}])[0].get("message",{}).get("content",
                                                                            "")
                cleaned = clean_llm_text(raw)
                parsed = extract_json_from_text(cleaned)
                if parsed:
                    assistant_text = parsed.get("reply") or parsed.get("text") or parsed.get("message") or parsed.get("announcement") or json.dumps(parsed, ensure_ascii=False)
                else:
                    assistant_text = cleaned
            else:
                print("OpenAI API error chat_send", r.status_code, r.text)
        except Exception as e:
            print("OpenAI call err chat_send:", e)

    if not assistant_text:
        assistant_text = f"서버 응답(샘플): 네 말 잘 들었어요 — \"{text}\""

    # now compute msg_id, save and emit
    msg_id = hashlib.sha1(("assistant|" + assistant_text).encode("utf-8")).hexdigest()
    save_chat({"ts": ts_iso, "user": "assistant", "text": assistant_text, "msg_id": msg_id})
    socketio.emit("chat_message", {"user": "assistant", "text": assistant_text, "msg_id": msg_id})
    return jsonify({"text": assistant_text}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@socketio.on("connect")
def on_connect():
    print("Client connected.")


@socketio.on("disconnect")
def on_disconnect():
    print("Client disconnected.")


if __name__ == "__main__":
    print(f"Starting server on 0.0.0.0:{PORT} (stability={STABILITY_SECONDS}s cooldown={COOLDOWN_SECONDS}s) async_mode={async_mode}")
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
