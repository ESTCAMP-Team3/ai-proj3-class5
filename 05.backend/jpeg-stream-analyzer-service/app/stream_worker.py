
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import threading, time

from .frame_reader import JPEGFolderReader, FrameSpec
from .mediapipe_analyzer import MediaPipeAnalyzer
from .kafka_client import KafkaJSONProducer
from .storage import StateStore

from .metrics import MetricsTracker
from .config import EAR_CLOSED_TH, YAWN_MAR_TH, BLINK_MIN_CLOSED_FRAMES, RATE_WINDOW_SEC


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

    def _build_metrics(self, res, ts_ms):
        snap = self._tracker.update(res.ear_mean, res.mar, ts_ms)
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
        
    def stop(self):
        self._stop.set()

    def run(self):
        try:
            for idx, ts_ms, frame in self._reader:
                if self._stop.is_set():
                    break
                # Analyze
                res = self._an.analyze_frame(frame)
                # Build record
                record = {
                    "topic": self.cfg.topic,
                    "frame": self._out_frame_idx,
                    "source_idx": idx,            # index from filename
                    "timestamp_ms": ts_ms,
                    "rel_time_sec": round((self._out_frame_idx-1) / self.cfg.fps, 6),
                    "metrics": self._build_metrics(res, ts_ms),
                }
                self._prod.produce_json(self.cfg.topic, record)
                self.frames_emitted += 1
                self.last_frame_idx = self._out_frame_idx
                self.last_ts_ms = ts_ms
                self._out_frame_idx += 1

                # Persist last
                if self.frames_emitted % 10 == 0:
                    self.state.save_last(self.cfg.topic, record)
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
