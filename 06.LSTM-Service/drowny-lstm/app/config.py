# -*- coding: utf-8 -*-

# 공통 설정
KAFKA_BOOTSTRAP = "kafka.dongango.com:9094"
CONTROL_TOPIC = "zolgima-control"
GROUP_ID = "drowny-lstm-consumer"

MODEL_PATH = "../../model.keras"
SCALER_PATH = "../../scaler_mean_std.npz"

FEATURE_COLS = [
    "EAR", "MAR",
    "yawn_rate_per_min", "blink_rate_per_min",
    "avg_blink_dur_sec", "longest_eye_closure_sec",
]

# 5초(150frame @30fps), 1초 hop(30frame)
SEQ_LEN = 150
HOP = 30

# softmax index -> 실제 레이블 매핑
CLS_LEVELS = [-1, 0, 1, 2, 3]

# 토픽 존재 대기 로직
TOPIC_WAIT_TOTAL_SEC = 60
TOPIC_WAIT_INTERVAL_SEC = 1
