# -*- coding: utf-8 -*-
import signal
import tensorflow as tf
from scaler import load_scaler
from manager import SessionManager
from config import (
    KAFKA_BOOTSTRAP, MODEL_PATH, SCALER_PATH,
)

def main():
    print("[boot] loading model & scaler...")
    model = tf.keras.models.load_model(MODEL_PATH)
    mean, std = load_scaler(SCALER_PATH)
    print("[boot] model/scaler ready.")

    mgr = SessionManager(
        kafka_bootstrap=KAFKA_BOOTSTRAP,
        model=model,
        mean=mean,
        std=std,
    )

    def _sig_handler(sig, frame):
        mgr.shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    mgr.start()

if __name__ == "__main__":
    main()
