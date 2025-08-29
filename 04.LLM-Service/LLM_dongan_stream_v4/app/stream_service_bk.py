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

from flask import Blueprint, current_app, request, jsonify, abort

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
    _log("Forwarded to OUTBOX", {"dst": str(dst)})


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

    @bp.post("/upload")
    def upload_jpeg():
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
