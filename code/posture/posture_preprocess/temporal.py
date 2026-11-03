"""C. 시계열 단계: One Euro 필터, 개인 기준선/드리프트 보정, 규칙 판정, 윈도우+히스테리시스"""
from collections import deque
import numpy as np


# ---------------------------------------------------------------- C1
class OneEuroFilter:
    """배열 전체에 적용되는 One Euro Filter. NaN 입력은 NaN 출력 + 해당 원소 상태 리셋. (3-5, 6-2)
    ※ 권장값(beta=0.007)은 '픽셀 좌표' 기준이라 정규화 전 픽셀 좌표에 적용한다."""

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x_prev = self.dx_prev = self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        x = np.asarray(x, dtype=np.float64)
        if self.x_prev is None:
            self.x_prev, self.dx_prev, self.t_prev = x.copy(), np.zeros_like(x), t
            return x.copy()
        dt = max(t - self.t_prev, 1e-6)
        valid, prev_valid = ~np.isnan(x), ~np.isnan(self.x_prev)
        both = valid & prev_valid
        dx = np.where(both, (np.nan_to_num(x) - np.nan_to_num(self.x_prev)) / dt, 0.0)
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        a = self._alpha(self.min_cutoff + self.beta * np.abs(dx_hat), dt)
        x_hat = np.where(both, a * np.nan_to_num(x) + (1 - a) * np.nan_to_num(self.x_prev), x)
        dx_hat = np.where(both, dx_hat, 0.0)
        self.x_prev, self.dx_prev, self.t_prev = x_hat.copy(), dx_hat, t
        return x_hat


# ---------------------------------------------------------------- C3
class BaselineCalibrator:
    """시작 후 duration 동안 '바른 자세' 특징의 중앙값을 기준선으로 등록(평균보다 이상치에 강함). (7-2)
    이후 바른 자세로 판정된 구간에서만 아주 천천히(EMA) 기준선을 갱신해 장시간 드리프트를 흡수. (1-3)"""

    def __init__(self, duration_sec=10.0, drift_alpha=0.001, min_valid_ratio=0.5):
        self.duration, self.alpha, self.min_valid = duration_sec, drift_alpha, min_valid_ratio
        self.reset()

    def reset(self):
        self.samples, self.start_t, self.baseline = [], None, None

    @property
    def done(self):
        return self.baseline is not None

    def add(self, feats, t):
        if self.start_t is None:
            self.start_t = t
        self.samples.append(feats)
        if t - self.start_t < self.duration:
            return False
        keys = self.samples[0].keys()
        arr = {k: np.array([s[k] for s in self.samples], dtype=np.float64) for k in keys}
        base = {k: (float(np.nanmedian(v)) if np.mean(~np.isnan(v)) >= self.min_valid else np.nan)
                for k, v in arr.items()}
        if all(np.isnan(v) for v in base.values()):   # 사람이 거의 안 보였으면 다시 측정
            self.reset()
            return False
        self.baseline = base
        return True

    def delta(self, feats):
        return {k: feats[k] - self.baseline.get(k, np.nan) for k in feats}

    def update_drift(self, feats):
        for k, v in feats.items():
            b = self.baseline.get(k, np.nan)
            if not np.isnan(v):
                self.baseline[k] = v if np.isnan(b) else (1 - self.alpha) * b + self.alpha * v


def rule_flag(delta, rules):
    """기준선 대비 변화량으로 프레임 단위 '흐트러짐' 판정. True/False, 판단 불가면 None.
    학습 모델을 쓰게 되면 이 함수 자리에 모델 추론을 넣으면 된다."""
    seen, bad = False, False
    for k, (op, thr) in rules.items():
        v = delta.get(k, np.nan)
        if np.isnan(v):
            continue
        seen = True
        if (op == "gt" and v > thr) or (op == "lt" and v < thr) or (op == "abs_gt" and abs(v) > thr):
            bad = True
    return bad if seen else None


# ---------------------------------------------------------------- C4
class WindowDecider:
    """슬라이딩 윈도우 내 불량 비율로 상태 전환(히스테리시스), 불량이 alert_after 이상 지속되면 알림. (6-3, 8-2)"""

    def __init__(self, size_sec=3.0, stride_sec=1.0, min_valid_ratio=0.5, min_fill_ratio=0.8,
                 enter_ratio=0.7, exit_ratio=0.3, alert_after_sec=30.0):
        self.size, self.stride = size_sec, stride_sec
        self.min_valid, self.min_fill = min_valid_ratio, min_fill_ratio
        self.enter, self.exit, self.alert_after = enter_ratio, exit_ratio, alert_after_sec
        self.buf = deque()
        self.state, self.bad_since, self.alerted = "good", None, False
        self.last_eval, self.ratio = None, None

    def update(self, t, flag):
        self.buf.append((t, flag))
        while self.buf and self.buf[0][0] < t - self.size:
            self.buf.popleft()
        alert = False
        span_ok = (t - self.buf[0][0]) >= self.min_fill * self.size
        if span_ok and (self.last_eval is None or t - self.last_eval >= self.stride - 1e-9):
            self.last_eval = t
            flags = [f for _, f in self.buf if f is not None]
            if len(flags) / len(self.buf) >= self.min_valid:   # 판단 가능한 프레임이 부족하면 상태 유지
                self.ratio = float(np.mean(flags))
                if self.state == "good" and self.ratio >= self.enter:
                    self.state, self.bad_since, self.alerted = "bad", t, False
                elif self.state == "bad" and self.ratio <= self.exit:
                    self.state, self.bad_since, self.alerted = "good", None, False
            else:
                self.ratio = None
        if self.state == "bad" and not self.alerted and t - self.bad_since >= self.alert_after:
            self.alerted, alert = True, True
        return {"state": self.state, "bad_ratio": self.ratio, "alert": alert,
                "bad_duration": (t - self.bad_since) if self.bad_since is not None else 0.0}
