
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import threading, time
import os

from frame_reader import JPEGFolderReader, FrameSpec
from mediapipe_analyzer import MediaPipeAnalyzer
from kafka_client import KafkaJSONProducer
from storage import StateStore

from metrics import MetricsTracker
from config import EAR_CLOSED_TH, YAWN_MAR_TH, BLINK_MIN_CLOSED_FRAMES, RATE_WINDOW_SEC

ear_sample = []
mar_sample = []


@dataclass
class WorkerConfig:
    jpeg_dir: str
    topic: str
    fps: float
    width: Optional[int]
    height: Optional[int]
    kafka_conf: Dict[str, Any]
    resume: bool = True
    poll_interval_sec: float = 0.02

class StreamWorker(threading.Thread):
    def __init__(self, cfg: WorkerConfig, state: StateStore):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.state = state
        self._stop = threading.Event()
        self.frames_emitted = 0
        self.last_frame_idx: int = 0
        self.last_ts_ms: Optional[int] = None
        self.started_at_ms = int(time.time() * 1000)
        self._ear_samples = []
        self._mar_samples = []
        self._calib_frames = 15  # 캘리브레이션 프레임 수
        self._thresholds = {
            "EAR_CLOSED_TH": EAR_CLOSED_TH,
            "EAR_OPEN_TH": EAR_CLOSED_TH * 1.25,  # 열림 임계 (임의 설정)
            "YAWN_MAR_TH": YAWN_MAR_TH,
        }

        self._reader = JPEGFolderReader(
            cfg.jpeg_dir, FrameSpec(cfg.width, cfg.height, cfg.fps),
            poll_interval_sec=cfg.poll_interval_sec,
        )
        self._an = MediaPipeAnalyzer()
        self._prod = KafkaJSONProducer(cfg.kafka_conf)
        self._tracker = MetricsTracker(
            fps=cfg.fps,
            ear_closed_th=EAR_CLOSED_TH,
            yawn_mar_th=YAWN_MAR_TH,
            min_closed_frames=BLINK_MIN_CLOSED_FRAMES,
            rate_window_sec=RATE_WINDOW_SEC,
        )

        # resume frame index if any
        if cfg.resume:
            last = self.state.load_last(cfg.topic)
            if last and isinstance(last.get("frame"), int):
                self.last_frame_idx = int(last["frame"])
                # Start next frame as last+1 (even if underlying jpeg starts at 1)
                # We'll keep an independent monotonic frame counter for Kafka records.
        self._out_frame_idx = self.last_frame_idx + 1

    def _build_metrics(self, res, ts_ms, threshold=None):
        snap = self._tracker.update(res.ear_mean, res.mar, ts_ms, thresholds=threshold)
        return {
            "label_name": snap.label_name,
            "EAR": snap.EAR,
            "MAR": snap.MAR,
            "yawn_rate_per_min": snap.yawn_rate_per_min,
            "blink_rate_per_min": snap.blink_rate_per_min,
            "avg_blink_dur_sec": snap.avg_blink_dur_sec,
            "longest_eye_closure_sec": snap.longest_eye_closure_sec,

            # (원시 피처도 함께 유지해 드립니다)
            "ear_left": res.ear_left,
            "ear_right": res.ear_right,
            "ear_mean": res.ear_mean,
            "mar": res.mar,
            "face_found": res.face_found,
        }
    
    def _estimate_thresholds(self):
        import numpy as np
        ear_arr = np.array([v for v in self._ear_samples if v is not None])
        mar_arr = np.array([v for v in self._mar_samples if v is not None])
        # 예시: median 기반
        ear_med = float(np.median(ear_arr)) if len(ear_arr) > 0 else self._thresholds["EAR_CLOSED_TH"]
        mar_med = float(np.median(mar_arr)) if len(mar_arr) > 0 else self._thresholds["YAWN_MAR_TH"]
        return {
            "EAR_CLOSED_TH": ear_med * 0.85,  # 닫힘 임계
            "EAR_OPEN_TH": ear_med * 1.05,    # 열림 임계(필요시)
            "YAWN_MAR_TH": mar_med * 1.25,    # 하품 임계
        }
        
    def stop(self):
        self._stop.set()

    def run(self):
        try:
            for idx, ts_ms, frame, src_path in self._reader:
                if self._stop.is_set():
                    break

                # 1. 항상 임계치로 분석/produce
                res = self._an.analyze_frame(frame, thresholds=self._thresholds)
                # 2. 캘리브레이션 샘플 쌓기
                self._ear_samples.append(res.ear_mean)
                self._mar_samples.append(res.mar)

                # 3. 지정 프레임 쌓이면 임계치 갱신 (단 1회만)
                if len(self._ear_samples) == self._calib_frames:
                    self._thresholds = self._estimate_thresholds()
                    self._tracker.ear_closed_th = self._thresholds["EAR_CLOSED_TH"]
                    self._tracker.yawn_mar_th = self._thresholds["YAWN_MAR_TH"]

                # Build record
                record = {
                    "topic": self.cfg.topic,
                    "frame": self._out_frame_idx,
                    "source_idx": idx,            # index from filename
                    "timestamp_ms": ts_ms,
                    "rel_time_sec": round((self._out_frame_idx-1) / self.cfg.fps, 6),
                    "metrics": self._build_metrics(res, ts_ms, threshold=self._thresholds),
                    # (신규) 캘리브레이션으로 추정된 임계치 정보 포함
                }
                self._prod.produce_json(self.cfg.topic, record)
                self.frames_emitted += 1
                self.last_frame_idx = self._out_frame_idx
                self.last_ts_ms = ts_ms
                self._out_frame_idx += 1

                # Persist last
                if self.frames_emitted % 10 == 0:
                    self.state.save_last(self.cfg.topic, record)

                # (신규) 처리 완료한 원본 파일 rename: completed-<원래파일명>
                try:
                    dirname, base = os.path.split(src_path)
                    new_path = os.path.join(dirname, f"completed-{base}")
                    # 이미 완료 표시된 파일이라면 skip
                    if not os.path.basename(src_path).startswith("completed-"):
                        # 기존에 동일 이름 있으면 덮어쓰기 회피
                        if os.path.exists(new_path):
                            # 중복 방지: completed-<base>.<epoch>
                            import time as _t
                            new_path = os.path.join(dirname, f"completed-{int(_t.time())}-{base}")
                        os.replace(src_path, new_path)
                except Exception as e:
                    # rename 실패는 치명 아님 → 로그만
                    print(f"[worker:{self.cfg.topic}] rename failed for {src_path}: {e}")

        finally:
            # Persist last on exit and flush
            if self.last_frame_idx > 0:
                self.state.save_last(self.cfg.topic, {
                    "topic": self.cfg.topic,
                    "frame": self.last_frame_idx,
                    "timestamp_ms": self.last_ts_ms,
                })
            try:
                self._prod.flush(2.0)
            except Exception:
                pass
            try:
                self._an.close()
            except Exception:
                pass
