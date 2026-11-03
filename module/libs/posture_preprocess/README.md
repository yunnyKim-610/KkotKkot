# 바른 자세 감지 로봇 – 데이터 전처리 코드

대화에서 정리한 전처리 파이프라인(A 영상 → B 키포인트 → C 시계열 → D 학습 데이터)을 구현한 코드입니다.
현장 조사 결과가 아직 반영되지 않은 **일반 조건 기준 초기값**이며, 조사 결과에 맞춰 `config.py`만 수정하면 됩니다.

## 폴더 구조

```
posture_preprocess/
  config.py     모든 파라미터 (주석에 체크리스트 근거 항목 번호)
  backends.py   포즈 추정 모델 연결부 (기본: YOLO pose, COCO-17 키포인트)
  video.py      A. 프레임 샘플링, 왜곡 보정, 안정화, 조명 보정, 대상자 고정, ROI, 얼굴 비식별화
  keypoints.py  B. 신뢰도 필터, 관절 마스킹, 결측 보간, 정규화
  temporal.py   C. One Euro 필터, 개인 기준선/드리프트 보정, 규칙 판정, 윈도우+히스테리시스
  features.py   C2. 자세 특징 (목 각도, 머리 전방 거리, 머리 높이, 어깨·머리 기울기, 몸통 각도)
  dataset.py    D. 오프라인 세션 정제, 라벨 정제, 사용자 단위 분할, 증강, 윈도우화, 불균형 처리
  pipeline.py   실시간 파이프라인 (위 모듈을 순서대로 연결)
  postprocess.py E. 후처리: 자리 비움 처리, 자세 유형 판별, 알림 정책, 구간 정리, 세션 리포트, 성능 평가
run_realtime.py 웹캠/영상 실행 예시
tests/          카메라·모델 없이 합성 데이터로 동작 확인
```

## 실행

```bash
pip install -r requirements.txt
python -m pytest tests -q                       # 동작 확인
python run_realtime.py                          # 웹캠 (시작 후 10초간 바른 자세 유지 → 캘리브레이션)
python run_realtime.py --save session01.npz     # 키포인트·특징·상태만 저장 (원본 영상 저장 안 함)
python run_realtime.py --report report.md       # 종료 시 세션 리포트 저장
```
실행 중 `c` 키로 재캘리브레이션, `q` 키로 종료합니다.

## 실시간 처리 순서

```
A1 샘플링 → A2 왜곡 보정 → A3 안정화 → A4 조명 보정(이전 프레임 ROI 기준)
→ 포즈 추정 → A5 검출 필터·대상자 ID 고정·ROI 갱신
→ B1 신뢰도 필터 → B2 관절 마스킹 → B3 결측 처리 → C1 One Euro(픽셀 좌표)
→ B4 정규화 → C2 특징 → C3 기준선 대비 변화량 → 규칙 판정 → C4 윈도우·히스테리시스
→ A6 얼굴 비식별화 (포즈 추정 후, 저장·표시용 프레임에만)
→ E1 자리 비움 처리 → E2 자세 유형 판별 → E3 알림 정책            (postprocess.PostProcessor)
```

## 후처리 (postprocess.py)

전처리·판정까지는 "지금 자세가 흐트러졌는가"만 답합니다. 후처리는 그 판정을 **사용자에게 언제, 어떻게 알릴지**와 **기록을 어떻게 정리·평가할지**를 담당합니다.

| 단계 | 하는 일 | 왜 필요한가 | 주요 설정 (`POSTPROCESS`) |
|---|---|---|---|
| E1 자리 비움 처리 | 사람이 5초 이상 안 보이면 상태 초기화, 10분 이상 비웠다 돌아오면 재캘리브레이션 | 이 처리가 없으면 구부정하게 있다가 자리를 떠도 '불량' 상태가 유지되어 빈자리에 알림이 울립니다 | `absent_reset_sec` 5, `recalibrate_after_absent_sec` 600 |
| E2 자세 유형 판별 | 불량 구간 동안 기준을 넘은 특징을 누적해 가장 많은 유형을 이유로 표시 | "자세가 나빠요"보다 "거북목 자세가 30초째예요"가 교정에 도움이 됩니다 | `REASON_NAMES` |
| E3 알림 정책 | 지속 시간 조건, 재알림 간격, 쿨다운, 시간당 상한, 단계적 강도 | 알림이 너무 잦으면 사용자가 로봇을 꺼버립니다(알림 피로) | `realert_interval_sec` 300, `alert_cooldown_sec` 60, `max_alerts_per_hour` 6, `escalate_after_alerts` 2 |
| E4 구간 정리 | 3초 이하로 끊긴 같은 상태는 병합, 5초 미만 구간은 흡수 | 리포트와 평가에서 구간 수가 노이즈로 부풀지 않게 합니다 | `merge_gap_sec` 3, `min_segment_sec` 5 |
| E5 세션 리포트 | 바른 자세 비율, 불량 구간 수·최장 시간, 유형별 시간, 알림 횟수, 10분 단위 추이 | 사용자 피드백과 장기 추적 | `session_report(block_sec=600)` |
| E6 성능 평가 | 프레임 단위 정밀도·재현율·F1, 구간 단위 감지율, 시간당 오알림, 알림 지연 | `RULES`·`HYSTERESIS` 임계값을 숫자로 비교하며 조정하기 위해 | `event_min_overlap` 0.3 |

```python
from posture_preprocess.postprocess import PostProcessor, evaluate
post = PostProcessor(pipe)
ev = post.update(pipe.process(frame, t))   # ev["alert"], ev["level"], ev["reason"], ev["message"]
rep, md = post.close()                      # 세션 종료 시 리포트 (dict, 마크다운)
metrics = evaluate(gt_ts, gt_bad, pred_ts, pred_bad, alert_times)   # 라벨이 있는 세션으로 평가
```

임계값 조정 시에는 `evaluate()` 결과에서 **시간당 오알림(false_alerts_per_hour)**과 **구간 감지율(event_recall)**을 함께 보세요. 프레임 단위 F1이 높아도 오알림이 잦으면 실사용에서는 실패입니다.

## 앞서 정리한 내용에서 구현하며 바뀐 점

- **C1 평활화를 B4 정규화보다 앞에 배치했습니다.** 권장 파라미터(beta 0.007)가 픽셀 좌표 기준 값이라, 정규화된 좌표(값이 1 내외)에 쓰면 필터가 거의 반응하지 않습니다. 각도 특징은 순서와 무관하게 같습니다.
- **실시간 결측 처리는 선형 보간 대신 '마지막 값 유지(0.5초)'입니다.** 선형 보간은 미래 프레임이 필요해 지연이 생깁니다. 학습 데이터(오프라인)에서는 선형 보간을 씁니다.
- **기준선은 평균 대신 중앙값으로 잡습니다.** 캘리브레이션 중 잠깐 움직여도 기준선이 흔들리지 않습니다.
- **정규화 스케일은 '바른 자세' 상태일 때만 갱신합니다.** 거북목 자세에서는 귀–어깨 거리 자체가 변하므로, 계속 갱신하면 거북목 변화가 정규화로 지워집니다.
- **좌우 기울기 특징은 두 점이 충분히 떨어져 있을 때만 계산합니다** (`FEATURE_VALIDITY`). 측면 설치에서는 양쪽 어깨·귀가 겹쳐 기울기 값이 노이즈뿐이라 자동으로 제외됩니다.
- **판정 규칙(`RULES`)은 임시 기준입니다.** 7-1(라벨 기준)이 확정되면 임계값을 조정하거나, 학습 모델을 `PosturePipeline(classifier=...)`로 넣어 교체하세요.
- **증강의 회전·스케일·반전은 세션 전체에 같은 값을 적용합니다.** 회전 10°는 목 각도 판정 임계값(10°)과 같은 크기라, 프레임마다 다르게 돌리면 라벨 의미가 깨집니다. 세션 단위로 돌리면 캘리브레이션 구간도 함께 돌아가 기준선 대비 변화량이 보존됩니다.

## 학습 데이터 만들기 (dataset.py)

세션 = 한 사용자가 한 번 앉아서 녹화한 키포인트 기록이며, **앞 10초는 바른 자세 캘리브레이션 구간**이어야 합니다.

```python
from posture_preprocess import dataset as D
nxy   = D.clean_session(raw_kpts, raw_conf, ts)            # B1~B4, C1 (오프라인)
keep  = D.trim_label_boundaries(labels, ts)                # 자세 전환 경계 ±0.5초 제외
review = D.flag_low_agreement(labels_a, labels_b, ts)      # 라벨러 간 kappa < 0.7 구간
for train_subj, val_subj in D.subject_splits(subject_ids): # 사용자 단위 분할 (증강보다 먼저)
    nxy_aug, lab_aug = D.augment_session(nxy, labels, flip_label_map={...})  # 학습 세트에만
    X = D.baseline_delta(D.session_features(nxy_aug), ts)
    Xw, yw = D.make_windows(X, lab_aug, ts, keep, fps=15)
weights = D.class_weights(yw)                              # 또는 D.make_focal_loss()
```

## 현장 조사 결과에 따라 바꿀 곳

| 조사 항목 | 수정할 설정 |
|---|---|
| 3-2 설치 방향 | `NORMALIZATION["scale_ref"]` (정면 `shoulder_width`, 측면 `ear_shoulder`) |
| 3-5 거치 안정성 | `STABILIZATION["enabled"]` |
| 3-7 렌즈 화각 | `UNDISTORT["enabled"]`, 저사양이면 `keypoints_only=True` |
| 5-1 가림 요소 | `JOINT_MASK["exclude"]` |
| 6-1 감지할 자세 | `RULES`에서 해당 특징만 남기기 |
| 6-3 최소 지속 시간 | `HYSTERESIS["alert_after_sec"]` |
| 8-1 연산 장치 | 라즈베리파이면 `FRAME_SAMPLING` 5fps, `run_realtime.py --imgsz 320` |
| 9-2 비식별화 | `ANONYMIZE["mode"]` (`none` / `blur` / `exclude`) |
| 1-3 연속 사용 시간 | `POSTPROCESS["max_alerts_per_hour"]`, `realert_interval_sec` |
| 4-1 타인 등장 | `POSTPROCESS["absent_reset_sec"]` (대상자를 놓치는 일이 잦으면 늘리기) |
