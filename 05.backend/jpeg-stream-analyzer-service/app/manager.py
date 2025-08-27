
from __future__ import annotations
from typing import Dict, Optional, Any, List
import threading

from models import StartStreamRequest, StreamStatus
from stream_worker import StreamWorker, WorkerConfig
from storage import StateStore

class StreamManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._workers: Dict[str, StreamWorker] = {}
        self._state = StateStore()

    def start(self, req: StartStreamRequest) -> str:
        cfg = WorkerConfig(
            jpeg_dir=req.jpeg_dir,
            topic=req.topic,
            fps=req.fps,
            width=req.width,
            height=req.height,
            kafka_conf=req.kafka.dict(),
            resume=req.resume,
        )
        with self._lock:
            if req.topic in self._workers and self._workers[req.topic].is_alive():
                raise RuntimeError(f"Stream for topic '{req.topic}' already running")
            w = StreamWorker(cfg, self._state)
            self._workers[req.topic] = w
            w.start()
        return req.topic

    def stop(self, topic: str) -> bool:
        with self._lock:
            w = self._workers.get(topic)
            if not w:
                return False
            w.stop()
            w.join(timeout=5.0)
            return True

    def status_all(self) -> List[StreamStatus]:
        with self._lock:
            out = []
            for t, w in self._workers.items():
                out.append(StreamStatus(
                    topic=t,
                    jpeg_dir=w.cfg.jpeg_dir,
                    fps=w.cfg.fps,
                    width=w.cfg.width,
                    height=w.cfg.height,
                    alive=w.is_alive(),
                    frames_emitted=w.frames_emitted,
                    last_frame_idx=w.last_frame_idx,
                    last_ts_ms=w.last_ts_ms,
                    started_at_ms=w.started_at_ms,
                ))
            return out

    def last_record(self, topic: str) -> Optional[dict]:
        return self._state.load_last(topic)
