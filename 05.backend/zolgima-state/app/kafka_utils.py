# app/kafka_utils.py
import logging, time
from confluent_kafka import Consumer, KafkaException, TopicPartition
from confluent_kafka.admin import AdminClient
from config import (
    KAFKA_BOOTSTRAP, KAFKA_SECURITY_PROTOCOL, KAFKA_SASL_MECHANISM,
    KAFKA_USERNAME, KAFKA_PASSWORD, LOGGER_NAME,
    TOPIC_WAIT_MAX_SEC, TOPIC_WAIT_INTERVAL_SEC
)

logger = logging.getLogger(LOGGER_NAME)

def build_consumer(group_id: str) -> Consumer:
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": group_id,
        "enable.auto.commit": True,
        "auto.offset.reset": "latest",
        "security.protocol": KAFKA_SECURITY_PROTOCOL,
    }
    if KAFKA_SECURITY_PROTOCOL.startswith("SASL"):
        if not (KAFKA_USERNAME and KAFKA_PASSWORD and KAFKA_SASL_MECHANISM):
            raise RuntimeError("SASL_* envs required for SASL_* protocol")
        conf.update({
            "sasl.mechanism": KAFKA_SASL_MECHANISM,
            "sasl.username": KAFKA_USERNAME,
            "sasl.password": KAFKA_PASSWORD,
        })
    return Consumer(conf)

def subscribe_seek_end(consumer: Consumer, topics):
    def on_assign(c, partitions):
        new_parts = []
        for p in partitions:
            low, high = c.get_watermark_offsets(p, timeout=5)
            new_parts.append(TopicPartition(p.topic, p.partition, high))
        c.assign(new_parts)
    consumer.subscribe(topics, on_assign=on_assign)

def is_partition_eof(err) -> bool:
    try:
        return err.code() == KafkaException._PARTITION_EOF
    except Exception:
        return False

# === 신규 추가 ===
def _admin_client() -> AdminClient:
    return AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})

def topic_exists(topic: str) -> bool:
    try:
        md = _admin_client().list_topics(timeout=5)
        t = md.topics.get(topic)
        return (t is not None) and (t.error is None)
    except Exception as e:
        logger.debug(f"metadata fetch failed while checking topic {topic}: {e}")
        return False

def wait_for_topic_exists(topic: str,
                          max_wait_sec: float = None,
                          interval_sec: float = None) -> bool:
    max_wait = TOPIC_WAIT_MAX_SEC if max_wait_sec is None else max_wait_sec
    interval = TOPIC_WAIT_INTERVAL_SEC if interval_sec is None else interval_sec

    start = time.time()
    while True:
        if topic_exists(topic):
            logger.info(f"Topic ready: {topic}")
            return True
        if time.time() - start >= max_wait:
            logger.warning(f"Topic wait timed out after {max_wait}s: {topic}")
            return False
        time.sleep(interval)
