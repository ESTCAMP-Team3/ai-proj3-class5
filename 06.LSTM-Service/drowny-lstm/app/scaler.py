# -*- coding: utf-8 -*-
from typing import Tuple
import numpy as np

def load_scaler(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """훈련 시 저장한 mean/std 로드"""
    s = np.load(path)
    return s["mean"].astype(np.float32), s["std"].astype(np.float32)

def apply_standardizer(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """X: (B, T, C) 에 채널별 표준화 적용"""
    return (X - mean) / std
