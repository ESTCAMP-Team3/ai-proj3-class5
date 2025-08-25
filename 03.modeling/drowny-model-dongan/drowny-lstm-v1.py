# train_drowsiness_lstm.py
import os, re, json, math, random, shutil
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from collections import Counter

import tensorflow as tf
from tensorflow.keras import layers, models, callbacks, optimizers

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
tf.random.set_seed(RANDOM_SEED)

# =========================
# 1) 유틸 & 데이터셋 준비
# =========================

FEATURE_COLS = [
    "EAR",
    "MAR",
    "yawn_rate_per_min",
    "blink_rate_per_min",
    "avg_blink_dur_sec",
    "longest_eye_closure_sec",
]

# level: -1,0,1,2,3  -> 총 5클래스. (-1 포함)
CLS_LEVELS = [-1, 0, 1, 2, 3]
LEVEL_TO_INDEX = {lvl: i for i, lvl in enumerate(CLS_LEVELS)}
INDEX_TO_LEVEL = {i: lvl for lvl, i in LEVEL_TO_INDEX.items()}

def _safe_symlink(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(src.resolve(), dst)
    except Exception:
        # 윈도우/권한 이슈 대비: 복사로 폴백
        shutil.copy2(src, dst)

def scan_pairs(data_dir: Path) -> List[Tuple[Path, Path]]:
    """
    data_dir 아래의 CSV/JSON 쌍을 찾아 반환.
    파일명(확장자 제외)이 일치하면 쌍으로 간주.
    """
    csvs = {}
    jsons = {}
    for p in data_dir.glob("**/*"):
        if p.is_file():
            stem = p.stem  # 파일명(확장자 제외)
            if p.suffix.lower() == ".csv":
                csvs[stem] = p
            elif p.suffix.lower() == ".json":
                jsons[stem] = p
    pairs = []
    for stem, csv_path in csvs.items():
        if stem in jsons:
            pairs.append((csv_path, jsons[stem]))
    return sorted(pairs)

def split_and_link(pairs: List[Tuple[Path, Path]], out_dir: Path, train_ratio=0.8):
    """
    쌍 목록을 8:2로 분할하고, out_dir/{train,val}에 심볼릭링크(또는 복사) 생성.
    """
    random.shuffle(pairs)
    n_total = len(pairs)
    n_train = int(round(n_total * train_ratio))
    train_pairs = pairs[:n_train]
    val_pairs = pairs[n_train:]

    for split_name, subset in [("train", train_pairs), ("val", val_pairs)]:
        for csv_path, json_path in subset:
            rel = csv_path.name  # 파일명만 사용
            dst_csv = out_dir / split_name / rel
            dst_json = out_dir / split_name / json_path.name
            _safe_symlink(csv_path, dst_csv)
            _safe_symlink(json_path, dst_json)
    return train_pairs, val_pairs

# -------------------------
# 라벨 JSON 해석 (유연 파서)
# -------------------------
def parse_label_json(json_path: Path) -> List[Tuple[int, int, int]]:
    """
    라벨 JSON을 다양한 스키마로 수용하여 [(start, end, level), ...] 리스트로 변환.
    - end는 inclusive로 간주 (start <= frame <= end)
    - 인식 실패 시 빈 리스트
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segs = []

    def norm_one(d):
        # 키 변형 수용
        if isinstance(d, dict):
            # 유형 1: 명시 키
            s = d.get("start_frame", d.get("frame_start", d.get("start")))
            e = d.get("end_frame", d.get("frame_end", d.get("end")))
            lvl = d.get("level", d.get("lvl", d.get("label", d.get("state"))))
            if s is not None and e is not None and lvl is not None:
                return int(s), int(e), int(lvl)
            # 유형 2: frames: [s, e]
            if "frames" in d and isinstance(d["frames"], (list, tuple)) and len(d["frames"]) >= 2:
                s, e = d["frames"][:2]
                lvl = int(d.get("level", d.get("label", -1)))
                return int(s), int(e), int(lvl)
        return None

    if isinstance(data, list):
        for item in data:
            r = norm_one(item)
            if r: segs.append(r)
    elif isinstance(data, dict):
        # 유형 3: {"segments":[{...}, ...]}
        if "segments" in data and isinstance(data["segments"], list):
            for item in data["segments"]:
                r = norm_one(item)
                if r: segs.append(r)
        # 유형 4: {"ranges": {"100-200": 2, ...}}
        elif "ranges" in data and isinstance(data["ranges"], dict):
            for k, v in data["ranges"].items():
                m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(k))
                if m:
                    s, e = int(m.group(1)), int(m.group(2))
                    segs.append((s, e, int(v)))
        # 유형 5: {"100-200": 1, "201-260": 2}
        else:
            for k, v in data.items():
                m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(k))
                if m:
                    s, e = int(m.group(1)), int(m.group(2))
                    segs.append((s, e, int(v)))

    # 정렬 & 병합은 생략(중복은 뒤값 우선)
    segs.sort(key=lambda x: (x[0], x[1]))
    return segs

def build_frame_labels(max_frame: int, segments: List[Tuple[int,int,int]], default_level=-1) -> np.ndarray:
    """
    0..max_frame 범위에 대해 프레임별 level 배열 만들기.
    """
    labels = np.full((max_frame+1,), default_level, dtype=np.int32)
    for s, e, lvl in segments:
        s = max(0, s); e = min(max_frame, e)
        if e >= s:
            labels[s:e+1] = int(lvl)
    return labels

def infer_fps_from_csv(df: pd.DataFrame) -> float:
    """
    CSV의 frame과 time_sec로 FPS 추정.
    """
    df = df.sort_values("frame")
    if "time_sec" in df.columns and df["time_sec"].max() > 0:
        f_span = float(df["frame"].iloc[-1] - df["frame"].iloc[0])
        t_span = float(df["time_sec"].iloc[-1] - df["time_sec"].iloc[0])
        if t_span > 0 and f_span > 0:
            return max(1.0, round(f_span / t_span, 2))
    # fallback: frame 차분의 중앙값을 1프레임으로 간주
    return 30.0  # 보수적 기본값

def load_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # 필수 컬럼 체크
    must = ["frame", "time_sec"] + FEATURE_COLS
    missing = [c for c in must if c not in df.columns]
    if missing:
        raise ValueError(f"[{csv_path.name}] 누락 컬럼: {missing}")
    df = df.sort_values("frame").reset_index(drop=True)
    return df

def make_windows_for_pair(
    csv_path: Path, json_path: Path,
    window_sec=5.0, hop_sec=1.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    하나의 (CSV, JSON) 쌍에서 (X, y) 윈도우 생성
    - X: (num_win, seq_len, num_feat)
    - y: (num_win,)  # 윈도우 대표 레벨 (다수결)
    """
    df = load_csv(csv_path)
    fps = infer_fps_from_csv(df)
    win = max(1, int(round(window_sec * fps)))
    hop = max(1, int(round(hop_sec * fps)))

    # 프레임별 라벨
    segs = parse_label_json(json_path)
    max_frame = int(df["frame"].max())
    frame_labels = build_frame_labels(max_frame, segs, default_level=-1)

    # 특성 행렬
    feats = df[FEATURE_COLS].astype(float).copy()
    # NaN 보정(앞채움→뒤채움→0)
    feats = feats.fillna(method="ffill").fillna(method="bfill").fillna(0.0)
    feat_np = feats.to_numpy(dtype=np.float32)
    frames = df["frame"].to_numpy(dtype=np.int32)

    # 프레임 인덱스 → 라벨 매핑
    label_by_row = np.array([frame_labels[f] if f <= max_frame else -1 for f in frames], dtype=np.int32)

    X_list, y_list = []
    X_list, y_list = [], []
    start = 0
    last_start = len(df) - win
    while start <= last_start:
        end = start + win
        seq = feat_np[start:end, :]  # (win, feat)
        seq_labels = label_by_row[start:end]  # (win,)

        # 윈도우 대표 라벨: 다수결(동점이면 마지막 프레임값)
        cnt = Counter(seq_labels.tolist())
        most = max(cnt.items(), key=lambda kv: (kv[1], kv[0]))[0]
        y = most

        X_list.append(seq)
        y_list.append(y)
        start += hop

    if not X_list:
        return np.empty((0, win, len(FEATURE_COLS)), dtype=np.float32), np.empty((0,), dtype=np.int32)

    X = np.stack(X_list, axis=0).astype(np.float32)
    y = np.array(y_list, dtype=np.int32)
    return X, y

def build_numpy_dataset(pairs: List[Tuple[Path,Path]], window_sec=5.0, hop_sec=1.0):
    Xs, ys = [], []
    for csv_path, json_path in pairs:
        Xi, yi = make_windows_for_pair(csv_path, json_path, window_sec, hop_sec)
        if len(Xi) > 0:
            Xs.append(Xi); ys.append(yi)
    if not Xs:
        raise RuntimeError("윈도우가 생성되지 않았습니다. 입력 파일/라벨을 확인하세요.")
    X = np.concatenate(Xs, axis=0)
    y = np.concatenate(ys, axis=0)
    return X, y

def fit_standardizer(X: np.ndarray):
    """
    채널별 표준화 스케일러(평균/표준편차) 반환.
    """
    # X shape: (N, T, C)
    mean = X.reshape(-1, X.shape[-1]).mean(axis=0)
    std = X.reshape(-1, X.shape[-1]).std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)

def apply_standardizer(X: np.ndarray, mean: np.ndarray, std: np.ndarray):
    return (X - mean) / std

def to_tf_dataset(X: np.ndarray, y: np.ndarray, batch=64, shuffle=True):
    # y를 인덱스로 변환(-1..3 → 0..4)
    y_idx = np.array([LEVEL_TO_INDEX[int(v)] for v in y], dtype=np.int32)
    ds = tf.data.Dataset.from_tensor_slices((X, y_idx))
    if shuffle:
        ds = ds.shuffle(min(len(X), 10000), seed=RANDOM_SEED)
    ds = ds.batch(batch).prefetch(tf.data.AUTOTUNE)
    return ds

# =========================
# 2) 모델
# =========================
def build_lstm_model(seq_len: int, n_feat: int, n_classes: int = 5) -> tf.keras.Model:
    """
    BiLSTM 스택 + LayerNorm + Dropout.
    합리적 기본값으로 튜닝된 구조.
    """
    inp = layers.Input(shape=(seq_len, n_feat))
    x = layers.LayerNormalization()(inp)
    x = layers.Bidirectional(layers.LSTM(128, return_sequences=True))(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Bidirectional(layers.LSTM(64))(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(64, activation="relu")(x)
    x = layers.Dropout(0.2)(x)
    out = layers.Dense(n_classes, activation="softmax")(x)

    model = models.Model(inp, out)
    model.compile(
        optimizer=optimizers.Adam(1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )
    return model

# =========================
# 3) 학습 & 평가
# =========================
def train_and_evaluate(
    data_root: str,
    prepared_dir: str = "prepared-dataset",
    window_sec: float = 5.0,
    hop_sec: float = 1.0,
    batch: int = 64,
    epochs: int = 30,
):
    data_root = Path(data_root).expanduser().resolve()
    prep_dir = Path(prepared_dir).resolve()
    prep_dir.mkdir(parents=True, exist_ok=True)

    # 스캔 & 분할 & 링크
    pairs = scan_pairs(data_root)
    print(f"총 파일쌍: {len(pairs)}")
    train_pairs, val_pairs = split_and_link(pairs, prep_dir, train_ratio=0.8)
    print(f"학습: {len(train_pairs)} / 검증: {len(val_pairs)}")

    # 넘파이 데이터셋
    Xtr, ytr = build_numpy_dataset(train_pairs, window_sec, hop_sec)
    Xva, yva = build_numpy_dataset(val_pairs, window_sec, hop_sec)

    # 스케일링 (학습 기반)
    mean, std = fit_standardizer(Xtr)
    Xtr = apply_standardizer(Xtr, mean, std)
    Xva = apply_standardizer(Xva, mean, std)

    # TF Dataset
    ds_tr = to_tf_dataset(Xtr, ytr, batch=batch, shuffle=True)
    ds_va = to_tf_dataset(Xva, yva, batch=batch, shuffle=False)

    # 모델
    seq_len, n_feat = Xtr.shape[1], Xtr.shape[2]
    model = build_lstm_model(seq_len, n_feat, n_classes=len(CLS_LEVELS))
    model.summary()

    # 클래스 불균형 가중치(선택)
    counts = Counter([LEVEL_TO_INDEX[int(v)] for v in ytr])
    total = sum(counts.values())
    class_weight = {i: total / (len(counts) * counts[i]) for i in counts}
    print("class_weight:", class_weight)

    # 콜백
    cbs = [
        callbacks.ModelCheckpoint("best_lstm.keras", monitor="val_loss", save_best_only=True),
        callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3),
        callbacks.EarlyStopping(monitor="val_loss", patience=7, restore_best_weights=True),
    ]

    # 학습
    history = model.fit(
        ds_tr,
        validation_data=ds_va,
        epochs=epochs,
        class_weight=class_weight,
        callbacks=cbs,
        verbose=1,
    )

    # 평가
    eval_res = model.evaluate(ds_va, verbose=0)
    print(f"[VAL] loss={eval_res[0]:.4f}, acc={eval_res[1]:.4f}")

    # 예측 샘플 & 혼동행렬
    y_true = np.concatenate([y for _, y in ds_va.unbatch().as_numpy_iterator()], axis=0)
    y_pred = []
    for xb, _ in ds_va:
        pb = model.predict(xb, verbose=0)
        y_pred.append(np.argmax(pb.numpy(), axis=1))
    y_pred = np.concatenate(y_pred, axis=0)

    # 간단 리포트
    from sklearn.metrics import classification_report, confusion_matrix
    print(classification_report(y_true, y_pred, target_names=[str(INDEX_TO_LEVEL[i]) for i in range(len(CLS_LEVELS))]))
    print("Confusion matrix:\n", confusion_matrix(y_true, y_pred))

    # 산출물 저장
    np.savez("scaler_mean_std.npz", mean=mean, std=std)
    with open("feature_cols.txt", "w") as f:
        f.write("\n".join(FEATURE_COLS))
    print("✔ 저장: best_lstm.keras, scaler_mean_std.npz, feature_cols.txt")

# =========================
# 4) 진입점
# =========================
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_root", type=str, required=True, help="CSV/JSON 원본 폴더")
    ap.add_argument("--prepared_dir", type=str, default="prepared-dataset")
    ap.add_argument("--window_sec", type=float, default=5.0)
    ap.add_argument("--hop_sec", type=float, default=1.0)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--epochs", type=int, default=30)
    args = ap.parse_args()

    train_and_evaluate(
        data_root=args.data_root,
        prepared_dir=args.prepared_dir,
        window_sec=args.window_sec,
        hop_sec=args.hop_sec,
        batch=args.batch,
        epochs=args.epochs,
    )
