"""B. 키포인트 단계: 신뢰도 필터, 관절 마스킹, 결측 보간, 정규화 (COCO-17 기준)"""
import numpy as np

COCO_NAMES = ["nose", "left_eye", "right_eye", "left_ear", "right_ear",
              "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
              "left_wrist", "right_wrist", "left_hip", "right_hip",
              "left_knee", "right_knee", "left_ankle", "right_ankle"]
IDX = {n: i for i, n in enumerate(COCO_NAMES)}
FLIP_PAIRS = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]


# ---------------------------------------------------------------- B1
def confidence_filter(xy, conf, min_conf):
    """신뢰도 낮은 키포인트를 NaN(결측)으로. 보간보다 먼저 해야 잘못된 점으로 보간하지 않는다. (4-3, 4-4)"""
    out = np.asarray(xy, dtype=np.float64).copy()
    out[np.asarray(conf) < min_conf] = np.nan
    return out


# ---------------------------------------------------------------- B2
def mask_joints(xy, exclude_names):
    """책상 등으로 항상 가려지는 관절을 입력에서 제외. (1-2, 5-1)"""
    out = xy.copy()
    for n in exclude_names:
        out[..., IDX[n], :] = np.nan
    return out


# ---------------------------------------------------------------- B3
class OnlineGapFiller:
    """실시간용 결측 처리: 미래 프레임이 없으므로 선형 보간 대신 max_gap 동안 마지막 값 유지. (5-1)"""

    def __init__(self, n_joints=17, max_gap_sec=0.5):
        self.max_gap = max_gap_sec
        self.last = np.full((n_joints, 2), np.nan)
        self.last_t = np.full(n_joints, -np.inf)

    def __call__(self, xy, t):
        out = xy.copy()
        valid = ~np.isnan(xy).any(axis=1)
        self.last[valid] = xy[valid]
        self.last_t[valid] = t
        fill = ~valid & (t - self.last_t <= self.max_gap)
        out[fill] = self.last[fill]
        return out


def interpolate_offline(seq, ts, max_gap_sec=0.5):
    """오프라인(학습 데이터)용: 양쪽에 값이 있는 max_gap 이하 결측 구간만 선형 보간. seq: (T, K, 2)"""
    out = seq.copy()
    ts = np.asarray(ts, dtype=np.float64)
    T, K, _ = seq.shape
    for k in range(K):
        valid = ~np.isnan(seq[:, k]).any(axis=1)
        if valid.sum() < 2:
            continue
        i = 0
        while i < T:
            if valid[i]:
                i += 1
                continue
            j = i
            while j < T and not valid[j]:
                j += 1
            if i > 0 and j < T and ts[j] - ts[i - 1] <= max_gap_sec + 1e-9:
                w = (ts[i:j] - ts[i - 1]) / (ts[j] - ts[i - 1])
                out[i:j, k] = seq[i - 1, k] + w[:, None] * (seq[j, k] - seq[i - 1, k])
            i = j
    return out


# ---------------------------------------------------------------- B4
def _nanmean_rows(a):
    a = a[~np.isnan(a).any(axis=1)]
    return a.mean(axis=0) if len(a) else np.array([np.nan, np.nan])


def shoulder_center(xy):
    return _nanmean_rows(xy[[IDX["left_shoulder"], IDX["right_shoulder"]]])


def raw_scale(xy, scale_ref="auto", front_view_min_ratio=1.0):
    """정규화용 스케일 후보. 정면=어깨너비, 측면=귀-어깨 거리. (3-2, 3-4)"""
    ls, rs = xy[IDX["left_shoulder"]], xy[IDX["right_shoulder"]]
    sw = np.linalg.norm(ls - rs) if not (np.isnan(ls).any() or np.isnan(rs).any()) else np.nan
    es_list = []
    for e, s in (("left_ear", "left_shoulder"), ("right_ear", "right_shoulder")):
        d = np.linalg.norm(xy[IDX[e]] - xy[IDX[s]])
        if not np.isnan(d):
            es_list.append(d)
    es = float(np.mean(es_list)) if es_list else np.nan
    if scale_ref == "shoulder_width":
        return sw
    if scale_ref == "ear_shoulder":
        return es
    if not np.isnan(sw) and (np.isnan(es) or sw / es >= front_view_min_ratio):
        return sw
    return es


class Normalizer:
    """원점=어깨 중점, 스케일=EMA로 안정화된 몸 크기. update_scale=False면 스케일 고정.
    거북목이면 귀-어깨 거리 자체가 변하므로 스케일은 '바른 자세'일 때만 갱신한다."""

    def __init__(self, scale_ref="auto", front_view_min_ratio=1.0, ema_alpha=0.05):
        self.ref, self.ratio, self.alpha = scale_ref, front_view_min_ratio, ema_alpha
        self.scale = None

    def __call__(self, xy, update_scale=True):
        origin = shoulder_center(xy)
        s = raw_scale(xy, self.ref, self.ratio)
        if update_scale and not np.isnan(s) and s > 1e-6:
            self.scale = s if self.scale is None else (1 - self.alpha) * self.scale + self.alpha * s
        if self.scale is None or np.isnan(origin).any():
            return np.full_like(xy, np.nan), origin, self.scale
        return (xy - origin) / self.scale, origin, self.scale
