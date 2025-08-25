
# JPEG Stream Mediapipe Analyzer (FastAPI)

서비스는 폴더에 순차적으로 생성되는 `000001.jpeg`, `000002.jpeg` ... 파일을 **실시간**으로 읽어
MediaPipe FaceMesh 기반 EAR/MAR을 계산하고 JSON을 **Kafka** 토픽으로 전송합니다.
여러 스트림(토픽)을 동시에 실행/중지/상태조회 할 수 있습니다.

## Python 환경
- Python 3.11 (Anaconda 권장)
- TensorFlow 2.16 공존 OK (본 서비스는 TF를 직접 사용하지 않음)
- OpenCV, Mediapipe, FastAPI, confluent-kafka

```bash
pip install -r requirements.txt
# 또는 conda env 에서 pip 사용
```

## 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

### 1) Start a stream
`POST /streams/start`

```json
{
  "jpeg_dir": "/path/to/jpegs/camA",
  "kafka": {
    "bootstrap_servers": "kafka.dongango.com:9094",
    "security_protocol": "SASL_PLAINTEXT",
    "sasl_mechanism": "SCRAM-SHA-256",
    "sasl_username": "user1",
    "sasl_password": "pass1"
  },
  "topic": "driver.camA",
  "fps": 30.0,
  "width": 640,
  "height": 360,
  "resume": true
}
```

### 2) Stop a stream
`POST /streams/stop`
```json
{ "topic": "driver.camA" }
```

### 3) List streams
`GET /streams`

### 4) Last record for a topic
`GET /streams/{topic}/last`

## 메시지 포맷 (Kafka)
```json
{
  "topic": "driver.camA",
  "frame": 1234,            // 서비스의 누적 프레임 (resume 시 이어짐)
  "source_idx": 1234,       // 파일명에서 유도한 원본 인덱스
  "timestamp_ms": 1724471000123,
  "rel_time_sec": 41.1,     // frame/fps
  "metrics": {
    "ear_left": 0.24,
    "ear_right": 0.25,
    "ear_mean": 0.245,
    "mar": 0.31,
    "face_found": true
  }
}
```

## 참고
- 토픽별 마지막 레코드는 `./state/<topic>.last.json` 에 보존되어 다음 실행 시 `frame`이 이어집니다.
- JPEG 파일은 **6자리 숫자** + `.jpeg/.jpg` 규칙을 가정합니다. (예: `000001.jpeg`)
- 도중에 파일이 생성중(쓰기중)인 경우 잠시 대기 후 재시도합니다.
```
