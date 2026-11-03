"""D. 학습 데이터 단계(오프라인): 세션 정제, 라벨 정제, 사용자 단위 분할, 증강, 윈도우화, 불균형 처리

권장 흐름 (세션 = 한 사용자가 한 번 앉아서 녹화한 키포인트 기록, 앞 10초는 바른 자세 캘리브레이션)
  1) clean_session()         : B1~B4, C1 을 오프라인으로 적용 → 정규화 키포인트
  2) trim_label_boundaries() / flag_low_agreement() : 라벨 정제
  3) subject_splits()        : 사용자 단위로 학습/검증 분할  ← 증강보다 반드시 먼저
  4) augment_session()       : 학습 세트에만, 세션 단위로 증강
  5) session_features() → baseline_delta() → make_windows()
  6) class_weights() 또는 FocalLoss
"""
import warnings

import numpy as np

from . import config as C
from .features import FEATURE_NAMES, compute_features, features_to_array
from .keypoints import FLIP_PAIRS, confidence_filter, interpolate_offline, mask_joints, raw_scale, shoulder_center
from .temporal import OneEuroFilter


# ---------------------------------------------------------------- 1) 세션 정제
def clean_session(raw_xy, conf, ts, cfg=C):
    """raw_xy: (T,17,2) 픽셀, conf: (T,17), ts: (T,) 초 → 정규화 키포인트 (T,17,2)
    오프라인이므로 선형 보간을 쓰고, 스케일은 세션 전체 중앙값으로 고정(가장 안정적)."""
    xy = confidence_filter(raw_xy, conf, cfg.KEYPOINT_FILTER["min_confidence"])   # B1
    xy = mask_joints(xy, cfg.JOINT_MASK["exclude"])                               # B2
    xy = interpolate_offline(xy, ts, cfg.INTERPOLATION["max_gap_sec"])            # B3
    euro = OneEuroFilter(**cfg.ONE_EURO)                                          # C1
    xy = np.stack([euro(xy[i], ts[i]) for i in range(len(xy))])
    n = cfg.NORMALIZATION
    scales = np.array([raw_scale(f, n["scale_ref"], n["front_view_min_ratio"]) for f in xy])
    calib = ts - ts[0] < cfg.CALIBRATION["baseline_duration_sec"]
    ref = scales[calib] if np.isfinite(scales[calib]).any() else scales
    scale = np.nanmedian(ref)                       # 캘리브레이션(바른 자세) 구간 기준 스케일
    origins = np.stack([shoulder_center(f) for f in xy])
    return (xy - origins[:, None, :]) / scale                                     # B4


def session_features(nxy):
    return np.stack([features_to_array(compute_features(f)) for f in nxy])        # (T, F)


def baseline_delta(feats, ts, cfg=C, calib_mask=None):
    """세션 앞 캘리브레이션 구간(또는 calib_mask) 중앙값을 빼서 개인 기준선 대비 변화량으로. (7-2)"""
    if calib_mask is None:
        calib_mask = ts - ts[0] < cfg.CALIBRATION["baseline_duration_sec"]
    with warnings.catch_warnings():   # 측면 설치면 기울기 특징이 전부 NaN인 것이 정상
        warnings.simplefilter("ignore", RuntimeWarning)
        base = np.nanmedian(feats[calib_mask], axis=0)
    return feats - base


# ---------------------------------------------------------------- 2) 라벨 정제
def trim_label_boundaries(labels, ts, trim_sec=None, cfg=C):
    """자세가 바뀌는 경계 ±trim_sec 프레임은 학습에서 제외(라벨이 애매한 구간). (7-3)"""
    trim_sec = cfg.LABEL_CLEANING["boundary_trim_sec"] if trim_sec is None else trim_sec
    labels, ts = np.asarray(labels), np.asarray(ts, dtype=np.float64)
    keep = np.ones(len(labels), bool)
    for i in np.where(labels[1:] != labels[:-1])[0] + 1:
        keep &= np.abs(ts - (ts[i - 1] + ts[i]) / 2) > trim_sec
    return keep


def cohen_kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    cats = np.union1d(a, b)
    po = np.mean(a == b)
    pe = sum(np.mean(a == c) * np.mean(b == c) for c in cats)
    return 1.0 if pe >= 1.0 and po >= 1.0 else (0.0 if pe >= 1.0 else (po - pe) / (1 - pe))


def flag_low_agreement(labels_a, labels_b, ts, cfg=C):
    """라벨러 2명의 라벨을 segment 단위로 비교해 kappa 미만 구간을 재검토 대상으로 표시. (7-1)"""
    lc = cfg.LABEL_CLEANING
    ts = np.asarray(ts, dtype=np.float64)
    seg = ((ts - ts[0]) // lc["kappa_segment_sec"]).astype(int)
    review = np.zeros(len(ts), bool)
    for s in np.unique(seg):
        m = seg == s
        if cohen_kappa(np.asarray(labels_a)[m], np.asarray(labels_b)[m]) < lc["min_cohen_kappa"]:
            review[m] = True
    return review


# ---------------------------------------------------------------- 3) 사용자 단위 분할
def subject_splits(subject_ids, cfg=C):
    """같은 사람이 학습·검증에 동시에 들어가지 않도록 사용자 단위 분할. (10-1)
    yield (train_subjects, val_subjects)"""
    subjects = np.unique(subject_ids)
    if cfg.DATA_SPLIT["method"] == "loso":
        for s in subjects:
            yield subjects[subjects != s], np.array([s])
        return
    k = min(cfg.DATA_SPLIT["n_splits"], len(subjects))
    rng = np.random.default_rng(0)
    folds = np.array_split(rng.permutation(subjects), k)
    for i in range(k):
        yield np.concatenate([f for j, f in enumerate(folds) if j != i]), folds[i]


# ---------------------------------------------------------------- 4) 증강
def augment_session(nxy, labels=None, rng=None, flip_label_map=None, cfg=C):
    """정규화 키포인트 세션 증강. 회전·스케일·반전은 세션 전체에 '같은 값'을 적용한다.
    → 캘리브레이션 구간도 함께 변하므로 기준선 대비 변화량(라벨 의미)이 보존된다.
    지터·드롭아웃은 프레임마다 독립. flip_label_map 예: {LEAN_LEFT: LEAN_RIGHT, LEAN_RIGHT: LEAN_LEFT}"""
    a = cfg.KEYPOINT_AUG
    rng = rng or np.random.default_rng()
    out = nxy.copy()
    th = np.deg2rad(rng.uniform(-a["rotation_deg"], a["rotation_deg"]))
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    out = out @ R.T * rng.uniform(*a["scale_range"])
    out = out + rng.normal(0, a["jitter_sigma"], out.shape)
    drop = rng.random(out.shape[:2]) < a["joint_dropout"]
    out[drop] = np.nan
    new_labels = None if labels is None else np.asarray(labels).copy()
    if rng.random() < a["hflip_prob"]:
        out[..., 0] *= -1
        for l, r in FLIP_PAIRS:                       # 좌/우 관절 인덱스 교환
            out[:, [l, r]] = out[:, [r, l]]
        if new_labels is not None and flip_label_map:  # 방향 라벨도 반전
            new_labels = np.array([flip_label_map.get(v, v) for v in new_labels])
    return out, new_labels


def augment_image(img, rng=None, cfg=C):
    """밝기·대비 증강 (원본 영상을 저장할 수 있을 때만, 9-1). img: uint8 BGR"""
    a = cfg.IMAGE_AUG
    rng = rng or np.random.default_rng()
    b = rng.uniform(-a["brightness"], a["brightness"]) * 255
    c = 1 + rng.uniform(-a["contrast"], a["contrast"])
    m = img.mean()
    return np.clip((img.astype(np.float32) - m) * c + m + b, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- 5) 윈도우화
def make_windows(X, labels, ts, keep_mask=None, fps=None, cfg=C):
    """X: (T,F) 특징 → (N, W, F) 윈도우. 라벨은 윈도우 내 다수결.
    트리밍으로 제외된 프레임이 많거나 결측이 많은 윈도우는 버린다. (6-3, 7-3)"""
    w = cfg.WINDOW
    ts = np.asarray(ts, dtype=np.float64)
    fps = fps or cfg.FRAME_SAMPLING["target_infer_fps"]
    W, S = int(round(w["size_sec"] * fps)), max(1, int(round(w["stride_sec"] * fps)))
    keep = np.ones(len(X), bool) if keep_mask is None else keep_mask
    labels = np.asarray(labels)
    xs, ys = [], []
    for st in range(0, len(X) - W + 1, S):
        sl = slice(st, st + W)
        if keep[sl].mean() < w["min_fill_ratio"]:
            continue
        if (~np.isnan(X[sl]).all(axis=1)).mean() < w["min_valid_ratio"]:
            continue
        vals, cnt = np.unique(labels[sl][keep[sl]], return_counts=True)
        xs.append(X[sl])
        ys.append(vals[np.argmax(cnt)])
    if not xs:
        return np.empty((0, W, X.shape[1])), np.empty((0,), labels.dtype)
    return np.stack(xs), np.array(ys)


# ---------------------------------------------------------------- 6) 불균형 처리
def class_weights(y):
    """빈도의 역수 가중치 (평균 1로 정규화). (6-4)"""
    vals, cnt = np.unique(y, return_counts=True)
    w = 1.0 / cnt
    w = w / w.mean()
    return dict(zip(vals.tolist(), w.tolist()))


def make_focal_loss(gamma=None, alpha=None, cfg=C):
    """PyTorch Focal Loss (γ=2). alpha: 클래스 가중치 텐서(선택)."""
    import torch.nn.functional as F
    gamma = cfg.IMBALANCE["focal_gamma"] if gamma is None else gamma

    def loss(logits, target):
        logp = F.log_softmax(logits, dim=-1)
        logpt = logp.gather(1, target[:, None]).squeeze(1)
        l = -((1 - logpt.exp()) ** gamma) * logpt
        if alpha is not None:
            l = l * alpha[target]
        return l.mean()
    return loss


__all__ = ["clean_session", "session_features", "baseline_delta", "trim_label_boundaries",
           "cohen_kappa", "flag_low_agreement", "subject_splits", "augment_session",
           "augment_image", "make_windows", "class_weights", "make_focal_loss", "FEATURE_NAMES"]
