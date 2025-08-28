# app/session_worker.py
import json
import logging
import threading
import time
from typing import Optional

from confluent_kafka import Consumer, KafkaError

from config import LOGGER_NAME
from kafka_utils import (
    build_consumer, subscribe_seek_end, is_partition_eof,
    wait_for_topic_exists, topic_exists
)
from fsm import SessionFSM

logger = logging.getLogger(LOGGER_NAME)

class SessionWorker(threading.Thread):
    def __init__(self, session_id: str, user_id: int, seesion_token: str, engine: "Engine"):
        super().__init__(name=f"worker-{session_id}", daemon=True)
        self.session_id = session_id
        self.user_id = user_id
        self.session_token = seesion_token
        self.engine = engine
        self.stop_flag = threading.Event()
        self.consumer: Optional[Consumer] = None
        self.fsm = SessionFSM(session_id=session_id, user_id=user_id, session_token=seesion_token, engine=engine)

    def stop(self):
        self.stop_flag.set()

    def _open_consumer(self, topic: str):
        """
        토픽이 나타날 때까지 대기한 뒤 컨슈머를 만들고 최신 오프셋으로 구독
        """
        wait_for_topic_exists(topic)  # 타임아웃 시에도 False 반환하지만 계속 진행(아래에서 재시도 로직)
        # self.consumer = build_consumer(group_id=f"zolgima-state-test-{self.session_id}")
        self.consumer = build_consumer(group_id=f"zolgima-state-test")
        subscribe_seek_end(self.consumer, [topic])
        logger.info(f"[{self.session_id}] consuming {topic} ...")

    def _close_consumer(self):
        if self.consumer:
            try:
                self.consumer.close()
            except Exception:
                pass
            self.consumer = None

    def run(self):
        topic = f"{self.session_id}-LSTM"

        # 초기 오픈(토픽 대기 후 구독)
        self._open_consumer(topic)

        backoff_sec = 1.0
        max_backoff = 10.0

        try:
            while not self.stop_flag.is_set():
                if self.consumer is None:
                    # 토픽 재등장 대기 → 재구독
                    if topic_exists(topic):
                        try:
                            self._open_consumer(topic)
                            backoff_sec = 1.0  # 성공 시 백오프 리셋
                        except Exception as e:
                            logger.warning(f"[{self.session_id}] reopen failed: {e}")
                            time.sleep(backoff_sec)
                            backoff_sec = min(max_backoff, backoff_sec * 2)
                            continue
                    else:
                        time.sleep(backoff_sec)
                        backoff_sec = min(max_backoff, backoff_sec * 2)
                        continue

                msg = self.consumer.poll(0.5)
                if msg is None:
                    continue

                if msg.error():
                    err = msg.error()
                    # 토픽/파티션 미존재: 토픽 생길 때까지 재대기 → 재구독

                    err = msg.error()
                    # 토픽/파티션 미존재: 토픽 생길 때까지 대기 후 재구독
                    if err.code() == KafkaError._UNKNOWN_TOPIC_OR_PART:
                        logger.warning(f"[{self.session_id}] topic missing, will wait & resubscribe: {err}")
                        self._close_consumer()
                        continue
                    
                    #if err.erro() == KafkaException._UNKNOWN_TOPIC_OR_PART or \
                    #   getattr(err, "name", lambda: "")() == "UNKNOWN_TOPIC_OR_PART":
                    #    logger.warning(f"[{self.session_id}] topic missing, will wait & resubscribe: {err}")
                    #    self._close_consumer()
                    #    # 다음 루프에서 topic_exists를 보며 재시도
                        continue

                    if is_partition_eof(err):
                        continue

                    logger.warning(f"[{self.session_id}] Kafka error: {err}")
                    continue

                # 정상 메시지 처리
                try:
                    payload = msg.value()
                    print("topic-lstm-mesage - payload : ", payload)
                    if not payload:
                        continue
                    data = json.loads(payload.decode("utf-8", errors="ignore"))

                    frame = data.get("frame")
                    if isinstance(frame, str) and frame.isdigit():
                        frame = int(frame)
                    elif isinstance(frame, (int, float)):
                        frame = int(frame)
                    else:
                        frame = None

                    dl = data.get("drowny-level")
                    if dl is None:
                        dl = data.get("drowny_level")
                    if isinstance(dl, str) and dl.lstrip("-").isdigit():
                        dl = int(dl)
                    elif not isinstance(dl, int):
                        continue

                    self.fsm.feed(frame=frame, drowny_level=dl)
                except Exception as e:
                    logger.exception(f"[{self.session_id}] message handling failed: {e}")

        finally:
            self._close_consumer()
            logger.info(f"[{self.session_id}] worker stopped.")
