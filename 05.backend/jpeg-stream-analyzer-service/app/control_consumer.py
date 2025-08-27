# app/control_consumer.py
from __future__ import annotations
import json
import threading
import time
from typing import Optional

from confluent_kafka import Consumer, KafkaException

from models import StartStreamRequest, KafkaConfig
from manager import StreamManager

class ControlConsumerThread(threading.Thread):
    """
    'zolgima-control' 토픽의 컨트롤 메시지를 소비하여
    - key: 'start-stream' → 스트림 시작
    - key: 'stop-stream'  → 스트림 종료
    value(JSON): {"session-id": "<id>"}
    를 처리합니다.
    """
    def __init__(
        self,
        mgr: StreamManager,
        bootstrap_servers: str = "kafka.dongango.com:9094",
        topic: str = "zolgima-control",
        group_id: str = "zolgima-mpipe",
        metrics_topic_prefix: str = "",   # 빈문자열이면 metrics topic= session-id
        default_fps: float = 30.0,
        default_width: int | None = None,
        default_height: int | None = None,
    ):
        super().__init__(daemon=True)
        self.mgr = mgr
        self.topic = topic
        self.metrics_topic_prefix = metrics_topic_prefix
        self.default_fps = default_fps
        self.default_width = default_width
        self.default_height = default_height
        self._stop = threading.Event()

        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "enable.auto.commit": True,
            "auto.offset.reset": "latest",  # 처음 접속 시 기존 데이터 무시, 최신부터 수신
        })

    def stop(self):
        self._stop.set()

    def _metrics_topic_for(self, session_id: str) -> str:
        return f"{self.metrics_topic_prefix}{session_id}" if self.metrics_topic_prefix else session_id

    def run(self):
        self.consumer.subscribe([self.topic])
        try:
            while not self._stop.is_set():
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    # 파티션 EOF 등은 무시
                    if msg.error().code() == KafkaException._PARTITION_EOF:
                        continue
                    # 기타 에러는 로그만
                    print(f"[control-consumer] Kafka error: {msg.error()}")
                    continue

                try:
                    key = msg.key().decode("utf-8").strip() if msg.key() else ""
                    val = msg.value().decode("utf-8") if msg.value() else "{}"
                    payload = json.loads(val) if val else {}
                    session_id = str(payload.get("session-id", "")).strip()
                    if not session_id:
                        print(f"[control-consumer] invalid payload (no session-id): {val}")
                        continue

                    # JPEG 폴더 경로: data/output/{session-id}
                    jpeg_dir = f"./data/outbox/{session_id}"
                    # jpeg_dir = f"../../../04.LLM-Service/LLM_dongan_stream/app/data/outbox/{session_id}"
                    topic = self._metrics_topic_for(session_id)

                    if key == "start-stream":
                        req = StartStreamRequest(
                            jpeg_dir=jpeg_dir,
                            kafka=KafkaConfig(bootstrap_servers=self.consumer.list_topics().orig_broker_name
                                              if hasattr(self.consumer.list_topics(), 'orig_broker_name')
                                              else ""),  # 안전하게 명시
                            topic=topic,
                            fps=self.default_fps,
                            width=self.default_width,
                            height=self.default_height,
                            resume=True,
                        )
                        # bootstrap_servers 를 명시적으로 지정
                        req.kafka.bootstrap_servers = self.consumer.list_topics().orig_broker_name \
                            if hasattr(self.consumer.list_topics(), 'orig_broker_name') else "kafka.dongango.com:9094"

                        try:
                            self.mgr.start(req)
                            print(f"[control-consumer] started stream: session={session_id}, topic={topic}, dir={jpeg_dir}")
                        except Exception as e:
                            print(f"[control-consumer] start failed for {session_id}: {e}")

                    elif key == "stop-stream":
                        ok = self.mgr.stop(topic)
                        print(f"[control-consumer] stopped stream: session={session_id}, topic={topic}, ok={ok}")

                    else:
                        print(f"[control-consumer] unknown key: {key} payload={payload}")

                except Exception as e:
                    print(f"[control-consumer] exception handling message: {e}")

        finally:
            try:
                self.consumer.close()
            except Exception:
                pass
