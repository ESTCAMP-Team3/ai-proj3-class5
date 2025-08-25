import os
import uuid
import json
import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template, jsonify, send_from_directory, abort

# ====== 기본 설정 ======
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INBOX_DIR = DATA_DIR / "inbox"       # 업로드 수신 디렉토리
OUTBOX_DIR = DATA_DIR / "outbox"     # 분석 서버로 넘길 디렉토리 (폴더공유/마운트 포인트 등)
PROCESSED_DIR = DATA_DIR / "processed"

INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# 처리 모드: outbox(기본) | local
PROCESSING_MODE = os.environ.get("PROCESSING_MODE", "outbox").lower()

# 분석 서버 HTTP 엔드포인트(선택, OUTBOX 대신 직접 전송에 쓰고 싶을 때)
VISION_ENDPOINT_URL = os.environ.get("VISION_ENDPOINT_URL", "").strip()

# 업로드 허용 MIME → 확장자 매핑
MIME_TO_EXT = {
    "video/mp4": "mp4",
    "video/webm": "webm"
}

# 업로드당 256MB 제한 (필요 시 조정)
MAX_UPLOAD_BYTES = 256 * 1024 * 1024

# 업로드 → 처리 워커 큐
work_q: "queue.Queue[Path]" = queue.Queue()

app = Flask(__name__, static_folder="static", template_folder="templates")


# ========== 간단 페이지 ==========
@app.get("/")
def index():
    return render_template("index.html")


# 헬스체크
@app.get("/healthz")
def healthz():
    return jsonify(ok=True, mode=PROCESSING_MODE)


# ========== 업로드 엔드포인트 ==========
@app.post("/upload")
def upload_chunk():
    """
    브라우저 MediaRecorder Blob 업로드 (1초 세그먼트).
    헤더:
      X-Session-Id: 클라이언트 생성 세션 식별자
      X-Seq: 세그먼스 시퀀스 (0부터 증가)
      X-Mime: Blob MIME (video/mp4 | video/webm)
    바디:
      바이너리 동영상 조각
    """
    session_id = request.headers.get("X-Session-Id")
    seq = request.headers.get("X-Seq")
    mime = request.headers.get("X-Mime", "").split(";")[0].strip().lower()

    if not session_id or seq is None:
        return abort(400, "Missing X-Session-Id or X-Seq")

    try:
        seq_num = int(seq)
    except ValueError:
        return abort(400, "X-Seq must be int")

    raw = request.get_data()
    if raw is None or len(raw) == 0:
        return abort(400, "Empty body")
    if len(raw) > MAX_UPLOAD_BYTES:
        return abort(413, "Payload too large")

    ext = MIME_TO_EXT.get(mime)
    if ext is None:
        # 기본은 webm로 저장
        ext = "webm"

    # 세션 폴더
    sess_dir = INBOX_DIR / safe_id(session_id)
    sess_dir.mkdir(parents=True, exist_ok=True)

    # 원자적 저장: .part → 최종명으로 rename
    fname = f"{seq_num:06d}.{ext}"
    tmp_path = sess_dir / (fname + ".part")
    final_path = sess_dir / fname

    with open(tmp_path, "wb") as f:
        f.write(raw)
    tmp_path.rename(final_path)

    # 처리 큐에 넣기
    work_q.put(final_path)

    return jsonify(ok=True, saved=str(final_path.relative_to(BASE_DIR)))


def safe_id(s: str) -> str:
    # 세션ID/파일명에 쓸 안전 문자열
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in s)[:128]


# ========== 처리 워커 ==========
def worker_loop():
    """
    업로드된 파일을 즉시 후속 단계로 전달.
    - PROCESSING_MODE=outbox : OUTBOX_DIR로 move (분석서버가 폴더 감시)
    - PROCESSING_MODE=local  : 로컬 Mediapipe 데모 처리
    - VISION_ENDPOINT_URL 설정 시 : HTTP POST로 전송(선택)
    """
    log("Worker started", {"mode": PROCESSING_MODE})

    while True:
        path: Path = work_q.get()
        try:
            if VISION_ENDPOINT_URL:
                # 선택: 직접 HTTP 전송 (큰 파일은 비권장. 예제로 남김)
                try_http_forward(path)
            elif PROCESSING_MODE == "outbox":
                forward_to_outbox(path)
            else:
                analyze_locally_with_mediapipe(path)
        except Exception as e:
            log("Worker error", {"file": str(path), "error": str(e)})
        finally:
            work_q.task_done()


def forward_to_outbox(src: Path):
    # OUTBOX/<session>/ 로 보관. 분석 서버는 이 경로를 바로 consume.
    rel = src.relative_to(INBOX_DIR)
    dst = OUTBOX_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    log("Forwarded to OUTBOX", {"dst": str(dst)})


def try_http_forward(src: Path):
    import requests
    files = {"file": (src.name, open(src, "rb"), "application/octet-stream")}
    meta = {"session": src.parent.name, "filename": src.name, "ts": datetime.utcnow().isoformat()}
    r = requests.post(VISION_ENDPOINT_URL, data=meta, files=files, timeout=30)
    r.raise_for_status()
    # 성공 시 원본 이동/삭제
    dst = PROCESSED_DIR / src.parent.name / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    log("Forwarded via HTTP", {"dst": str(dst), "status": r.status_code})


def analyze_locally_with_mediapipe(video_path: Path):
    """
    간단 데모: OpenCV + Mediapipe Face Detection으로 프레임 수/검출 수를 로그.
    실제 환경에 맞게 EAR/MAR 등 분석 루틴으로 바꾸세요.
    """
    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    mp_fd = mp.solutions.face_detection
    detector = mp_fd.FaceDetection(model_selection=0, min_detection_confidence=0.5)

    frame_cnt = 0
    detected_total = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_cnt += 1

        # BGR → RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = detector.process(rgb)
        if res.detections:
            detected_total += len(res.detections)

    cap.release()
    # 분석 끝난 원본 이동
    dst = PROCESSED_DIR / video_path.parent.name / video_path.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(video_path), str(dst))

    log("Analyzed locally", {
        "file": str(dst),
        "frames": frame_cnt,
        "faces_detected_total": detected_total
    })


def log(msg: str, extra=None):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg} :: {json.dumps(extra or {}, ensure_ascii=False)}", flush=True)


# 워커 스레드 시작
t = threading.Thread(target=worker_loop, daemon=True)
t.start()


if __name__ == "__main__":
    # HTTPS가 필요합니다(모바일 카메라 접근). 도메인에 TLS가 있다면 역프록시 뒤에 두세요.
    # 로컬 테스트(모바일 접속)엔 자체서명 인증서 사용:
    #   export SSL_CERTFILE=server.crt
    #   export SSL_KEYFILE=server.key
    cert = os.environ.get("SSL_CERTFILE")
    key = os.environ.get("SSL_KEYFILE")
    ssl_ctx = (cert, key) if (cert and key) else None

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    # 개발 편의를 위해 threaded=True
    app.run(host=host, port=port, ssl_context=ssl_ctx, threaded=True)
