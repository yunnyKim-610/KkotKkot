"""E. 후처리 단계

[실시간] PostProcessor
  E1 자리 비움 처리   : 판단 가능한 프레임이 끊기면 상태 초기화, 오래 비웠으면 재캘리브레이션
  E2 자세 유형 판별   : 불량 구간 동안 어떤 특징이 기준을 넘었는지 누적 → "거북목" 등 이유 표시
  E3 알림 정책        : 지속 시간 조건 + 재알림 간격 + 쿨다운 + 시간당 상한 + 단계적 강도

[오프라인] 세션 기록 분석
  E4 구간 정리        : 짧게 끊긴 구간 병합, 너무 짧은 구간 흡수
  E5 세션 리포트      : 바른 자세 비율, 불량 구간, 자세 유형별 시간, 알림 횟수, 시간대별 추이
  E6 성능 평가        : 프레임 단위 정밀도/재현율, 구간 단위 감지율, 오알림/시간, 알림 지연
"""
from collections import Counter, deque

import numpy as np

from . import config as C


# ======================================================================
# 실시간
# ======================================================================
class PostProcessor:
    def __init__(self, pipeline, cfg=C):
        self.pipe, self.cfg = pipeline, cfg
        self.p = cfg.POSTPROCESS
        self.alert_after = cfg.HYSTERESIS["alert_after_sec"]
        self.last_valid_t = None
        self.absent, self.absent_since = False, None
        self.episode = None
        self.episodes = []                 # 종료된 불량 구간 기록
        self.last_alert_t = -np.inf
        self.alert_times = deque()         # 최근 1시간 알림 시각
        self.log = []                      # (t, status, reason) → 리포트용
        self.alerts = []                   # (t, level, reason)

    # ---------------------------------------------------------- E2
    def _reason(self):
        if not self.episode or not self.episode["reasons"]:
            return "자세 흐트러짐"
        by_name = Counter()
        for k, n in self.episode["reasons"].items():
            by_name[self.cfg.REASON_NAMES.get(k, k)] += n
        return by_name.most_common(1)[0][0]

    def _close_episode(self, t):
        if self.episode is not None:
            self.episode["end"] = t
            self.episode["reason"] = self._reason()
            self.episodes.append(self.episode)
            self.episode = None

    # ---------------------------------------------------------- E3
    def _try_alert(self, t, bad_duration):
        ep, p = self.episode, self.p
        if bad_duration < self.alert_after:
            return None
        due = ep["n_alerts"] == 0 or t - ep["last_alert_t"] >= p["realert_interval_sec"]
        while self.alert_times and t - self.alert_times[0] > 3600:
            self.alert_times.popleft()
        if not due or t - self.last_alert_t < p["alert_cooldown_sec"] \
                or len(self.alert_times) >= p["max_alerts_per_hour"]:
            return None
        ep["n_alerts"] += 1
        ep["last_alert_t"] = self.last_alert_t = t
        self.alert_times.append(t)
        level = 2 if ep["n_alerts"] >= p["escalate_after_alerts"] else 1
        reason = self._reason()
        mins = bad_duration / 60
        dur = f"{mins:.0f}분" if mins >= 1 else f"{bad_duration:.0f}초"
        msg = (f"{reason} 자세가 {dur}째 이어지고 있어요. 자세를 바르게 해 주세요." if level == 1 else
               f"{reason} 자세가 {dur}째 계속되고 있어요. 잠시 일어나 스트레칭을 해 보세요.")
        self.alerts.append((t, level, reason))
        return level, reason, msg

    # ---------------------------------------------------------- 메인
    def update(self, r):
        """pipeline.process() 결과를 받아 최종 상태/알림을 돌려준다. (r이 None이면 None)"""
        if r is None:
            return None
        t = r["t"]
        ev = {"t": t, "status": None, "alert": False, "level": 0, "reason": None, "message": None,
              "bad_duration": 0.0}

        if r["status"] == "calibrating":
            ev["status"] = "calibrating"
            self.last_valid_t = t
            self.log.append((t, "calibrating", None))
            return ev

        # E1 자리 비움 처리
        valid = r["target_found"] and r["flag"] is not None
        if valid:
            if self.absent:
                away = t - self.absent_since
                self.absent = False
                recal = self.p["recalibrate_after_absent_sec"]
                if recal and away >= recal:
                    self.pipe.recalibrate()
                    ev["status"] = "recalibrating"
                    self.log.append((t, "calibrating", None))
                    return ev
            self.last_valid_t = t
        else:
            if self.last_valid_t is None:
                self.last_valid_t = t
            if not self.absent and t - self.last_valid_t >= self.p["absent_reset_sec"]:
                self.absent, self.absent_since = True, self.last_valid_t
                self.pipe.decider.reset()
                self._close_episode(self.last_valid_t)
        if self.absent:
            ev["status"] = "absent"
            self.log.append((t, "absent", None))
            return ev

        # E2 + E3
        state = r["state"]
        if state == "bad":
            if self.episode is None:
                self.episode = {"start": t - r["bad_duration"], "reasons": Counter(),
                                "n_alerts": 0, "last_alert_t": -np.inf}
            self.episode["reasons"].update(r.get("violations", []))
            ev["reason"] = self._reason()
            ev["bad_duration"] = r["bad_duration"]
            a = self._try_alert(t, r["bad_duration"])
            if a:
                ev["alert"] = True
                ev["level"], ev["reason"], ev["message"] = a
        else:
            self._close_episode(t)
        ev["status"] = state
        self.log.append((t, state, ev["reason"]))
        return ev

    def close(self):
        """세션 종료 시 호출: 진행 중인 불량 구간을 마감하고 리포트를 만든다."""
        if self.log:
            self._close_episode(self.log[-1][0])
        return session_report(self.log, self.alerts, self.cfg)


# ======================================================================
# 오프라인
# ======================================================================
def _runs(ts, labels):
    """같은 값이 이어지는 구간 [start, end, label] 목록. 마지막 구간 끝 = 마지막 시각 + 평균 간격."""
    ts = np.asarray(ts, dtype=np.float64)
    if len(ts) == 0:
        return []
    dt = float(np.median(np.diff(ts))) if len(ts) > 1 else 0.0
    segs, s = [], 0
    for i in range(1, len(ts) + 1):
        if i == len(ts) or labels[i] != labels[s]:
            end = ts[i] if i < len(ts) else ts[-1] + dt
            segs.append([float(ts[s]), float(end), labels[s]])
            s = i
    return segs


def _coalesce(segs):
    out = []
    for s in segs:
        if out and out[-1][2] == s[2]:
            out[-1][1] = s[1]
        else:
            out.append(list(s))
    return out


# ---------------------------------------------------------- E4
def clean_segments(ts, labels, merge_gap_sec=None, min_segment_sec=None, cfg=C):
    """① 같은 상태 사이에 끼인 merge_gap 이하 구간은 병합
       ② 남은 구간 중 min_segment 미만은 앞 구간(첫 구간이면 뒤 구간)에 흡수"""
    p = cfg.POSTPROCESS
    gap = p["merge_gap_sec"] if merge_gap_sec is None else merge_gap_sec
    min_len = p["min_segment_sec"] if min_segment_sec is None else min_segment_sec
    segs = _runs(ts, list(labels))
    changed = True
    while changed and len(segs) >= 3:
        changed = False
        for i in range(1, len(segs) - 1):
            if segs[i][1] - segs[i][0] <= gap and segs[i - 1][2] == segs[i + 1][2]:
                segs[i][2] = segs[i - 1][2]
                segs = _coalesce(segs)
                changed = True
                break
    out = []
    for s in segs:
        if s[1] - s[0] < min_len and out:
            out[-1][1] = s[1]
        else:
            out.append(list(s))
    if len(out) >= 2 and out[0][1] - out[0][0] < min_len:
        out[1][0] = out[0][0]
        out = out[1:]
    return _coalesce(out)


# ---------------------------------------------------------- E5
def session_report(log, alerts, cfg=C, block_sec=600.0):
    """log: [(t, status, reason)], alerts: [(t, level, reason)] → (리포트 dict, 마크다운 문자열)"""
    if len(log) < 2:
        return {}, "기록이 너무 짧아 리포트를 만들 수 없습니다."
    ts = np.array([l[0] for l in log], dtype=np.float64)
    status = [l[1] for l in log]
    reason = [l[2] for l in log]
    dur = np.diff(ts, append=ts[-1] + np.median(np.diff(ts)))
    total = float(dur.sum())
    tsum = lambda cond: float(sum(d for d, c in zip(dur, cond) if c))
    good = tsum([s == "good" for s in status])
    bad = tsum([s == "bad" for s in status])
    absent = tsum([s == "absent" for s in status])
    calib = tsum([s == "calibrating" for s in status])
    seated = good + bad
    by_reason = Counter()
    for d, s, rsn in zip(dur, status, reason):
        if s == "bad":
            by_reason[rsn or "자세 흐트러짐"] += float(d)

    segs = [s for s in clean_segments(ts, ["bad" if s == "bad" else "other" for s in status], cfg=cfg)
            if s[2] == "bad"]
    blocks = []
    for b0 in np.arange(ts[0], ts[-1] + 1e-9, block_sec):
        m = (ts >= b0) & (ts < b0 + block_sec)
        g = tsum([mm and s == "good" for mm, s in zip(m, status)])
        bb = tsum([mm and s == "bad" for mm, s in zip(m, status)])
        blocks.append({"start_min": round((b0 - ts[0]) / 60, 1),
                       "good_ratio": round(g / (g + bb), 3) if g + bb > 0 else None})

    rep = {
        "total_sec": round(total, 1), "seated_sec": round(seated, 1),
        "absent_sec": round(absent, 1), "calibrating_sec": round(calib, 1),
        "good_ratio": round(good / seated, 3) if seated else None,
        "bad_episodes": len(segs),
        "longest_bad_sec": round(max((s[1] - s[0] for s in segs), default=0.0), 1),
        "bad_sec_by_reason": {k: round(v, 1) for k, v in by_reason.most_common()},
        "alerts": len(alerts), "strong_alerts": sum(1 for a in alerts if a[1] >= 2),
        "blocks": blocks,
    }
    mm = lambda s: f"{int(s // 60)}분 {int(s % 60)}초"
    lines = ["# 자세 리포트", "",
             f"- 전체 기록: {mm(total)} (착석 {mm(seated)}, 자리 비움 {mm(absent)})",
             f"- 바른 자세 비율: {rep['good_ratio'] * 100:.0f}%" if seated else "- 바른 자세 비율: -",
             f"- 흐트러진 구간: {rep['bad_episodes']}회, 가장 길었던 구간 {mm(rep['longest_bad_sec'])}",
             f"- 알림: {rep['alerts']}회 (강한 알림 {rep['strong_alerts']}회)", "", "## 자세 유형별 시간"]
    lines += [f"- {k}: {mm(v)}" for k, v in rep["bad_sec_by_reason"].items()] or ["- 없음"]
    lines += ["", f"## {int(block_sec // 60)}분 단위 바른 자세 비율"]
    lines += [f"- {b['start_min']:.0f}분~: " + ("-" if b["good_ratio"] is None else f"{b['good_ratio'] * 100:.0f}%")
              for b in blocks]
    return rep, "\n".join(lines)


# ---------------------------------------------------------- E6
def evaluate(gt_ts, gt_bad, pred_ts, pred_bad, alert_times=(), cfg=C):
    """정답 라벨과 예측 결과 비교. gt_bad / pred_bad: 0·1 (또는 bool) 배열.
    판정 임계값(RULES, HYSTERESIS)을 조정할 때 이 숫자들을 기준으로 삼는다."""
    gt_ts, pred_ts = np.asarray(gt_ts, float), np.asarray(pred_ts, float)
    gt_bad, pred_bad = np.asarray(gt_bad).astype(bool), np.asarray(pred_bad).astype(bool)
    # 프레임 단위: 정답 시각마다 직전 예측값 사용
    idx = np.clip(np.searchsorted(pred_ts, gt_ts, side="right") - 1, 0, len(pred_ts) - 1)
    p = pred_bad[idx]
    tp, fp = int((p & gt_bad).sum()), int((p & ~gt_bad).sum())
    fn, tn = int((~p & gt_bad).sum()), int((~p & ~gt_bad).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    # 구간 단위
    min_ov = cfg.POSTPROCESS["event_min_overlap"]
    gt_segs = [s for s in clean_segments(gt_ts, list(gt_bad), cfg=cfg) if s[2]]
    pr_segs = [s for s in clean_segments(pred_ts, list(pred_bad), cfg=cfg) if s[2]]
    ov = lambda a, b: max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    hit = [any(ov(g, q) / (g[1] - g[0]) >= min_ov for q in pr_segs) for g in gt_segs]
    true_pred = [any(ov(q, g) > 0 for g in gt_segs) for q in pr_segs]

    # 알림: 정답 불량 구간 안(끝 + 여유 10초)에서 울렸는지
    alert_times = np.asarray(alert_times, float)
    in_gt = [any(g[0] <= a <= g[1] + 10 for g in gt_segs) for a in alert_times]
    latencies = []
    for g in gt_segs:
        a = alert_times[(alert_times >= g[0]) & (alert_times <= g[1] + 10)]
        if len(a):
            latencies.append(float(a.min() - g[0]))
    hours = max((gt_ts[-1] - gt_ts[0]) / 3600, 1e-9)
    return {
        "frame_precision": round(prec, 3), "frame_recall": round(rec, 3), "frame_f1": round(f1, 3),
        "frame_accuracy": round((tp + tn) / max(len(p), 1), 3),
        "event_recall": round(float(np.mean(hit)), 3) if gt_segs else None,
        "event_precision": round(float(np.mean(true_pred)), 3) if pr_segs else None,
        "false_alerts_per_hour": round(sum(1 for x in in_gt if not x) / hours, 2),
        "alert_latency_median_sec": round(float(np.median(latencies)), 1) if latencies else None,
        "gt_episodes": len(gt_segs), "pred_episodes": len(pr_segs),
    }
