# stream_service.py
from __future__ import annotations
import os
import json
import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from confluent_kafka import Producer

from flask import Blueprint, current_app, request, jsonify, abort

## session_token 을 위한 single run
class _StreamServiceState:
    def __init__(self):
        self.session_token = None   # 로그인 후 주입받을 값
        self.other_state = {}       # 추가 상태 저장 가능

# ✅ 모듈 전역에 싱글턴 객체 생성
stream_state = _StreamServiceState()


# ---- 내부 상태를 app.extensions에 보관하기 위한 컨테이너 ----
class _StreamServiceState:
    def __init__(self, data_dir: Path, processing_mode: str):
        self.BASE_DIR = data_dir.resolve()
        self.DATA_DIR = self.BASE_DIR
        self.INBOX_DIR = self.DATA_DIR / "inbox"
        self.OUTBOX_DIR = self.DATA_DIR / "outbox"
        self.PROCESSED_DIR = self.DATA_DIR / "processed"
        self.PROCESSING_MODE = processing_mode
        self.work_q: "queue.Queue[Path]" = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None

        # sessions 상태 저장용 (필요시 확장 가능)
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()


        # --- Kafka Producer 초기화 ---
        kafka_conf = {
            "bootstrap.servers": "kafka.dongango.com:9094",
        }
        self.kafka_topic = "zolgima-control"
        self.producer = Producer(kafka_conf)

    def _delivery_report(self, err, msg):
        if err is not None:
            _log("Kafka delivery failed", {"error": str(err), "topic": msg.topic(), "key": msg.key().decode() if msg.key() else None})
        else:
            _log("Kafka delivered", {"topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(), "key": msg.key().decode() if msg.key() else None})

    def send_control(self, key: str, session_id: str, stream_type: str = "jpeg"):
        """
        key: "start-stream" | "stop-stream"
        payload: {"sesstion-id": session_id, "session-id": session_id, "type": stream_type}
        """
        payload = {
            "session-id": session_id,    # 일반 표기(소비자 호환용)
            "type": stream_type,
            "session_token" : stream_state.session_token
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.producer.produce(
                topic=self.kafka_topic,
                key=key.encode("utf-8"),
                value=data,
                on_delivery=self._delivery_report
            )
            # 큐 비우기 (non-blocking)
            self.producer.poll(0)
            _log("Kafka produce queued", {"topic": self.kafka_topic, "key": key, "payload": payload})
        except Exception as e:
            _log("Kafka produce error", {"error": str(e), "key": key})

    def ensure_dirs(self):
        self.INBOX_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        self.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    def start_worker_once(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        t = threading.Thread(target=self._worker_loop, daemon=True)
        t.start()
        self.worker_thread = t
        _log("Worker started", {"mode": self.PROCESSING_MODE})

    # --- 워커 루프 ---
    def _worker_loop(self):
        while True:
            path: Path = self.work_q.get()
            try:
                if self.PROCESSING_MODE == "outbox":
                    _forward_to_outbox(self, path)
                else:
                    # "none": 저장만
                    pass
            except Exception as e:
                _log("Worker error", {"file": str(path), "error": str(e)})
            finally:
                self.work_q.task_done()


# ---- 유틸 함수들 ----
def _safe_id(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in s)[:128]

def _log(msg: str, extra: Optional[Dict[str, Any]] = None):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg} :: {json.dumps(extra or {}, ensure_ascii=False)}", flush=True)

def _forward_to_outbox(state: _StreamServiceState, src: Path):
    rel = src.relative_to(state.INBOX_DIR)
    dst = state.OUTBOX_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    ## _log("Forwarded to OUTBOX", {"dst": str(dst)})


# ---- 블루프린트 팩토리 ----
def create_stream_blueprint() -> Blueprint:
    """
    업로드/헬스체크만 제공하는 경량 블루프린트.
    템플릿/정적파일은 메인 앱에서 제공하세요.
    """
    bp = Blueprint("stream_service", __name__)

    @bp.get("/healthz")
    def healthz():
        st = _get_state()
        return jsonify(ok=True, mode=st.PROCESSING_MODE)

    @bp.post("/start")
    def start_session():
        """
        업로드 시작을 명시적으로 알림.
        헤더: X-Session-Id
        """
        st = _get_state()
        session_id = request.headers.get("X-Session-Id")
        if not session_id:
            return abort(400, "Missing X-Session-Id")

        with st._lock:
            if session_id not in st.sessions or st.sessions[session_id].get("ended"):
                st.sessions[session_id] = {
                    "started": True,
                    "ended": False,
                    "first_seq": None,
                    "last_seq": None,
                    "last_seen": None,
                }
                _log("▶ stream started(by client)", {"session": session_id})
                st.send_control("start-stream", session_id, stream_type="jpeg")
        return jsonify(ok=True)

    @bp.post("/stop")
    def stop_session():
        """
        업로드 종료를 명시적으로 알림.
        헤더: X-Session-Id
        """
        st = _get_state()
        session_id = request.headers.get("X-Session-Id")
        if not session_id:
            return abort(400, "Missing X-Session-Id")

        with st._lock:
            info = st.sessions.get(session_id)
            if info and not info.get("ended"):
                info["ended"] = True
                _log("■ stream ended(by client)", {
                    "session": session_id,
                    "last_seq": info.get("last_seq")
                })
                st.send_control("stop-stream", session_id, stream_type="jpeg")
        return jsonify(ok=True)

    @bp.post("/upload")
    def upload_jpeg():
        """
        헤더:
        X-Session-Id: 세션 식별자(클라이언트 생성)
        X-Seq: 프레임 시퀀스 번호 (0..)
        바디:
        image/jpeg 바이트 (chunked 가능)
        """
        st = _get_state()

        session_id = request.headers.get("X-Session-Id")
        seq = request.headers.get("X-Seq")
        content_type = (request.headers.get("Content-Type") or "").lower()

        if not session_id or seq is None:
            return abort(400, "Missing X-Session-Id or X-Seq")

        try:
            seq_num = int(seq)
        except ValueError:
            return abort(400, "X-Seq must be int")

        if "image/jpeg" not in content_type:
            return abort(415, f"Unsupported Content-Type: {content_type}")

        # 세션 폴더 준비
        sess_dir = st.INBOX_DIR / _safe_id(session_id)
        sess_dir.mkdir(parents=True, exist_ok=True)

        # 파일 경로 (원자적 저장: .part -> 최종)
        fname = f"{seq_num:06d}.jpg"
        tmp_path = sess_dir / (fname + ".part")
        final_path = sess_dir / fname

        # === 핵심 변경: 스트리밍으로 바로 파일에 기록 ===
        # request.stream 은 WSGI 입력 스트림으로 chunked body도 지원합니다.
        CHUNK = 64 * 1024  # 64KB 권장
        with open(tmp_path, "wb") as f:
            while True:
                chunk = request.stream.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
            # 속도를 우선할 때는 flush/fsync 생략 (내구성 강화 원하면 아래 주석 해제)
            # f.flush()
            # os.fsync(f.fileno())

        # 원자적 교체 (다른 프로세스가 항상 완성본만 보도록)
        os.replace(tmp_path, final_path)

        # 후속 처리 큐에 전달
        st.work_q.put(final_path)

        # 지연 최소화를 위해 본문 없이 204 반환 (클라가 본문 안 읽는다면 가장 빠름)
        #return Response(status=204)

        # 만약 기존 JSON 응답을 유지하고 싶다면 위 204 대신 아래를 사용:
        return jsonify(ok=True, saved=str(final_path))

    @bp.post("/upload_old")
    def upload_jpeg_old():
        """
        헤더:
          X-Session-Id: 세션 식별자(클라이언트 생성)
          X-Seq: 프레임 시퀀스 번호 (0..)
        바디:
          image/jpeg 바이트
        """
        st = _get_state()

        session_id = request.headers.get("X-Session-Id")
        seq = request.headers.get("X-Seq")
        content_type = (request.headers.get("Content-Type") or "").lower()

        if not session_id or seq is None:
            return abort(400, "Missing X-Session-Id or X-Seq")

        try:
            seq_num = int(seq)
        except ValueError:
            return abort(400, "X-Seq must be int")

        if "image/jpeg" not in content_type:
            return abort(415, f"Unsupported Content-Type: {content_type}")

        raw = request.get_data()
        if not raw:
            return abort(400, "Empty body")

        # 세션 폴더
        sess_dir = st.INBOX_DIR / _safe_id(session_id)
        sess_dir.mkdir(parents=True, exist_ok=True)

        # 원자적 저장 (.part → .jpg)
        fname = f"{seq_num:06d}.jpg"
        tmp_path = sess_dir / (fname + ".part")
        final_path = sess_dir / fname
        with open(tmp_path, "wb") as f:
            f.write(raw)
        tmp_path.rename(final_path)

        # 후속 처리 큐에 전달
        st.work_q.put(final_path)

        return jsonify(ok=True, saved=str(final_path))


    return bp


# ---- 메인 앱에 등록하는 헬퍼 ----
def register_stream_service(app, url_prefix: str = "/stream"):
    """
    메인 Flask 앱에서 호출:
        from stream_service import register_stream_service
        register_stream_service(app, url_prefix="/stream")

    구성 키 (app.config 로 설정 가능):
      - STREAM_DATA_DIR (str | Path): 기본 "./data"
      - STREAM_PROCESSING_MODE (str): "outbox"(기본) | "none"
    """
    data_dir = Path(app.config.get("STREAM_DATA_DIR", "./data"))
    processing_mode = str(app.config.get("STREAM_PROCESSING_MODE", "outbox")).lower()

    # reloader(자식 프로세스)에서 중복 기동 방지
    # Flask/Werkzeug는 재시작 시 WERKZEUG_RUN_MAIN=TRUE를 설정
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" and app.debug:
        # 이미 부모 프로세스에서 등록되었는지 확인
        if getattr(app, "_stream_service_registered", False):
            # 자식 프로세스에서도 확장 상태만 세팅
            state = _StreamServiceState(data_dir, processing_mode)
            state.ensure_dirs()
            app.extensions["stream_service"] = state
            # 자식은 워커를 새로 띄우지 않음 (부모에서 이미 띄움)
            app.register_blueprint(create_stream_blueprint(), url_prefix=url_prefix)
            return

    # 최초 등록
    if "stream_service" in app.extensions:
        # 이미 등록되어 있으면 무시 (여러 번 호출되어도 안전)
        return

    state = _StreamServiceState(data_dir, processing_mode)
    state.ensure_dirs()
    state.start_worker_once()

    app.extensions["stream_service"] = state
    app.register_blueprint(create_stream_blueprint(), url_prefix=url_prefix)
    app._stream_service_registered = True  # 중복 방지 플래그


def _get_state() -> _StreamServiceState:
    st = current_app.extensions.get("stream_service")
    if not st:
        raise RuntimeError("stream_service is not initialized. Call register_stream_service(app) first.")
    return st
