"""C2. 자세 특징 계산 (정규화 좌표 입력, 이미지 좌표계: y가 아래로 증가)"""
import math
import numpy as np
from .keypoints import IDX
from . import config as C

FEATURE_NAMES = ["neck_angle", "head_forward", "head_height", "shoulder_tilt", "head_tilt", "trunk_angle"]


def _ok(*pts):
    return all(not np.isnan(p).any() for p in pts)


def _tilt(left, right):
    """두 점을 잇는 선의 수평 대비 기울기[deg]. 사람의 왼쪽이 낮으면 +."""
    return math.degrees(math.atan2(left[1] - right[1], abs(left[0] - right[0]) + 1e-9))


def compute_features(nxy, validity=None):
    v = validity or C.FEATURE_VALIDITY
    f = {k: np.nan for k in FEATURE_NAMES}
    if np.isnan(nxy).all():
        return f
    # 거북목: 귀-어깨 선이 수직에서 얼마나 기울었는지, 귀가 어깨보다 얼마나 앞에 있는지 (측면/대각선 설치에서 유효)
    angles, offsets = [], []
    for e, s in (("left_ear", "left_shoulder"), ("right_ear", "right_shoulder")):
        ear, sh = nxy[IDX[e]], nxy[IDX[s]]
        if _ok(ear, sh):
            angles.append(math.degrees(math.atan2(abs(ear[0] - sh[0]), sh[1] - ear[1])))
            offsets.append(abs(ear[0] - sh[0]))
    if angles:
        f["neck_angle"], f["head_forward"] = float(np.mean(angles)), float(np.mean(offsets))
    # 구부정/엎드림: 코가 어깨 중점(원점) 위로 얼마나 올라와 있는지
    nose = nxy[IDX["nose"]]
    if _ok(nose):
        f["head_height"] = float(-nose[1])
    # 좌우 기울어짐 (정면/대각선 설치에서 유효)
    ls, rs = nxy[IDX["left_shoulder"]], nxy[IDX["right_shoulder"]]
    if _ok(ls, rs) and abs(ls[0] - rs[0]) >= v["min_shoulder_dx"]:
        f["shoulder_tilt"] = _tilt(ls, rs)
    le, re = nxy[IDX["left_ear"]], nxy[IDX["right_ear"]]
    if _ok(le, re) and abs(le[0] - re[0]) >= v["min_ear_dx"]:
        f["head_tilt"] = _tilt(le, re)
    # 몸통 기울기: 골반 중점 → 어깨 중점(원점) 선의 수직 대비 각도 (골반이 보일 때만)
    hips = nxy[[IDX["left_hip"], IDX["right_hip"]]]
    hips = hips[~np.isnan(hips).any(axis=1)]
    if len(hips):
        hc = hips.mean(axis=0)
        f["trunk_angle"] = math.degrees(math.atan2(abs(hc[0]), hc[1] + 1e-9))
    return f


def features_to_array(f):
    return np.array([f[k] for k in FEATURE_NAMES], dtype=np.float64)
