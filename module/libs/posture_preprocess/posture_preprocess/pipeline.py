"""실시간 전처리 파이프라인 (A → 포즈 추정 → B → C 순서)"""
import numpy as np

from . import config as C
from .features import compute_features
from .keypoints import Normalizer, OnlineGapFiller, confidence_filter, mask_joints
from .temporal import BaselineCalibrator, OneEuroFilter, WindowDecider, rule_flag, rule_violations
from .video import (
    FrameSampler,
    LightingCorrector,
    Stabilizer,
    TargetTracker,
    Undistorter,
    anonymize_face,
    expand_box,
    filter_detections,
)


class PosturePipeline:
    """
    처리 순서
      A1 프레임 샘플링 → A2 왜곡 보정 → A3 안정화 → A4 조명 보정(이전 ROI 기준)
      → 포즈 추정 → A5 검출 필터 · 대상자 ID 고정 · ROI 갱신
      → B1 신뢰도 필터 → B2 관절 마스킹 → B3 결측 처리 → C1 One Euro(픽셀 좌표)
      → B4 정규화 → C2 특징 → C3 기준선 대비 변화량 → 규칙 판정 → C4 윈도우/히스테리시스
      → A6 얼굴 비식별화(포즈 추정 '후', 저장/표시용 프레임에만)
    """

    def __init__(self, backend, frame_size, cfg=C, classifier=None):
        self.cfg, self.backend = cfg, backend
        self.classifier = classifier or (lambda delta: rule_flag(delta, cfg.RULES))
        self.sampler = FrameSampler(cfg.FRAME_SAMPLING["target_infer_fps"])
        u = cfg.UNDISTORT
        self.undist = Undistorter(u["calib_file"], frame_size, u["keypoints_only"]) if u["enabled"] else None
        s = cfg.STABILIZATION
        self.stab = Stabilizer(s["orb_features"], s["smoothing_radius"], s["min_matches"]) if s["enabled"] else None
        self.light = LightingCorrector(cfg.GAMMA, cfg.CLAHE)
        self.tracker = TargetTracker(**cfg.TARGET_TRACKING)
        self.gap = OnlineGapFiller(17, cfg.INTERPOLATION["max_gap_sec"])
        self.euro = OneEuroFilter(**cfg.ONE_EURO)
        n = cfg.NORMALIZATION
        self.norm = Normalizer(n["scale_ref"], n["front_view_min_ratio"], n["scale_ema_alpha"])
        c = cfg.CALIBRATION
        self.calib = BaselineCalibrator(c["baseline_duration_sec"], c["drift_ema_alpha"], c["min_valid_ratio"])
        self.decider = WindowDecider(**cfg.WINDOW, **cfg.HYSTERESIS)
        self.roi = None

    def recalibrate(self):
        """사용자가 바뀌거나 자리를 옮겼을 때 호출."""
        self.calib.reset()
        self.norm.scale = None

    def process(self, frame, t):
        if not self.sampler.should_process(t):
            return None
        cfg = self.cfg
        if self.undist is not None and not self.undist.keypoints_only:
            frame = self.undist.frame(frame)                                   # A2
        if self.stab is not None:
            frame = self.stab(frame, ignore_box=self.roi)                      # A3
        frame = self.light(frame, roi=self.roi)                                # A4

        persons = self.backend(frame)                                          # 포즈 추정
        persons = filter_detections(persons, frame.shape, **cfg.PERSON_DETECTION)   # A5
        target = self.tracker.update(persons, t, frame.shape)
        box = self.tracker.box
        self.roi = expand_box(box, cfg.ROI_CROP["margin_ratio"], frame.shape) if box is not None else None

        if target is not None:
            xy, conf = target.kpts.astype(np.float64), target.kconf
        else:
            xy, conf = np.full((17, 2), np.nan), np.zeros(17)
        raw_xy, raw_conf = xy.copy(), conf.copy()
        if self.undist is not None and self.undist.keypoints_only:
            xy = self.undist.points(xy)                                        # A2(저사양 대안)

        xy = confidence_filter(xy, conf, cfg.KEYPOINT_FILTER["min_confidence"])   # B1
        xy = mask_joints(xy, cfg.JOINT_MASK["exclude"])                        # B2
        xy = self.gap(xy, t)                                                   # B3
        xy = self.euro(xy, t)                                                  # C1
        update_scale = (not self.calib.done) or self.decider.state == "good"
        nxy, _, _ = self.norm(xy, update_scale=update_scale)                   # B4
        feats = compute_features(nxy)                                          # C2

        out = {"t": t, "target_found": target is not None, "roi": self.roi,
               "raw_kpts": raw_xy, "raw_conf": raw_conf, "kpts": xy, "features": feats,
               "frame": anonymize_face(frame, xy, cfg.ANONYMIZE["mode"],
                                       cfg.ANONYMIZE["blur_kernel"], cfg.ANONYMIZE["face_margin"])}  # A6

        if not self.calib.done:                                                # C3 캘리브레이션
            self.calib.add(feats, t)
            elapsed = 0.0 if self.calib.start_t is None else t - self.calib.start_t
            out.update(status="calibrating", calib_progress=min(1.0, elapsed / self.calib.duration),
                       delta=None, flag=None, violations=[], state=None, alert=False)
            return out

        delta = self.calib.delta(feats)                                        # C3
        flag = self.classifier(delta)
        dec = self.decider.update(t, flag)                                     # C4
        if dec["state"] == "good" and flag is False:
            self.calib.update_drift(feats)                                     # C3 드리프트 보정
        out.update(status="running", delta=delta, flag=flag,
                   violations=rule_violations(delta, cfg.RULES), **dec)
        return out
