
from pathlib import Path
from typing import Optional
import os

STATE_DIR = Path(os.environ.get("STATE_DIR", "./state")).resolve()
STATE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_POLL_INTERVAL_SEC = float(os.environ.get("POLL_INTERVAL_SEC", "0.02"))  # 20ms
DEFAULT_LOG_EVERY_N = int(os.environ.get("LOG_EVERY_N", "100"))

# Mediapipe
MP_STATIC_IMAGE_MODE = False
MP_MAX_NUM_FACES = 1
MP_MIN_DET_CONF = 0.5
MP_MIN_TRACK_CONF = 0.5

# Thresholds (환경변수로 조정 가능)
EAR_CLOSED_TH = float(os.environ.get("EAR_CLOSED_TH", "0.21"))  # ear_mean < TH ⇒ eyes closed
BLINK_MIN_CLOSED_FRAMES = int(os.environ.get("BLINK_MIN_CLOSED_FRAMES", "2"))
YAWN_MAR_TH = float(os.environ.get("YAWN_MAR_TH", "0.60"))
RATE_WINDOW_SEC = float(os.environ.get("RATE_WINDOW_SEC", "20.0"))  # per-minute 환산용 슬라이딩 윈도우
