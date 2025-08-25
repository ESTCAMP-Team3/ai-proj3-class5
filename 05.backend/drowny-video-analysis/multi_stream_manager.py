# multi_stream_manager.py
from __future__ import annotations
import time
import signal
import threading
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional, Literal
from multiprocessing import Process, get_start_method, set_start_method

from jpeg_drowny_service import DrownyJPEGService

Mode = Literal["thread", "process"]

@dataclass
class StreamConfig:
    stream_id: str
    image_dir: str
    kafka_conf: Dict[str, Any]
    kafka_topic: str
    fps: int = 24
    frame_size: Tuple[int, int] = (1280, 720)
    start_frame: int = 1

# -----------------------
# 프로세스 워커 엔트리
# -----------------------
def _proc_entry(cfg: StreamConfig):
    """
    개별 스트림을 '프로세스'로 실행할 때의 엔트리 포인트.
    SIGTERM/SIGINT 수신 시 깨끗하게 종료.
    """
    svc = DrownyJPEGService()
    stop_evt = threading.Event()

    def _on_signal(sig, frame):
        stop_evt.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # 서비스 시작
    svc.start(
        image_dir=cfg.image_dir,
        kafka_conf=cfg.kafka_conf,
        kafka_topic=cfg.kafka_topic,
        fps=cfg.fps,
        frame_size=cfg.frame_size,
        start_frame=cfg.start_frame,
    )

    try:
        while not stop_evt.is_set():
            time.sleep(0.5)
    finally:
        svc.stop()

# -----------------------
# 스레드 워커 래퍼 (실제로는 내부에서 자체 스레드 2개를 돌리는 서비스 인스턴스)
# -----------------------
class _ThreadWorker:
    def __init__(self, cfg: StreamConfig):
        self.cfg = cfg
        self.svc = DrownyJPEGService()
        self._running = False

    def start(self):
        if self._running:
            return
        self.svc.start(
            image_dir=self.cfg.image_dir,
            kafka_conf=self.cfg.kafka_conf,
            kafka_topic=self.cfg.kafka_topic,
            fps=self.cfg.fps,
            frame_size=self.cfg.frame_size,
            start_frame=self.cfg.start_frame,
        )
        self._running = True

    def stop(self):
        if self._running:
            self.svc.stop()
            self._running = False

# -----------------------
# 멀티 스트림 매니저
# -----------------------
class MultiStreamManager:
    def __init__(self, mode: Mode = "thread"):
        """
        mode="thread": 한 프로세스 안에서 여러 스트림(서비스 인스턴스)을 스레드 기반으로 실행
        mode="process": 각 스트림을 별도 프로세스로 실행(격리도/안정성↑, 자원 사용량↑)
        """
        if mode not in ("thread", "process"):
            raise ValueError("mode must be 'thread' or 'process'")
        self.mode: Mode = mode
        self._threads: Dict[str, _ThreadWorker] = {}
        self._procs: Dict[str, Process] = {}

        # 프로세스 모드에서 맥/리눅스 호환성 보장 (특히 macOS에서 spawn 사용 권장)
        if self.mode == "process":
            try:
                if get_start_method(allow_none=True) is None:
                    set_start_method("spawn", force=True)
            except RuntimeError:
                pass  # 이미 설정됨

    def start_stream(self, cfg: StreamConfig) -> None:
        """
        스트림 시작. 같은 stream_id가 이미 있으면 무시/갱신은 stop 후 start 권장.
        """
        if self.mode == "thread":
            if cfg.stream_id in self._threads:
                print(f"[Manager] stream '{cfg.stream_id}' already running (thread).")
                return
            worker = _ThreadWorker(cfg)
            worker.start()
            self._threads[cfg.stream_id] = worker
            print(f"[Manager] started thread stream: {cfg.stream_id}")

        else:  # process
            if cfg.stream_id in self._procs and self._procs[cfg.stream_id].is_alive():
                print(f"[Manager] stream '{cfg.stream_id}' already running (process).")
                return
            p = Process(target=_proc_entry, args=(cfg,), daemon=True)
            p.start()
            self._procs[cfg.stream_id] = p
            print(f"[Manager] started process stream: {cfg.stream_id} pid={p.pid}")

    def stop_stream(self, stream_id: str, timeout: float = 10.0) -> None:
        """
        스트림 종료. (thread: 서비스 stop, process: SIGTERM/terminate)
        """
        if self.mode == "thread":
            w = self._threads.pop(stream_id, None)
            if w:
                w.stop()
                print(f"[Manager] stopped thread stream: {stream_id}")
            else:
                print(f"[Manager] stream '{stream_id}' not found (thread).")
        else:
            p = self._procs.get(stream_id)
            if p and p.is_alive():
                p.terminate()  # SIGTERM
                p.join(timeout=timeout)
                if p.is_alive():
                    p.kill()
                    p.join(timeout=3.0)
                self._procs.pop(stream_id, None)
                print(f"[Manager] stopped process stream: {stream_id}")
            else:
                self._procs.pop(stream_id, None)
                print(f"[Manager] stream '{stream_id}' not found/already dead (process).")

    def list_streams(self) -> Dict[str, str]:
        """
        실행중인 스트림 나열
        """
        if self.mode == "thread":
            return {sid: "running" for sid in self._threads.keys()}
        else:
            status = {}
            for sid, p in list(self._procs.items()):
                status[sid] = "running" if p.is_alive() else "dead"
                if not p.is_alive():
                    # 청소
                    self._procs.pop(sid, None)
            return status

    def stop_all(self):
        if self.mode == "thread":
            for sid in list(self._threads.keys()):
                self.stop_stream(sid)
        else:
            for sid in list(self._procs.keys()):
                self.stop_stream(sid)
