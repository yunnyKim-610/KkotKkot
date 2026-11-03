"""A. 영상 단계: 프레임 샘플링, 왜곡 보정, 안정화, 조명 보정, 대상자 선택, ROI, 비식별화"""
import math
from collections import deque

import cv2
import numpy as np


# ---------------------------------------------------------------- A1
class FrameSampler:
    """입력 FPS와 무관하게 목표 FPS로만 추론하도록 프레임을 고른다. (3-6, 8-2)"""

    def __init__(self, target_fps):
        self.interval = 1.0 / float(target_fps)
        self.next_t = None

    def should_process(self, t):
        if self.next_t is None:
            self.next_t = t + self.interval
            return True
        if t >= self.next_t:
            # 처리가 밀려 한 주기 이상 늦었으면 현재 시각 기준으로 재설정(누적 지연 방지)
            self.next_t = (t if t - self.next_t > self.interval else self.next_t) + self.interval
            return True
        return False


# ---------------------------------------------------------------- A2
def calibrate_camera(image_paths, checkerboard=(9, 6), square_size_mm=25.0, out_file="camera_calib.npz"):
    """체커보드 사진 15~20장으로 카메라 내부 파라미터를 구해 저장한다. (3-7)"""
    cols, rows = checkerboard
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_size_mm
    obj_pts, img_pts, size = [], [], None
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3)
    for p in image_paths:
        gray = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
        size = gray.shape[::-1]
        ok, corners = cv2.findChessboardCorners(gray, checkerboard)
        if ok:
            obj_pts.append(objp)
            img_pts.append(cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), crit))
    if len(obj_pts) < 10:
        raise RuntimeError(f"체커보드 검출 성공 {len(obj_pts)}장: 최소 10장 이상 필요")
    rms, K, dist, _, _ = cv2.calibrateCamera(obj_pts, img_pts, size, None, None)
    np.savez(out_file, K=K, dist=dist, image_size=np.array(size))
    return rms


class Undistorter:
    """렌즈 왜곡 보정. keypoints_only=True면 영상 대신 좌표만 보정(저사양 대안)."""

    def __init__(self, calib_file, image_size, keypoints_only=False):
        d = np.load(calib_file)
        self.K, self.dist = d["K"], d["dist"]
        w, h = image_size
        self.newK, _ = cv2.getOptimalNewCameraMatrix(self.K, self.dist, (w, h), 0)
        self.keypoints_only = keypoints_only
        self.maps = None
        if not keypoints_only:  # 맵을 미리 계산해 두면 프레임마다 remap 한 번이면 끝
            self.maps = cv2.initUndistortRectifyMap(self.K, self.dist, None, self.newK, (w, h), cv2.CV_16SC2)

    def frame(self, img):
        return img if self.maps is None else cv2.remap(img, *self.maps, cv2.INTER_LINEAR)

    def points(self, xy):
        out = xy.copy()
        valid = ~np.isnan(xy).any(axis=1)
        if valid.any():
            pts = xy[valid].reshape(-1, 1, 2).astype(np.float64)
            out[valid] = cv2.undistortPoints(pts, self.K, self.dist, P=self.newK).reshape(-1, 2)
        return out


# ---------------------------------------------------------------- A3
class Stabilizer:
    """배경 ORB 특징점으로 카메라 흔들림을 추정하고 과거 이동평균 위치로 되돌린다(인과적, 실시간용). (3-5)"""

    def __init__(self, n_features=500, radius=15, min_matches=10):
        self.orb = cv2.ORB_create(n_features)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.min_matches = min_matches
        self.prev = None
        self.traj = np.zeros(3)
        self.hist = deque(maxlen=radius)

    def __call__(self, frame, ignore_box=None):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mask = np.full(gray.shape, 255, np.uint8)
        if ignore_box is not None:  # 사람 영역은 제외하고 배경만 추적
            x1, y1, x2, y2 = ignore_box
            mask[y1:y2, x1:x2] = 0
        kp, des = self.orb.detectAndCompute(gray, mask)
        dx = dy = da = 0.0
        if self.prev is not None and des is not None and self.prev[1] is not None:
            matches = self.bf.match(self.prev[1], des)
            if len(matches) >= self.min_matches:
                src = np.float32([self.prev[0][m.queryIdx].pt for m in matches])
                dst = np.float32([kp[m.trainIdx].pt for m in matches])
                M, _ = cv2.estimateAffinePartial2D(src, dst)
                if M is not None:
                    dx, dy, da = M[0, 2], M[1, 2], math.atan2(M[1, 0], M[0, 0])
        self.prev = (kp, des)
        self.traj += (dx, dy, da)
        self.hist.append(self.traj.copy())
        tx, ty, ta = np.mean(self.hist, axis=0) - self.traj
        c, s = math.cos(ta), math.sin(ta)
        M = np.array([[c, -s, tx], [s, c, ty]], dtype=np.float64)
        return cv2.warpAffine(frame, M, (frame.shape[1], frame.shape[0]), borderMode=cv2.BORDER_REPLICATE)


# ---------------------------------------------------------------- A4
class LightingCorrector:
    """저조도면 감마 LUT, 이후 LAB L채널 CLAHE. roi가 주어지면 그 영역에만 CLAHE. (2-2~2-4)"""

    def __init__(self, gamma_cfg, clahe_cfg):
        self.g = gamma_cfg
        self.c = clahe_cfg
        self.lut = np.array([((i / 255.0) ** gamma_cfg["gamma"]) * 255 for i in range(256)]).clip(0, 255).astype(np.uint8)
        self.clahe = cv2.createCLAHE(clipLimit=clahe_cfg["clip_limit"], tileGridSize=tuple(clahe_cfg["tile_grid_size"]))

    def __call__(self, frame, roi=None):
        out = frame
        region = (slice(roi[1], roi[3]), slice(roi[0], roi[2])) if roi is not None else (slice(None), slice(None))
        if self.g["enabled"]:
            if cv2.cvtColor(frame[region], cv2.COLOR_BGR2GRAY).mean() < self.g["brightness_threshold"]:
                out = cv2.LUT(out, self.lut)
        if self.c["enabled"]:
            out = out.copy() if out is frame else out
            target = region if (self.c["roi_only"] and roi is not None) else (slice(None), slice(None))
            lab = cv2.cvtColor(out[target], cv2.COLOR_BGR2LAB)
            lab[..., 0] = self.clahe.apply(lab[..., 0])
            out[target] = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        return out


# ---------------------------------------------------------------- A5
def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def filter_detections(persons, frame_shape, min_confidence=0.5, min_box_area_ratio=0.05):
    """낮은 신뢰도·작은 박스(멀리 지나가는 사람, 포스터, 모니터 속 사람)를 제거. (4-1, 5-3)"""
    h, w = frame_shape[:2]
    keep = []
    for p in persons:
        area = (p.box[2] - p.box[0]) * (p.box[3] - p.box[1])
        if p.score >= min_confidence and area >= min_box_area_ratio * w * h:
            keep.append(p)
    return keep


class TargetTracker:
    """대상자 1명을 IoU로 고정. 놓치면 timeout 동안은 다른 사람을 대상자로 바꾸지 않는다. (4-1)"""

    def __init__(self, iou_threshold=0.3, lost_timeout_sec=5.0):
        self.thr = iou_threshold
        self.timeout = lost_timeout_sec
        self.box = None
        self.last_seen = None

    def update(self, persons, t, frame_shape):
        if self.box is not None:
            if persons:
                best = max(persons, key=lambda p: iou(p.box, self.box))
                if iou(best.box, self.box) >= self.thr:
                    self.box, self.last_seen = best.box.copy(), t
                    return best
            if t - self.last_seen <= self.timeout:
                return None          # 대상자를 기다리는 중: 다른 사람은 무시
            self.box = None          # timeout 경과 → 재선택
        if not persons:
            return None
        h, w = frame_shape[:2]

        def score(p):  # 크고 화면 중앙에 가까운 사람을 대상자로
            cx, cy = (p.box[0] + p.box[2]) / 2, (p.box[1] + p.box[3]) / 2
            area = (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]) / (w * h)
            dist = math.hypot(cx / w - 0.5, cy / h - 0.5)
            return area * (1.0 - dist)

        best = max(persons, key=score)
        self.box, self.last_seen = best.box.copy(), t
        return best


def expand_box(box, margin, frame_shape):
    """검출 박스를 margin 비율만큼 넓힌 정수 ROI. (5-2)"""
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return (int(max(0, x1 - mx)), int(max(0, y1 - my)), int(min(w, x2 + mx)), int(min(h, y2 + my)))


# ---------------------------------------------------------------- A6
def anonymize_face(frame, kpts, mode="blur", kernel=51, margin=0.6):
    """포즈 추정이 끝난 뒤 얼굴(코·눈·귀 키포인트 영역)을 블러하거나 지운다. (9-2)"""
    if mode == "none":
        return frame
    face = kpts[:5]
    face = face[~np.isnan(face).any(axis=1)]
    if len(face) < 2:
        return frame
    out = frame.copy()
    (x1, y1), (x2, y2) = face.min(axis=0), face.max(axis=0)
    size = max(x2 - x1, y2 - y1, 10.0) * (1 + margin)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    h, w = frame.shape[:2]
    bx1, by1 = int(max(0, cx - size / 2)), int(max(0, cy - size / 2))
    bx2, by2 = int(min(w, cx + size / 2)), int(min(h, cy + size / 2))
    if bx2 <= bx1 or by2 <= by1:
        return frame
    if mode == "exclude":
        out[by1:by2, bx1:bx2] = 0
    else:
        k = kernel | 1
        out[by1:by2, bx1:bx2] = cv2.GaussianBlur(out[by1:by2, bx1:bx2], (k, k), 0)
    return out
