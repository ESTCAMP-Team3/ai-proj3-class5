
# app/stream_upload.py
from __future__ import annotations
import os, json, queue, threading
from datetime import datetime
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, abort, session, current_app

bp = Blueprint("stream_upload", __name__, template_folder="templates", static_folder="static")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "uploads"
INBOX_DIR = DATA_DIR / "inbox"        # JPEG 수신 디렉터리
OUTBOX_DIR = DATA_DIR / "outbox"      # 분석 서버로 넘길 디렉터리(공유/마운트 포인트)
PROCESSED_DIR = DATA_DIR / "processed"

for d in (INBOX_DIR, OUTBOX_DIR, PROCESSED_DIR):
    d.mkdir(parents=True, exist_ok=True)

PROCESSING_MODE = os.environ.get("PROCESSING_MODE", "outbox").lower()
work_q: "queue.Queue[Path]" = queue.Queue()

def safe_id(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in s)[:128]

@bp.get("/stream")
def stream_setup():
    if not session.get("user"):
        # 기존 앱의 세션 키(user) 기준, 없으면 로그인으로 유도
        return abort(401)
    return render_template("stream.html")

@bp.get("/stream/healthz")
def healthz():
    return jsonify(ok=True, mode=PROCESSING_MODE)

@bp.post("/api/upload_frame")
def upload_frame():
    # 헤더: X-Stream-ID, X-Seq
    stream_id = request.headers.get("X-Stream-ID") or request.headers.get("X-Session-Id")
    seq = request.headers.get("X-Seq") or "0"
    content_type = (request.headers.get("Content-Type") or "").lower()
    if not stream_id or seq is None:
        return abort(400, "Missing X-Stream-ID/X-Session-Id or X-Seq")
    try:
        seq_num = int(seq)
    except ValueError:
        return abort(400, "X-Seq must be int")

    # JPEG 본문
    if "image/jpeg" not in content_type:
        return abort(415, "Content-Type must be image/jpeg")
    raw = request.get_data(cache=False)
    if not raw:
        return abort(400, "Empty body")

    # 사용자별 디렉토리
    user = session.get("user", "anon")
    sess_dir = INBOX_DIR / safe_id(f"{user}-{stream_id}")
    sess_dir.mkdir(parents=True, exist_ok=True)

    # 원자적 저장
    fname = f"{seq_num:06d}.jpg"
    tmp = sess_dir / (fname + ".part")
    final = sess_dir / fname
    with open(tmp, "wb") as f:
        f.write(raw)
    tmp.rename(final)

    work_q.put(final)
    return jsonify(ok=True, saved=str(final.relative_to(BASE_DIR)))

def worker_loop():
    while True:
        path = work_q.get()
        try:
            if PROCESSING_MODE == "outbox":
                # 동일 파일명으로 OUTBOX에 복사 (분석 파이프라인 인입)
                out = OUTBOX_DIR / path.parent.name / path.name
                out.parent.mkdir(parents=True, exist_ok=True)
                # 하드 링크 시도 후 실패 시 복사
                try:
                    if out.exists(): out.unlink()
                    os.link(path, out)
                except Exception:
                    out.write_bytes(path.read_bytes())
            # 기타 모드: none (저장만)
        except Exception as e:
            print("[worker] error:", e, "on", path)
        finally:
            work_q.task_done()

# 백그라운드 워커 시작
t = threading.Thread(target=worker_loop, daemon=True)
t.start()
