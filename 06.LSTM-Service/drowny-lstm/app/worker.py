# -*- coding: utf-8 -*-
import json
import threading
from collections import deque
from typing import Dict, Optional, List

import numpy as np
import tensorflow as tf
from confluent_kafka import Consumer, Producer, KafkaError

from scaler import apply_standardizer
from utils.kafka_tools import wait_for_topic_or_fail
from config import (
    SEQ_LEN, HOP, FEATURE_COLS, CLS_LEVELS,
    TOPIC_WAIT_TOTAL_SEC, TOPIC_WAIT_INTERVAL_SEC,
)

# 멀티 스레드 예측 시 안전성 확보용
_PREDICT_LOCK = threading.Lock()

class DrownyLSTMWorker:
    """
    세션(채널) 단위 LSTM 실시간 추론 워커
    - 입력 토픽이 아직 없을 때: 1초 간격 재시도, 60초까지 실패 시 종료
    - 150프레임 윈도우 → 표준화 → softmax 예측 → {session-id}-LSTM 으로 publish
    """
    def __init__(
        self,
        session_id: str,
        kafka_bootstrap: str,
        group_id: str,
        input_topic: str,
        output_topic: str,
        model: tf.keras.Model,
        scaler_mean: np.ndarray,
        scaler_std: np.ndarray,
        feature_cols: Optional[List[str]] = None,
        seq_len: int = SEQ_LEN,
        hop: int = HOP,
        input_key_filter: Optional[str] = None,  # 예: "drowniness_indicator"
    ):
        self.session_id = session_id
        self.kafka_bootstrap = kafka_bootstrap
        self.group_id = group_id
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.model = model
        self.mean = scaler_mean.astype(np.float32)
        self.std = scaler_std.astype(np.float32)
        self.feature_cols = feature_cols or FEATURE_COLS
        self.seq_len = seq_len
        self.hop = hop
        self.input_key_filter = input_key_filter

        # 버퍼
        self.window = deque(maxlen=self.seq_len)
        self.frames = deque(maxlen=self.seq_len)
        self._last_values: Dict[str, float] = {}

        # 제어
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"LSTMWorker-{session_id}", daemon=True)

        # Kafka 클라이언트
        common_conf = {
            "bootstrap.servers": self.kafka_bootstrap,
            "group.id": self.group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        }
        self.consumer = Consumer(common_conf)
        self.producer = Producer({"bootstrap.servers": self.kafka_bootstrap})

    def start(self):
        print(f"[{self.session_id}] wait for topic: {self.input_topic}")
        # ✅ 토픽 준비될 때까지 대기(1초 간격, 최대 60초)
        wait_for_topic_or_fail(
            self.kafka_bootstrap,
            self.input_topic,
            total_wait_sec=TOPIC_WAIT_TOTAL_SEC,
            interval_sec=TOPIC_WAIT_INTERVAL_SEC,
        )
        print(f"[{self.session_id}] topic ready: {self.input_topic}")

        self.consumer.subscribe([self.input_topic])
        self._stop_event.clear()
        self._thread.start()
        print(f"[{self.session_id}] worker started. input={self.input_topic}, output={self.output_topic}")

    def stop(self):
        print(f"[{self.session_id}] worker stopping...")
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        try:
            self.consumer.close()
        except Exception:
            pass
        print(f"[{self.session_id}] worker stopped.")

    # ---------- 내부 유틸 ----------

    def _extract_features(self, payload: dict) -> Optional[np.ndarray]:
        feats = []
        for col in self.feature_cols:
            v = payload.get(col)
            try:
                v = float(v)
                if np.isnan(v):
                    raise ValueError
            except Exception:
                v = self._last_values.get(col, 0.0)
            self._last_values[col] = v
            feats.append(v)
        return np.asarray(feats, dtype=np.float32)

    def _predict_and_publish(self):
        if len(self.window) < self.seq_len:
            return

        X = np.asarray(self.window, dtype=np.float32).reshape(1, self.seq_len, len(self.feature_cols))
        X = apply_standardizer(X, self.mean, self.std)

        with _PREDICT_LOCK:
            y_pred = self.model.predict(X, verbose=0)  # (1, 5)

        idx = int(np.argmax(y_pred, axis=1)[0])
        level = int(CLS_LEVELS[idx])
        last_frame = int(self.frames[-1])

        # 요구된 이중 배열 포맷
        out = {
            "frame": last_frame,
            "drowny-level": level
        }

        # publish (output topic은 브로커 설정에 따라 자동 생성될 수 있음)
        try:
            self.producer.produce(
                self.output_topic,
                key="drowny-lstm-result",
                value=json.dumps(out),
            )
            self.producer.poll(0)
            print(f"[{self.session_id}] publish => {out}")
        except BufferError:
            self.producer.flush(2.0)
            self.producer.produce(self.output_topic, key="drowny-lstm-result", value=json.dumps(out))

        # 슬라이딩(앞에서 30개 제거)
        for _ in range(self.hop):
            if self.window:
                self.window.popleft()
            if self.frames:
                self.frames.popleft()

    def _run(self):
        try:
            while not self._stop_event.is_set():
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        print(f"[{self.session_id}] Kafka error: {msg.error()}")
                    continue

                if self.input_key_filter:
                    k = msg.key().decode("utf-8") if msg.key() else ""
                    if k != self.input_key_filter:
                        continue

                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                except Exception as e:
                    print(f"[{self.session_id}] JSON decode error: {e}")
                    continue

                # 프레임 순서 체크
                try:
                    frame_no = int(payload.get("frame"))
                except Exception:
                    continue
                if len(self.frames) and frame_no <= self.frames[-1]:
                    continue

                feats = self._extract_features(payload)
                if feats is None:
                    continue

                self.window.append(feats)
                self.frames.append(frame_no)

                if len(self.window) == self.seq_len:
                    self._predict_and_publish()

        except Exception as e:
            print(f"[{self.session_id}] worker exception: {e}")
        finally:
            try:
                self.consumer.close()
            except Exception:
                pass
