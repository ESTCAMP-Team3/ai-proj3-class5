
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
import numpy as np
import cv2
import mediapipe as mp
from .config import MP_MAX_NUM_FACES, MP_MIN_DET_CONF, MP_MIN_TRACK_CONF, MP_STATIC_IMAGE_MODE

# FaceMesh landmark indices for EAR (approximate mapping from 468-pt mesh)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [263, 387, 385, 362, 380, 373]

# Mouth indices (simple MAR proxy using inner-lip vertical (13-14) over horizontal (61-291))
MOUTH_VERT = (13, 14)
MOUTH_HORZ = (61, 291)

def _dist(p1: np.ndarray, p2: np.ndarray) -> float:
    return float(np.linalg.norm(p1 - p2))

def _ear_from_points(landmarks_xy: np.ndarray, idx: list[int]) -> float:
    # EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)  with 6 pts [p1,p2,p3,p4,p5,p6]
    p = landmarks_xy[idx, :]
    A = _dist(p[1], p[5])
    B = _dist(p[2], p[4])
    C = _dist(p[0], p[3])
    if C == 0: return 0.0
    return (A + B) / (2.0 * C)

def _mar_from_points(landmarks_xy: np.ndarray) -> float:
    a = landmarks_xy[MOUTH_VERT[0]]
    b = landmarks_xy[MOUTH_VERT[1]]
    left = landmarks_xy[MOUTH_HORZ[0]]
    right = landmarks_xy[MOUTH_HORZ[1]]
    vert = _dist(a, b)
    horz = _dist(left, right)
    if horz == 0: return 0.0
    return vert / horz

@dataclass
class MPResult:
    face_found: bool
    ear_left: Optional[float]
    ear_right: Optional[float]
    ear_mean: Optional[float]
    mar: Optional[float]

class MediaPipeAnalyzer:
    def __init__(self):
        self._mp_face = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=MP_STATIC_IMAGE_MODE,
            max_num_faces=MP_MAX_NUM_FACES,
            refine_landmarks=True,
            min_detection_confidence=MP_MIN_DET_CONF,
            min_tracking_confidence=MP_MIN_TRACK_CONF,
        )

    def analyze_frame(self, frame_bgr) -> MPResult:
        # Input: BGR image (OpenCV)
        img_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = self._mp_face.process(img_rgb)
        if not res.multi_face_landmarks:
            return MPResult(False, None, None, None, None)
        face = res.multi_face_landmarks[0]
        h, w = img_rgb.shape[:2]
        # Convert landmarks to (x,y)
        xy = np.array([(lm.x * w, lm.y * h) for lm in face.landmark], dtype=np.float32)
        ear_l = _ear_from_points(xy, LEFT_EYE)
        ear_r = _ear_from_points(xy, RIGHT_EYE)
        mar = _mar_from_points(xy)
        ear_m = (ear_l + ear_r) / 2.0 if (ear_l is not None and ear_r is not None) else None
        return MPResult(True, ear_l, ear_r, ear_m, mar)

    def close(self):
        self._mp_face.close()
