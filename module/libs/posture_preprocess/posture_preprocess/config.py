"""
전처리 초기 파라미터 (현장 조사 반영 전 '일반 조건 기준' 값)
주석의 (x-x)는 현장 조사 체크리스트 항목 번호입니다.
현장 조사 결과가 나오면 이 파일만 수정하면 됩니다.
"""

# ============================ A. 영상 단계 ============================
FRAME_SAMPLING = {"target_infer_fps": 15}                 # (3-6, 8-2) 10~15fps

UNDISTORT = {                                             # (3-7) 광각/어안일 때만
    "enabled": False,
    "calib_file": "camera_calib.npz",
    "keypoints_only": False,     # 저사양(라즈베리파이)이면 True: 키포인트 좌표에만 보정
    "checkerboard": (9, 6),      # 체커보드 내부 코너 수
    "square_size_mm": 25.0,
}

STABILIZATION = {                                         # (3-5) 이동형/진동 거치일 때만
    "enabled": False,
    "orb_features": 500,
    "smoothing_radius": 15,      # 이동평균 반경(프레임)
    "min_matches": 10,
}

GAMMA = {"enabled": True, "brightness_threshold": 80, "gamma": 0.7}   # (2-2, 2-3)

CLAHE = {                                                 # (2-2, 2-4)
    "enabled": True,
    "clip_limit": 2.0,
    "tile_grid_size": (8, 8),
    "roi_only": True,            # 이전 프레임의 대상자 ROI에만 적용(연산 절감)
}

PERSON_DETECTION = {"min_confidence": 0.5, "min_box_area_ratio": 0.05}  # (4-1, 5-3)
TARGET_TRACKING = {"iou_threshold": 0.3, "lost_timeout_sec": 5.0}       # (4-1)
ROI_CROP = {"margin_ratio": 0.2}                                        # (5-2)

ANONYMIZE = {"mode": "blur", "blur_kernel": 51, "face_margin": 0.6}     # (9-2) none|blur|exclude

# ============================ B. 키포인트 단계 ============================
KEYPOINT_FILTER = {"min_confidence": 0.3}                 # (4-3, 4-4) MediaPipe면 0.5

JOINT_MASK = {                                            # (1-2, 5-1) 책상 착석 시 하체 제외
    "exclude": ["left_knee", "right_knee", "left_ankle", "right_ankle"],
}

INTERPOLATION = {"max_gap_sec": 0.5}                      # (5-1)

NORMALIZATION = {                                         # (3-2, 3-4, 4-2)
    "scale_ref": "auto",         # "shoulder_width"(정면) | "ear_shoulder"(측면) | "auto"
    "front_view_min_ratio": 1.0, # auto: 어깨너비/귀-어깨거리 ≥ 1.0 이면 정면으로 간주
    "scale_ema_alpha": 0.05,     # 스케일은 '바른 자세' 구간에서만 천천히 갱신
}

# ============================ C. 시계열 단계 ============================
ONE_EURO = {"min_cutoff": 1.0, "beta": 0.007, "d_cutoff": 1.0}   # (3-5, 6-2) 픽셀 좌표 기준

CALIBRATION = {"baseline_duration_sec": 10.0, "drift_ema_alpha": 0.001, "min_valid_ratio": 0.5}  # (1-3, 7-2)

WINDOW = {"size_sec": 3.0, "stride_sec": 1.0, "min_valid_ratio": 0.5, "min_fill_ratio": 0.8}    # (6-3)

HYSTERESIS = {"enter_ratio": 0.7, "exit_ratio": 0.3, "alert_after_sec": 30.0}  # (6-3) 5/30/60으로 교체

# 기준선 대비 변화량으로 판정하는 규칙 (학습 모델 도입 전 임시 기준, 7-1 확정 후 조정)
# (비교 방식, 임계값): gt = 기준보다 증가, lt = 기준보다 감소, abs_gt = 어느 방향이든 변화
RULES = {
    "neck_angle":    ("gt", 10.0),    # 귀-어깨 선의 수직 대비 각도 증가 [deg] → 거북목
    "head_forward":  ("gt", 0.15),    # 귀가 어깨보다 앞으로 나간 거리 증가 [정규화 단위]
    "head_height":   ("lt", -0.15),   # 코가 어깨 위로 올라와 있는 높이 감소 → 구부정/엎드림
    "shoulder_tilt": ("abs_gt", 5.0), # 어깨 기울기 변화 [deg] → 좌우 기울어짐
    "head_tilt":     ("abs_gt", 8.0), # 머리 기울기 변화 [deg]
    "trunk_angle":   ("gt", 10.0),    # 몸통 기울기 증가 [deg] (골반이 보일 때만)
}

# 좌우 기울기 특징의 유효 조건: 두 점의 가로 간격(정규화 단위)이 이 값 이상일 때만 계산
# 측면 설치(3-2)에서는 양쪽 어깨·귀가 겹쳐 기울기가 노이즈뿐이므로 자동으로 제외된다
FEATURE_VALIDITY = {"min_shoulder_dx": 0.5, "min_ear_dx": 0.2}

# ============================ D. 학습 데이터 단계 ============================
LABEL_CLEANING = {"boundary_trim_sec": 0.5, "min_annotators": 2, "min_cohen_kappa": 0.7,
                  "kappa_segment_sec": 10.0}              # (7-1, 7-3)

DATA_SPLIT = {"method": "group_kfold", "n_splits": 5}      # (10-1) 또는 "loso"

KEYPOINT_AUG = {                                          # (10-1, 10-2)
    "rotation_deg": 10.0,
    "scale_range": (0.9, 1.1),
    "jitter_sigma": 0.01,
    "joint_dropout": 0.1,
    "hflip_prob": 0.5,           # 좌/우 인덱스 교환 + 방향 라벨 반전 포함
}

IMAGE_AUG = {"brightness": 0.3, "contrast": 0.2}          # (2-4) 원본 영상 저장 가능할 때만

IMBALANCE = {"method": "class_weight", "focal_gamma": 2.0}  # (6-4)

# ============================ E. 후처리 단계 ============================
POSTPROCESS = {
    # 알림 정책 (6-3, 8-2)
    "realert_interval_sec": 300.0,   # 같은 불량 구간이 계속되면 5분마다 재알림
    "alert_cooldown_sec": 60.0,      # 알림 사이 최소 간격 (자세를 잠깐 고쳤다 다시 무너지는 경우 도배 방지)
    "max_alerts_per_hour": 6,        # 시간당 알림 상한 (알림 피로 방지)
    "escalate_after_alerts": 2,      # 같은 구간에서 n번째 알림부터 강한 알림(level 2)
    # 자리 비움 처리 (4-1, 1-3)
    "absent_reset_sec": 5.0,         # 판단 가능한 프레임이 이 시간 이상 없으면 '자리 비움' → 상태 초기화
    "recalibrate_after_absent_sec": 600.0,  # 이만큼 비웠다 돌아오면 재캘리브레이션 (0이면 사용 안 함)
    # 리포트/평가용 구간 정리
    "merge_gap_sec": 3.0,            # 이 시간 이하로 끊긴 같은 상태 구간은 하나로 합침
    "min_segment_sec": 5.0,          # 이보다 짧은 구간은 앞 구간에 흡수
    "event_min_overlap": 0.3,        # 평가 시 정답 구간과 이 비율 이상 겹치면 '감지 성공'
}

# 특징 → 사용자에게 보여줄 자세 이름
REASON_NAMES = {
    "neck_angle": "거북목", "head_forward": "거북목",
    "head_height": "구부정/엎드림", "trunk_angle": "몸통 기울어짐",
    "shoulder_tilt": "좌우 기울어짐", "head_tilt": "좌우 기울어짐",
}
