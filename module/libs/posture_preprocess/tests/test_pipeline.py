"""합성 데이터로 파이프라인 동작 확인 (카메라·모델 없이 실행 가능): python -m pytest tests -q"""
import numpy as np
from posture_preprocess import PosturePipeline
from posture_preprocess import dataset as D
from posture_preprocess.backends import Person
from posture_preprocess.keypoints import IDX, OnlineGapFiller, interpolate_offline
from posture_preprocess.temporal import OneEuroFilter

W, H = 640, 480


def side_view_pose(forward=0.0):
    """측면에서 본 착석 자세 (픽셀). forward>0 이면 머리가 앞으로(거북목)."""
    k = np.full((17, 2), np.nan)
    sh = np.array([320.0, 260.0])
    k[IDX["left_shoulder"]] = sh
    k[IDX["right_shoulder"]] = sh + [4, 2]
    k[IDX["left_ear"]] = sh + [5 + forward, -70 + forward * 0.3]
    k[IDX["right_ear"]] = k[IDX["left_ear"]] + [3, 1]
    k[IDX["nose"]] = k[IDX["left_ear"]] + [30, 10]
    k[IDX["left_eye"]] = k[IDX["nose"]] + [-8, -10]
    k[IDX["right_eye"]] = k[IDX["left_eye"]] + [2, 0]
    k[IDX["left_hip"]] = sh + [-10, 170]
    k[IDX["right_hip"]] = k[IDX["left_hip"]] + [4, 2]
    for n in ("left_elbow", "left_wrist", "right_elbow", "right_wrist"):
        k[IDX[n]] = sh + [60, 100]
    for n in ("left_knee", "right_knee", "left_ankle", "right_ankle"):
        k[IDX[n]] = sh + [80, 250]
    return k


class FakeBackend:
    def __init__(self, schedule, rng):
        self.schedule, self.rng, self.t = schedule, rng, 0.0

    def __call__(self, frame):
        fwd = self.schedule(self.t)
        k = side_view_pose(fwd) + self.rng.normal(0, 1.5, (17, 2))
        conf = np.full(17, 0.9)
        conf[self.rng.random(17) < 0.05] = 0.1          # 가끔 저신뢰 키포인트
        persons = [Person(np.array([220, 150, 460, 470.0]), 0.9, k, conf)]
        if 20 < self.t < 25:                             # 지나가는 사람 (작은 박스, 무시돼야 함)
            persons.append(Person(np.array([10, 10, 60, 60.0]), 0.8, k * 0.1, conf))
        return persons


def run(schedule, seconds, fps=30):
    rng = np.random.default_rng(1)
    be = FakeBackend(schedule, rng)
    pipe = PosturePipeline(be, (W, H))
    frame = np.full((H, W, 3), 120, np.uint8)
    results = []
    for i in range(int(seconds * fps)):
        t = i / fps
        be.t = t
        r = pipe.process(frame, t)
        if r is not None:
            results.append(r)
    return results


def test_good_posture_never_alerts():
    res = run(lambda t: 0.0, 60)
    assert res[0]["status"] == "calibrating"
    running = [r for r in res if r["status"] == "running"]
    assert running and all(r["state"] == "good" for r in running)
    assert not any(r["alert"] for r in res)


def test_forward_head_triggers_alert_after_30s():
    res = run(lambda t: 0.0 if t < 15 else 45.0, 60)
    alerts = [r["t"] for r in res if r["alert"]]
    assert len(alerts) == 1
    assert 45 <= alerts[0] <= 52      # 15초 시작 + 윈도우 판정 지연 + 30초 지속
    assert res[-1]["delta"]["neck_angle"] > 10


def test_short_slouch_ignored():
    res = run(lambda t: 45.0 if 30 <= t < 31 else 0.0, 50)   # 1초짜리 순간 동작
    assert all(r["state"] in (None, "good") for r in res)


def test_offline_interpolation_respects_max_gap():
    ts = np.arange(30) / 15
    seq = np.tile(np.arange(30, dtype=float)[:, None, None], (1, 1, 2))
    seq[5:9] = np.nan          # 4프레임(≈0.33s) → 보간
    seq[15:25] = np.nan        # 10프레임(≈0.73s) → 유지
    out = interpolate_offline(seq, ts, 0.5)
    assert np.allclose(out[5:9, 0, 0], np.arange(5, 9))
    assert np.isnan(out[15:25]).all()


def test_online_gap_filler():
    g = OnlineGapFiller(1, 0.5)
    g(np.array([[1.0, 2.0]]), 0.0)
    assert np.allclose(g(np.array([[np.nan, np.nan]]), 0.4), [[1, 2]])
    assert np.isnan(g(np.array([[np.nan, np.nan]]), 0.7)).all()


def test_one_euro_reduces_jitter():
    rng = np.random.default_rng(0)
    f = OneEuroFilter()
    raw = 100 + rng.normal(0, 2, 300)
    sm = np.array([f(np.array([v]), i / 15)[0] for i, v in enumerate(raw)])
    assert np.std(sm[50:]) < np.std(raw[50:]) * 0.7


def test_dataset_flow():
    rng = np.random.default_rng(0)
    fps, T = 15, 15 * 40
    ts = np.arange(T) / fps
    labels = (ts >= 20).astype(int)
    raw = np.stack([side_view_pose(0 if t < 20 else 45) + rng.normal(0, 1.5, (17, 2)) for t in ts])
    conf = np.full((T, 17), 0.9)
    nxy = D.clean_session(raw, conf, ts)
    aug, aug_labels = D.augment_session(nxy, labels, rng, flip_label_map={})
    for arr in (nxy, aug):
        X = D.baseline_delta(D.session_features(arr), ts)
        keep = D.trim_label_boundaries(labels, ts)
        Xw, yw = D.make_windows(X, labels, ts, keep, fps)
        assert Xw.shape[1:] == (45, len(D.FEATURE_NAMES)) and set(yw) == {0, 1}
        neck = D.FEATURE_NAMES.index("neck_angle")
        assert np.nanmean(Xw[yw == 1][:, :, neck]) > 10 > np.nanmean(Xw[yw == 0][:, :, neck])
    assert abs(D.cohen_kappa([0, 0, 1, 1], [0, 0, 1, 1]) - 1) < 1e-9
    splits = list(D.subject_splits(np.array(["a", "b", "c", "d", "e", "f"])))
    assert all(not set(tr) & set(va) for tr, va in splits)
    w = D.class_weights(np.array([0] * 90 + [1] * 10))
    assert w[1] > w[0]


def front_view_pose(lean=0.0):
    """정면 착석 자세. lean>0 이면 사람의 왼쪽(화면 오른쪽) 어깨가 내려감."""
    k = np.full((17, 2), np.nan)
    c = np.array([320.0, 260.0])
    k[IDX["left_shoulder"]] = c + [80, lean]
    k[IDX["right_shoulder"]] = c + [-80, -lean]
    k[IDX["left_ear"]] = c + [30, -90 + lean * 0.5]
    k[IDX["right_ear"]] = c + [-30, -90 - lean * 0.5]
    k[IDX["nose"]] = c + [0, -75]
    k[IDX["left_eye"]] = c + [12, -90]
    k[IDX["right_eye"]] = c + [-12, -90]
    return k


def test_front_view_lean_detected():
    rng = np.random.default_rng(2)

    class FB:
        t = 0.0
        def __call__(self, frame):
            k = front_view_pose(0 if self.t < 15 else 25) + rng.normal(0, 1.5, (17, 2))
            return [Person(np.array([200, 150, 440, 470.0]), 0.9, k, np.full(17, 0.9))]
    be = FB()
    pipe = PosturePipeline(be, (W, H))
    frame = np.full((H, W, 3), 120, np.uint8)
    states = []
    for i in range(30 * 25):
        be.t = i / 30
        r = pipe.process(frame, be.t)
        if r and r["status"] == "running":
            states.append((be.t, r["state"], r["delta"]["shoulder_tilt"]))
    assert all(s == "good" for t, s, _ in states if t < 15)
    assert states[-1][1] == "bad" and abs(states[-1][2]) > 5


def test_video_stage_functions():
    import cv2
    from posture_preprocess import config as C
    from posture_preprocess.video import FrameSampler, LightingCorrector, Stabilizer, anonymize_face
    dark = np.full((H, W, 3), 40, np.uint8)
    out = LightingCorrector(C.GAMMA, C.CLAHE)(dark, roi=(100, 100, 300, 300))
    assert out.mean() > dark.mean()                       # 저조도 → 밝아짐
    rng = np.random.default_rng(0)
    tex = (rng.random((H, W)) * 255).astype(np.uint8)
    tex = cv2.cvtColor(cv2.GaussianBlur(tex, (5, 5), 0), cv2.COLOR_GRAY2BGR)
    st = Stabilizer()
    st(tex)
    shifted = np.roll(tex, 8, axis=1)                      # 카메라가 8px 흔들림
    fixed = st(shifted)
    err_before = np.abs(shifted[50:-50, 50:-50].astype(int) - tex[50:-50, 50:-50]).mean()
    err_after = np.abs(fixed[50:-50, 50:-50].astype(int) - tex[50:-50, 50:-50]).mean()
    assert err_after < err_before
    img = (rng.random((H, W, 3)) * 255).astype(np.uint8)
    anon = anonymize_face(img, front_view_pose(), "exclude")
    assert anon[185, 320].sum() == 0                       # 얼굴 영역 제거
    s = FrameSampler(15)
    assert sum(s.should_process(i / 30) for i in range(300)) in (150, 151)
