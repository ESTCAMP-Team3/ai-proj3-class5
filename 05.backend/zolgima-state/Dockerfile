# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl tini && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

# ENV KAFKA_BOOTSTRAP_SERVERS="kafka.dongango.com:9094" \
#    KAFKA_CONTROL_TOPIC="zolgima-control" \
#    FRAMES_PER_SEC="24" \
#    MYSQL_URL="mysql+pymysql://class5:zmffotm5@mysql.dongango.com:3306/ai3class5?charset=utf8mb4" \
#    LOG_LEVEL="INFO"

# ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/app/app.py"]
