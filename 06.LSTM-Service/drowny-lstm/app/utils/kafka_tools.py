# -*- coding: utf-8 -*-
import time
from confluent_kafka import Consumer

def topic_exists(bootstrap: str, topic: str, timeout_sec: float = 3.0) -> bool:
    """
    브로커 메타데이터로 토픽 존재/파티션 유무 확인.
    """
    c = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": "topic-checker",
        "session.timeout.ms": 6000,
        "enable.auto.commit": False,
    })
    try:
        md = c.list_topics(topic=topic, timeout=timeout_sec)
        tmd = md.topics.get(topic)
        if tmd is None:
            return False
        if tmd.error is not None:
            # 존재하나 에러(unknown topic or partition 등) → 사용 불가로 간주
            return False
        # 파티션이 0이면 아직 완전히 준비되지 않은 것으로 간주
        return len(tmd.partitions) > 0
    except Exception:
        return False
    finally:
        try:
            c.close()
        except Exception:
            pass

def wait_for_topic_or_fail(bootstrap: str, topic: str, total_wait_sec: int, interval_sec: int) -> None:
    """
    토픽이 아직 없으면 1초 간격으로 재시도, total_wait_sec 까지 대기.
    실패 시 RuntimeError 발생.
    """
    waited = 0
    while waited < total_wait_sec:
        if topic_exists(bootstrap, topic, timeout_sec=2.0):
            return
        time.sleep(interval_sec)
        waited += interval_sec
    raise RuntimeError(f"Topic '{topic}' not found or not ready within {total_wait_sec}s")
