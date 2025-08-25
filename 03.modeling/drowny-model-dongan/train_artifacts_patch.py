"""
train_artifacts_patch.py
------------------------
Drop this module into your training environment (or %run it in a notebook) and call:

    from train_artifacts_patch import save_artifacts

    save_artifacts(
        model,                          # Trained tf.keras model
        scaler=scaler,                  # Optional: sklearn/StandardScaler or similar; can be None
        feature_names=feature_names,    # List[str] in the exact order your model expects
        meta=dict(
            project="drowny",
            version="v1",
            window_sec=5.0,
            hop_sec=1.0,
            sampling_hz=30.0,           # or your actual sampling rate (frames/s or messages/s)
            seq_len=None,               # if known; otherwise will be inferred from model input
            label_map={
                "0": "awake",
                "1": "early_drowsy",
                "2": "drowsy",
                "3": "very_drowsy"
            },
        ),
        out_dir="artifacts/drowny-v1"   # any folder; will be created
    )

This will save:
- model:            model.keras  (TensorFlow SavedModel-in-.keras container)
- optional scaler:  scaler.joblib (if provided)
- metadata:         meta.json    (feature names, seq_len, window/sec, label map, etc.)

You can later point the realtime service (kafka_infer_service.py) to this folder.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

def _infer_seq_len_from_model(model) -> Optional[int]:
    """
    Try to infer (timesteps, feat_dim) from model.input_shape.
    Works for common shapes like (None, T, F) or (T, F).
    """
    try:
        ish = getattr(model, "input_shape", None)
        if ish is None:
            return None
        # Accept single-input models only for simplicity
        if isinstance(ish, (list, tuple)) and isinstance(ish[0], (list, tuple)):
            # Some models return [ (None, T, F) ]
            ish = ish[0]
        # ish like (None, T, F) or (T, F)
        if len(ish) == 3:
            # (batch, T, F)
            return ish[1]
        if len(ish) == 2:
            # (T, F)
            return ish[0]
    except Exception:
        pass
    return None

def save_artifacts(
    model,
    scaler=None,
    feature_names: Sequence[str] = (),
    meta: Optional[Dict[str, Any]] = None,
    out_dir: str = "artifacts",
):
    """
    Save model + optional scaler + metadata for realtime inference.

    Parameters
    ----------
    model : tf.keras.Model
    scaler : Optional[sklearn-like] — must implement .transform(X) if used
    feature_names : List[str] in the *exact* order expected by the model
    meta : Dict with keys like:
        - project, version
        - window_sec, hop_sec, sampling_hz
        - seq_len (optional, inferred if missing)
        - label_map: Dict[str_label_id] -> name
        - thresholds (optional) — e.g., per-class thresholds if you use them
    out_dir : output folder
    """
    import tensorflow as tf
    from joblib import dump

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1) Save model (.keras)
    model_path = out / "model.keras"
    model.save(model_path)
    print(f"[save_artifacts] Saved model -> {model_path}")

    # 2) Save scaler if provided
    scaler_path = None
    if scaler is not None:
        scaler_path = out / "scaler.joblib"
        dump(scaler, scaler_path)
        print(f"[save_artifacts] Saved scaler -> {scaler_path}")

    # 3) Build metadata
    meta = dict(meta or {})
    # ensure feature names
    meta["feature_names"] = list(feature_names)
    # seq_len
    if not meta.get("seq_len"):
        meta["seq_len"] = _infer_seq_len_from_model(model)
    # model info
    meta["model"] = {
        "format": ".keras",
        "path": "model.keras",
    }
    # scaler info
    if scaler_path is not None:
        meta["scaler"] = {
            "path": "scaler.joblib",
            "type": type(scaler).__name__,
        }
    else:
        meta["scaler"] = None

    # save meta.json
    meta_path = out / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[save_artifacts] Saved meta -> {meta_path}")

    print("[save_artifacts] DONE.")