"""
바른 자세 감지 로봇 - 전처리 초기 파라미터 설정
※ 현장 조사 결과 반영 전의 '일반 조건 기준' 초기값입니다.
※ 주석의 (x-x)는 현장 조사 체크리스트 근거 항목 번호입니다.
"""

# =============================================================
# A. 영상 단계
# =============================================================

# A1. 프레임 샘플링 (3-6, 8-2)
FRAME_SAMPLING = {
    "target_infer_fps": 15,      # 추론 10~15fps
    "frame_skip": 2,             # 30fps 입력 기준 2~3프레임마다 1회 추론
}

# A2. 렌즈 왜곡 보정 - 광각/어안일 때만 (3-7)
UNDISTORT = {
    "enabled": False,
    "calib_images": 20,          # 체커보드 캘리브레이션 15~20장
    "precompute_map": True,      # cv2.initUndistortRectifyMap 으로 맵 사전 계산
    "keypoints_only": False,     # 저사양이면 True: 키포인트에만 cv2.undistortPoints 적용
}

# A3. 영상 안정화 - 이동형/진동 거치일 때만 (3-5)
STABILIZATION = {
    "enabled": False,
    "orb_features": 500,         # 배경 특징점(ORB) 개수
    "smoothing_radius": 15,      # 이동평균 반경 (프레임)
}

# A4. 조명 보정 (2-2, 2-3, 2-4)
GAMMA = {
    "enabled": True,
    "brightness_threshold": 80,  # 평균 밝기 < 80 일 때만 적용
    "gamma": 0.7,                # 0.6~0.8
}
CLAHE = {
    "enabled": True,
    "channel": "LAB_L",          # LAB의 L 채널에만 적용
    "clip_limit": 2.0,
    "tile_grid_size": (8, 8),
    "roi_only": True,            # 저사양이면 ROI에만 적용
}

# A5. 대상자 검출 / ID 고정 / ROI 크롭 (4-1, 5-2, 5-3)
PERSON_DETECTION = {
    "min_confidence": 0.5,       # 검출 신뢰도 하한
    "min_box_area_ratio": 0.05,  # 화면 대비 최소 박스 면적 5%
}
TARGET_TRACKING = {
    "iou_threshold": 0.3,        # 이전 박스와 IoU ≥ 0.3 이면 동일인 유지
    "lost_timeout_sec": 5.0,     # 5초간 미검출 시 대상자 재선택
}
ROI_CROP = {
    "margin_ratio": 0.2,         # 박스 기준 상하좌우 15~20% 여백
}

# A6. 얼굴 비식별화 - 반드시 포즈 추정 '후'에 적용 (9-1, 9-2)
ANONYMIZE = {
    "enabled": True,
    "apply_after_pose": True,
}

# =============================================================
# B. 키포인트 단계
# =============================================================

# B1. 키포인트 신뢰도 필터 (4-3, 4-4)
KEYPOINT_FILTER = {
    "min_confidence": 0.3,       # 일반 모델 기준
    "mediapipe_visibility": 0.5, # MediaPipe 사용 시
}

# B2. 상시 가림 관절 마스킹 (1-2, 5-1)
JOINT_MASK = {
    "exclude": ["left_knee", "right_knee", "left_ankle", "right_ankle"],  # 책상 착석 시 하체 제외
}

# B3. 결측 보간 (5-1)
INTERPOLATION = {
    "method": "linear",
    "max_gap_sec": 0.5,          # 0.5초 이하만 보간, 초과 시 판정 보류
}

# B4. 위치·스케일 정규화 (3-4, 4-2)
NORMALIZATION = {
    "origin": "shoulder_center", # 원점 = 어깨 중점
    "scale_ref": "shoulder_width",  # 정면: shoulder_width / 측면: ear_shoulder_dist
}

# =============================================================
# C. 시계열 단계
# =============================================================

# C1. One Euro Filter (3-5, 6-2)
ONE_EURO = {
    "min_cutoff": 1.0,           # 떨림 심하면 0.5
    "beta": 0.007,               # 1초 이내 반응 필요 시 0.02~0.05
    "d_cutoff": 1.0,
}

# C3. 개인 캘리브레이션 / 드리프트 재보정 (1-3, 7-2)
CALIBRATION = {
    "baseline_duration_sec": 10, # 시작 시 바른 자세 10초 평균 = 기준선
    "drift_ema_alpha": 0.001,    # '바른 자세' 판정 구간에서만 갱신
}

# C4. 슬라이딩 윈도우 / 히스테리시스 판정 (6-3)
WINDOW = {
    "size_sec": 3.0,
    "stride_sec": 1.0,
}
HYSTERESIS = {
    "enter_ratio": 0.7,          # 윈도우의 70% 이상 불량 → 불량 진입
    "exit_ratio": 0.3,           # 30% 이하 → 해제
    "alert_after_sec": 30,       # 6-3 조사값으로 교체 (5 / 30 / 60)
}

# =============================================================
# D. 학습 데이터 단계 (오프라인)
# =============================================================

# D1. 라벨 정제 (7-1, 7-3)
LABEL_CLEANING = {
    "boundary_trim_sec": 0.5,    # 자세 전환 경계 ±0.5초 제외
    "min_annotators": 2,
    "min_cohen_kappa": 0.7,      # 미만 구간은 재검토
}

# D2. 데이터 분할 - 반드시 증강 '전'에 수행 (10-1)
DATA_SPLIT = {
    "method": "group_kfold",     # 사용자 단위 분할 (또는 "loso")
    "group_key": "subject_id",
}

# D3. 데이터 증강 (2-4, 10-1, 10-2)
KEYPOINT_AUG = {
    "rotation_deg": 10,          # ±10°
    "scale_range": (0.9, 1.1),
    "jitter_sigma": 0.01,        # 정규화 좌표 기준
    "joint_dropout": 0.1,
    "hflip": True,               # ※ 좌/우 인덱스 교환 + 방향 라벨도 반전 필수
}
IMAGE_AUG = {
    "enabled": False,            # 영상 입력 모델 학습 시에만 / 9-1 저장 불가면 사용 불가
    "brightness": 0.3,           # ±30%
    "contrast": 0.2,             # ±20%
}

# D4. 클래스 불균형 처리 (6-4)
IMBALANCE = {
    "method": "class_weight",    # "class_weight" (빈도 역수) 또는 "focal_loss"
    "focal_gamma": 2.0,
}