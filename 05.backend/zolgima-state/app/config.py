import os
import logging

KAFKA_BOOTSTRAP_SERVERS='kafka.dongango.com:9094'
MYSQL_URL='mysql+pymysql://class5:zmffotm5@mysql.dongango.com:3306/ai3class5?charset=utf8mb4'
TOPIC_WAIT_MAX_SEC = 60   # 최대 5분 대기
TOPIC_WAIT_INTERVAL_SEC  = 1

# Kafka
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka.dongango.com:9094")
KAFKA_CONTROL_TOPIC = os.getenv("KAFKA_CONTROL_TOPIC", "zolgima-control")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM")
KAFKA_USERNAME = os.getenv("KAFKA_USERNAME")
KAFKA_PASSWORD = os.getenv("KAFKA_PASSWORD")

# LSTM 윈도우/프레임 시간 계산
FRAMES_PER_SEC = float(os.getenv("FRAMES_PER_SEC", "24"))

# MySQL (SQLAlchemy URL)
MYSQL_URL = os.getenv(
    "MYSQL_URL",
    "mysql+pymysql://class5:zmffotm5@mysql.dongango.com:3306/ai3class5?charset=utf8mb4",
)

# LLM 연동(옵션)
LLM_SERVICE_BASE = os.getenv("LLM_SERVICE_BASE")  # e.g. http://llm-service:8000

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(threadName)s %(name)s: %(message)s",
)
LOGGER_NAME = "zolgima-state-service"
