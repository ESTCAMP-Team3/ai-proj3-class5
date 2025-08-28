import json
import logging
import threading
from typing import Dict

from config import LOGGER_NAME, KAFKA_CONTROL_TOPIC
from db import create_mysql_engine
from kafka_utils import build_consumer, subscribe_seek_end
from session_worker import SessionWorker

logger = logging.getLogger(LOGGER_NAME)

class ControlService:
    """
    컨트롤 토픽(zolgima-control)에서 start/stop 이벤트를 읽고
    세션 워커 생성/종료를 관리
    """
    def __init__(self, engine=None):
        self.engine = engine or create_mysql_engine()
#        self.consumer = build_consumer("zolgima-state-control")
        self.consumer = build_consumer("zolgima-state-control-test")
        subscribe_seek_end(self.consumer, [KAFKA_CONTROL_TOPIC])
        self.workers: Dict[str, SessionWorker] = {}
        self.lock = threading.Lock()

    def start(self):
        logger.info(f"Control listening on topic={KAFKA_CONTROL_TOPIC}")
        while True:
            msg = self.consumer.poll(0.5)
            if msg is None:
                continue
            if msg.error():
                logger.warning(f"Control kafka error: {msg.error()}")
                continue

            key = (msg.key() or b"").decode("utf-8", errors="ignore")
            val_raw = (msg.value() or b"").decode("utf-8", errors="ignore")
            try:
                val = json.loads(val_raw) if val_raw else {}
            except Exception:
                val = {}

            session_token = val.get("session_token") or val.get("session_token")
            session_id = val.get("session-id") or val.get("session_id")
            user_id = int(val.get("user_id", 0))

            if not session_id:
                logger.warning(f"Control event missing session-id: key={key} value={val_raw}")
                continue

            if key == "start-stream":
                self._start_session(session_id, user_id, session_token)
            elif key == "stop-stream":
                self._stop_session(session_id, session_token)
            else:
                logger.info(f"Ignored control key={key} session={session_id}")

    def _start_session(self, session_id: str, user_id: int, session_token: str = None):
        with self.lock:
            if session_id in self.workers:
                logger.info(f"[{session_id}] already running; ignoring start")
                return
            w = SessionWorker(session_id=session_id, user_id=user_id, seesion_token=session_token, engine=self.engine)
            
            self.workers[session_id] = w
            w.start()

    def _stop_session(self, session_id: str):
        with self.lock:
            w = self.workers.pop(session_id, None)
            if w:
                w.stop()
                logger.info(f"[{session_id}] stopping worker...")
            else:
                logger.info(f"[{session_id}] not running; ignoring stop")
