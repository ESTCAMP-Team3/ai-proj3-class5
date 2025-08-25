import os
import json
import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template, jsonify, abort

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"        # JPEG 수신 디렉터리
OUTBOX_DIR = DATA_DIR / "outbox"      # 분석 서버로 넘길 디렉터리(공유/마운트 포인트)
PROCESSED_DIR = DATA_DIR / "processed"

INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# 처리 모드: outbox(기본) | none (그냥 저장만)
PROCESSING_MODE = os.environ.get("PROCESSING_MODE", "outbox").lower()

work_q: "queue.Queue[Path]" = queue.Queue()

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify(ok=True, mode=PROCESSING_MODE)


@app.post("/upload")  # JPEG 프레임 업로드 엔드포인트
def upload_jpeg():
    """
    헤더:
      X-Session-Id: 세션 식별자(클라이언트 생성)
      X-Seq: 프레임 시퀀스 번호 (0..)
    바디:
      image/jpeg 바이트
    """
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
    sess_dir = INBOX_DIR / safe_id(session_id)
    sess_dir.mkdir(parents=True, exist_ok=True)

    # 원자적 저장 (.part → .jpg)
    fname = f"{seq_num:06d}.jpg"
    tmp_path = sess_dir / (fname + ".part")
    final_path = sess_dir / fname
    with open(tmp_path, "wb") as f:
        f.write(raw)
    tmp_path.rename(final_path)

    # 후속 처리 큐
    work_q.put(final_path)

    return jsonify(ok=True, saved=str(final_path.relative_to(BASE_DIR)))


def safe_id(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in s)[:128]


def worker_loop():
    while True:
        path: Path = work_q.get()
        try:
            if PROCESSING_MODE == "outbox":
                forward_to_outbox(path)
            else:
                pass  # 저장만
        except Exception as e:
            log("Worker error", {"file": str(path), "error": str(e)})
        finally:
            work_q.task_done()


def forward_to_outbox(src: Path):
    rel = src.relative_to(INBOX_DIR)
    dst = OUTBOX_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    log("Forwarded to OUTBOX", {"dst": str(dst)})


def log(msg: str, extra=None):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg} :: {json.dumps(extra or {}, ensure_ascii=False)}", flush=True)


# 백그라운드 워커 시작
t = threading.Thread(target=worker_loop, daemon=True)
t.start()


if __name__ == "__main__":
    # localhost 테스트는 HTTP로 충분 (카메라 정책: localhost는 secure origin)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    app.run(host=host, port=port, threaded=True)
