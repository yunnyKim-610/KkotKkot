"""후처리 동작 확인 (합성 데이터)"""
import copy
import types

import numpy as np
from posture_preprocess import PosturePipeline
from posture_preprocess import config as C
from posture_preprocess.backends import Person
from posture_preprocess.postprocess import PostProcessor, clean_segments, evaluate
from test_pipeline import H, W, side_view_pose


def make_cfg(**post):
    cfg = types.SimpleNamespace(**{k: copy.deepcopy(getattr(C, k)) for k in dir(C) if k.isupper()})
    cfg.POSTPROCESS.update(post)
    return cfg


def simulate(schedule, seconds, cfg=C, fps=30):
    """schedule(t) → 머리 전방 이동량, None이면 사람 없음"""
    rng = np.random.default_rng(3)

    class FB:
        t = 0.0
        def __call__(self, frame):
            fwd = schedule(self.t)
            if fwd is None:
                return []
            k = side_view_pose(fwd) + rng.normal(0, 1.5, (17, 2))
            return [Person(np.array([220, 150, 460, 470.0]), 0.9, k, np.full(17, 0.9))]
    be = FB()
    pipe = PosturePipeline(be, (W, H), cfg=cfg)
    post = PostProcessor(pipe, cfg=cfg)
    frame = np.full((H, W, 3), 120, np.uint8)
    evs = []
    for i in range(int(seconds * fps)):
        be.t = i / fps
        ev = post.update(pipe.process(frame, be.t))
        if ev:
            evs.append(ev)
    return post, evs


def test_alert_has_reason_and_message():
    post, evs = simulate(lambda t: 0.0 if t < 15 else 45.0, 60)
    alerts = [e for e in evs if e["alert"]]
    assert len(alerts) == 1 and alerts[0]["reason"] == "거북목" and "거북목" in alerts[0]["message"]


def test_leaving_seat_suppresses_alert():
    # 15초부터 구부정 → 25초에 자리를 떠남: 30초 지속 조건을 채우기 전에 떠났으므로 알림 없어야 함
    post, evs = simulate(lambda t: 0.0 if t < 15 else (45.0 if t < 25 else None), 70)
    assert not any(e["alert"] for e in evs)
    assert evs[-1]["status"] == "absent"


def test_return_after_short_absence_continues():
    post, evs = simulate(lambda t: None if 20 <= t < 30 else 0.0, 50)
    assert any(e["status"] == "absent" for e in evs)
    assert evs[-1]["status"] == "good"


def test_long_absence_triggers_recalibration():
    cfg = make_cfg(recalibrate_after_absent_sec=20.0)
    post, evs = simulate(lambda t: None if 15 <= t < 40 else 0.0, 60, cfg)
    assert any(e["status"] == "recalibrating" for e in evs)
    assert any(e["status"] == "calibrating" and e["t"] > 40 for e in evs)


def test_realert_and_escalation():
    cfg = make_cfg(realert_interval_sec=20.0, alert_cooldown_sec=10.0)
    post, evs = simulate(lambda t: 0.0 if t < 15 else 45.0, 100, cfg)
    alerts = [e for e in evs if e["alert"]]
    assert len(alerts) >= 2
    assert alerts[0]["level"] == 1 and alerts[1]["level"] == 2
    assert alerts[1]["t"] - alerts[0]["t"] >= 20 - 1e-6


def test_cooldown_blocks_rapid_alerts():
    cfg = make_cfg(alert_cooldown_sec=120.0)
    cfg.HYSTERESIS["alert_after_sec"] = 5.0
    # 불량 15초 → 바른 자세 10초 → 다시 불량: 두 번째 구간은 쿨다운 때문에 알림 없어야 함
    sched = lambda t: 45.0 if (12 <= t < 27 or t >= 37) else 0.0
    post, evs = simulate(sched, 70, cfg)
    assert sum(e["alert"] for e in evs) == 1


def test_clean_segments():
    ts = np.arange(0, 60, 1.0)
    lab = np.array([0] * 20 + [1] * 2 + [0] * 10 + [1] * 20 + [0] + [1] * 7)
    segs = clean_segments(ts, lab, merge_gap_sec=3, min_segment_sec=5)
    assert [s[2] for s in segs] == [0, 1]           # 2초짜리 불량 흡수, 1초 끊김 병합
    assert segs[1][0] == 32.0


def test_report_and_evaluate():
    post, evs = simulate(lambda t: 0.0 if t < 15 else (45.0 if t < 60 else 0.0), 90)
    rep, md = post.close()
    assert rep["bad_episodes"] == 1 and rep["alerts"] == 1
    assert "거북목" in rep["bad_sec_by_reason"] and "# 자세 리포트" in md
    run = [e for e in evs if e["status"] in ("good", "bad")]
    pt = np.array([e["t"] for e in run]); pb = np.array([e["status"] == "bad" for e in run])
    gt_t = np.arange(10, 90, 0.5); gt_b = (gt_t >= 15) & (gt_t < 60)
    m = evaluate(gt_t, gt_b, pt, pb, [a[0] for a in post.alerts])
    assert m["event_recall"] == 1.0 and m["false_alerts_per_hour"] == 0
    assert m["frame_f1"] > 0.85 and 30 <= m["alert_latency_median_sec"] <= 38
