from dataclasses import dataclass
from collections import deque
from typing import Optional
import math

@dataclass
class MetricsSnapshot:
    label_name: str
    EAR: float
    MAR: float
    yawn_rate_per_min: float
    blink_rate_per_min: float
    avg_blink_dur_sec: float
    longest_eye_closure_sec: float

class MetricsTracker:
    """
    간단한 상태기계:
    - Blink: eyes open → closed(연속 N 프레임 이상) → open 이면 1회로 집계, duration 누적
    - Yawn: MAR 임계치 이상 프레임 발생 시 이벤트로 집계(간단 디바운스)
    - Rate: 최근 RATE_WINDOW_SEC 만큼의 이벤트 수를 '분당'으로 환산
    """
    def __init__(self, fps: float, ear_closed_th: float, yawn_mar_th: float,
                 min_closed_frames: int = 2, rate_window_sec: float = 60.0):
        self.fps = fps
        self.ear_closed_th = ear_closed_th
        self.yawn_mar_th = yawn_mar_th
        self.min_closed_frames = min_closed_frames
        self.rate_window_sec = rate_window_sec

        self.closed_run = 0
        self.longest_closure_sec = float('nan')

        self._blink_times = deque()      # epoch sec
        self._blink_durs = deque()       # sec
        self._yawn_times = deque()       # epoch sec

    def _prune(self, now_sec: float):
        # 오래된 이벤트 제거
        while self._blink_times and now_sec - self._blink_times[0] > self.rate_window_sec:
            self._blink_times.popleft()
            self._blink_durs.popleft()
        while self._yawn_times and now_sec - self._yawn_times[0] > self.rate_window_sec:
            self._yawn_times.popleft()

    def update(self, ear_mean: Optional[float], mar: Optional[float], ts_ms: int) -> MetricsSnapshot:
        now_sec = ts_ms / 1000.0

        # 눈 상태 판정 + blink 집계
        if ear_mean is not None and ear_mean < self.ear_closed_th:
            self.closed_run += 1
        else:
            if self.closed_run >= self.min_closed_frames:
                dur = self.closed_run / self.fps
                self._blink_times.append(now_sec)
                self._blink_durs.append(dur)
                if math.isnan(self.longest_closure_sec) or dur > self.longest_closure_sec:
                    self.longest_closure_sec = dur
            self.closed_run = 0

        # yawn 집계 (간단 디바운스: 1초 이내 중복 방지)
        if mar is not None and mar >= self.yawn_mar_th:
            if not self._yawn_times or (now_sec - self._yawn_times[-1]) > 1.0:
                self._yawn_times.append(now_sec)

        # 윈도우 정리 + 분당 환산
        self._prune(now_sec)
        blink_rate = len(self._blink_times) * (60.0 / max(self.rate_window_sec, 1e-6))
        yawn_rate = len(self._yawn_times) * (60.0 / max(self.rate_window_sec, 1e-6))
        avg_blink = float('nan') if not self._blink_durs else sum(self._blink_durs)/len(self._blink_durs)

        label = "eyes_state/open"
        if ear_mean is not None and ear_mean < self.ear_closed_th:
            label = "eyes_state/closed"

        return MetricsSnapshot(
            label_name=label,
            EAR=ear_mean if ear_mean is not None else float('nan'),
            MAR=mar if mar is not None else float('nan'),
            yawn_rate_per_min=yawn_rate,
            blink_rate_per_min=blink_rate,
            avg_blink_dur_sec=avg_blink,
            longest_eye_closure_sec=self.longest_closure_sec,
        )
