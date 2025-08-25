
from typing import Any, Dict, Optional
import json, time
from confluent_kafka import Producer

class KafkaJSONProducer:
    def __init__(self, conf: Dict[str, Any]):
        # Map our pydantic config into confluent_kafka Producer config
        cfg = {
            "bootstrap.servers": conf.get("bootstrap_servers"),
            "client.id": conf.get("client_id","jpeg-mp-service"),
            "enable.idempotence": True,
            "linger.ms": 5,
            "compression.type": "lz4",
        }
        sec = conf.get("security_protocol","PLAINTEXT").upper()
        cfg["security.protocol"] = sec
        if sec.startswith("SASL"):
            cfg["sasl.mechanism"] = conf.get("sasl_mechanism","SCRAM-SHA-256")
            cfg["sasl.username"] = conf.get("sasl_username")
            cfg["sasl.password"] = conf.get("sasl_password")
        self.producer = Producer(cfg)

    def produce_json(self, topic: str, payload: Dict[str, Any]):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.producer.produce(topic, value=data)
    
    def flush(self, timeout: float = 5.0):
        self.producer.flush(timeout)
