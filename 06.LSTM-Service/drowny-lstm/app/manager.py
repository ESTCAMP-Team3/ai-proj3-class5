# -*- coding: utf-8 -*-
import json
from typing import Dict

import numpy as np
import tensorflow as tf
from confluent_kafka import Consumer, KafkaError

from worker import DrownyLSTMWorker
from config import (
    CONTROL_TOPIC, GROUP_ID,
    FEATURE_COLS, SEQ_LEN, HOP,
)

class SessionManager:
    """
    zolgima-control 토픽을 구독하여
    - key="start-stream": {"session-id": "..."} → 세션 워커 시작
    - key="stop-stream" : {"session-id": "..."} → 세션 워커 중지
    """
    def __init__(self, kafka_bootstrap: str, model: tf.keras.Model, mean: np.ndarray, std: np.ndarray):
        self.kafka_bootstrap = kafka_bootstrap
        self.model = model
        self.mean = mean
        self.std = std

        self.workers: Dict[str, DrownyLSTMWorker] = {}

        self.consumer = Consumer({
            "bootstrap.servers": self.kafka_bootstrap,
            "group.id": GROUP_ID,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        self.consumer.subscribe([CONTROL_TOPIC])

    def start(self):
        print("[manager] listening control topic:", CONTROL_TOPIC)
        try:
            while True:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        print("[manager] Kafka error:", msg.error())
                    continue

                key = msg.key().decode("utf-8") if msg.key() else ""
                try:
                    val = json.loads(msg.value().decode("utf-8"))
                except Exception:
                    val = {}

                session_id = val.get("session-id") or val.get("session_id") or val.get("sessionId")
                if not session_id:
                    continue

                if key == "start-stream":
                    self._start_session(session_id)
                elif key == "stop-stream":
                    self._stop_session(session_id)
                else:
                    # 기타 키는 무시
                    pass

        except KeyboardInterrupt:
            print("[manager] interrupted by user")
        finally:
            self.shutdown()

    def _start_session(self, session_id: str):
        if session_id in self.workers:
            print(f"[manager] session {session_id} already running")
            return

        input_topic = session_id
        output_topic = f"{session_id}-LSTM"
        worker = DrownyLSTMWorker(
            session_id=session_id,
            kafka_bootstrap=self.kafka_bootstrap,
            group_id=GROUP_ID,
            input_topic=input_topic,
            output_topic=output_topic,
            model=self.model,
            scaler_mean=self.mean,
            scaler_std=self.std,
            feature_cols=FEATURE_COLS,
            seq_len=SEQ_LEN,
            hop=HOP,
            input_key_filter=None,  # 필요 시 "drowniness_indicator"
        )
        try:
            worker.start()
        except RuntimeError as e:
            # 60초 내 토픽 준비 실패
            print(f"[manager] failed to start session {session_id}: {e}")
            return

        self.workers[session_id] = worker
        print(f"[manager] started session {session_id}")

    def _stop_session(self, session_id: str):
        worker = self.workers.pop(session_id, None)
        if worker:
            worker.stop()
            print(f"[manager] stopped session {session_id}")
        else:
            print(f"[manager] session {session_id} not found")

    def shutdown(self):
        print("[manager] shutting down...")
        try:
            self.consumer.close()
        except Exception:
            pass

        # 모든 워커 안전 종료
        for sid, w in list(self.workers.items()):
            try:
                w.stop()
            except Exception:
                pass
        self.workers.clear()
        print("[manager] bye.")
