# CLAUDE.md — 꼿꼿 AI (KkotKkot)

이 파일은 Claude가 이 저장소에서 작업할 때 먼저 읽는 안내서다. 결정이 바뀌면 이 파일과 `docs/decisions.md`를 함께 고친다.

## 1. 한 줄 소개

**꼿꼿 AI**는 기존 서비스 로봇(공장 물류 로봇, 사무실 배송 로봇)에 붙이는 **자세 코칭 센싱 모듈**이다. 로봇이 본업 중 멈춘 순간 1~5m 앞 근로자의 자세를 분석하고, 위험한 자세가 이어지면 그 근로자의 **UWB 태그만 진동**시킨다. 얼굴 인식은 쓰지 않고, 영상은 기기 밖으로 나가지 않는다.

이 제품은 자세 인식 개선 보조 도구이며, 질환 예방·치료·진단을 표방하지 않는다.

## 2. 현재 방향 (가장 먼저 확인)

저장소에는 두 가지 방향이 섞여 있다.

| 구분 | 내용 | 위치 |
| --- | --- | --- |
| **현재 기준 (로봇 모듈)** | 서비스 로봇 장착 모듈 + UWB 태그 진동 + 근로자 앱 | 이 파일, `docs/decisions.md`, `module/`, `firmware/`, `ml/`, `report/*report`, `code/DB-main/docs/05~10` |
| 이전 안 (천장 카메라) | 천장 PoE 카메라 + Jetson Orin Nano + ESP32 경광등·부저 + MQTT | `PRD/PRD.md`, `code/DB-main/docs/01~04` 일부 |

- 새 코드와 문서는 **로봇 모듈 기준**으로 작성한다.
- `PRD/PRD.md`는 아직 갱신 전이다(결정 #15 미결). PRD 내용과 충돌하면 임의로 한쪽을 고치지 말고 사용자에게 확인한다.

## 3. 절대 원칙 (어기는 변경은 하지 않는다)

1. **영상은 저장·전송하지 않는다.** 영상은 `vision` 컨테이너 메모리에서만 처리하고, 밖으로는 관절 좌표만 보낸다. 영상을 디스크, 로그, DB, 네트워크로 보내는 코드를 만들지 않는다.
2. **얼굴 인식·신원 식별을 하지 않는다.** 사람과 태그는 위치(방향·거리)로만 매칭한다. 태그 ID는 익명 번호다.
3. **태그를 지닌 사람만 분석한다.** 태그가 매칭되지 않은 사람의 데이터는 즉시 버린다.
4. **개인 기록은 근로자 본인에게만.** 서버·DB에는 공정 단위 집계만 저장한다. 태그 ID, 좌표, 개인별 알림 기록을 DB 스키마에 넣지 않는다.
5. **인사 평가·징계 용도의 기능을 만들지 않는다.** (개인별 순위, 개인 기록 열람 등)
6. **비밀값을 커밋하지 않는다.** Supabase service role 키, 기기 토큰, `.env`, `device.env`는 저장소 밖에 둔다. 기기에는 service role 키를 두지 않는다.

## 4. 저장소 구조

```
KkotKkot/
├── CLAUDE.md                 이 파일
├── index.html                제품 소개 홈페이지 (GitHub Pages 시작 파일)
├── images/                   홈페이지 이미지 (앱 화면 app-*.png 포함)
├── design/                   홈페이지·앱 시안
├── PRD/PRD.md                제품 요구사항 (이전 안 기준, 갱신 필요)
├── report/                   보고서 (전처리, 추론 엔진, 부품 선정 등)
├── docs/decisions.md         결정 기록 (결정이 바뀌면 여기부터 수정)
├── module/                   센싱 모듈 소프트웨어 (Jetson)
│   ├── libs/posture_preprocess/  전처리·판정·후처리 라이브러리 + 테스트
│   ├── shared/messages.py        컨테이너 간 메시지 형식
│   ├── containers/               vision, core, mcu-bridge, robot-bridge, telemetry
│   └── compose/docker-compose.yml
├── firmware/
│   ├── module-mcu/           보조 MCU (ESP32-S3, ESP-IDF)
│   └── tag/                  근로자 태그 (DWM3001C, 예정)
├── ml/                       YOLO11s-pose 학습 설정·스크립트 (데이터·가중치는 git 제외)
├── app/                      근로자용 앱 (설계 단계)
├── code/DB-main/             Supabase: 홈페이지 FAQ RAG + 통계 저장(zone_stats)
└── .github/workflows/        CI (ci.yml, firmware.yml)
```

## 5. 시스템 구조 요약

**하드웨어 (센싱 모듈)**
- SBC: Jetson Orin NX 16GB — 포즈 추정, 3D 복원, 판정
- 보조 MCU: ESP32-S3 — 전원 감시·안전 종료, Jetson 감시·재시작, UWB 처리, 로봇 CAN
- 센서: 스테레오 깊이 카메라(USB 3), UWB 방향 측정(Qorvo DW3000 계열, 듀얼 안테나), IMU
- 전원: 로봇 배터리 24/48V → 보호 회로 → 광입력 DC-DC → 19V / 5V / 3.3V(저잡음 LDO)
- 프라이버시 표시등은 카메라 전원선에 하드웨어로 직결 (소프트웨어로 끌 수 없게)

**근로자 태그**: Qorvo DWM3001C (nRF52833 + DW3110 + 가속도계), 진동 모터, 리튬 배터리

**소프트웨어 (Jetson 위 컨테이너 5개)**

```
카메라 → [vision] --좌표만--> [core] --알림--> [mcu-bridge] → ESP32 → UWB/BLE → 태그 진동
                                 ↑  ↑
              [mcu-bridge] UWB ──┘  └── [robot-bridge] 정차 상태 (ROS2)
                                 ↓
                         [telemetry] --공정 단위 통계--> Supabase (Edge Function → zone_stats)
```

- `vision`만 GPU를 쓰고, 네트워크가 차단되어 있다.
- 컨테이너 간 통신은 `/run/kkotkkot`의 유닉스 도메인 소켓, 줄 단위 JSON (`module/shared/messages.py`).
- 메시지 형식을 바꾸면 `VERSION`을 올리고, 받는 쪽은 모르는 필드를 무시하게 유지한다.

## 6. 기술 스택

| 영역 | 선택 | 비고 |
| --- | --- | --- |
| 포즈 모델 | YOLO11s-pose (COCO-17) | Ultralytics AGPL-3.0 → 상용 전 라이선스 결정 필요 (결정 #11) |
| 학습 | 2단계 미세조정, imgsz 640, AdamW, lr0 0.001 | `ml/pose/configs/train.yaml` |
| 추론 엔진 | ONNX Runtime + TensorRT EP (→ CUDA → CPU) | 입력 640×640 고정, 엔진 캐시 볼륨 |
| 전처리·판정 | Python, NumPy, OpenCV | `module/libs/posture_preprocess/config.py`가 모든 파라미터의 단일 출처 |
| 컨테이너 | Docker + NVIDIA Container Toolkit + Compose | JetPack 버전과 기반 이미지 맞추기, digest 고정 |
| 로봇 연동 | ROS2 Humble (robot-bridge 안에만) | |
| 보조 MCU | ESP32-S3, ESP-IDF v5.x, FreeRTOS | 아래 주의사항 필수 |
| DB | Supabase (Postgres) | `code/DB-main/supabase/` |
| CI | GitHub Actions | ruff, pytest, ESP-IDF 빌드 |

## 7. ESP32 사용 시 주의사항

보조 MCU를 ESP32-S3로 정했다. 이 칩은 안전 기능(전원 감시, Jetson 재시작)을 맡으므로 다음을 지킨다.

1. **Wi-Fi·BLE는 끈다.** 무선은 Jetson이 맡는다. ESP32 무선을 켜면 순간 전류가 커지고 ADC 잡음이 늘며, 안전 태스크의 타이밍이 흔들린다.
2. **CAN은 클래식 CAN만 된다.** ESP32-S3의 TWAI는 CAN 2.0이며 CAN FD를 지원하지 않는다. 로봇 본체가 CAN FD를 쓰면 외부 CAN FD 컨트롤러가 필요하다. 외부 CAN 트랜시버(절연형 권장)는 항상 필요하다.
3. **ADC 정확도가 낮다.** 내장 ADC는 비선형성과 잡음이 있다. 보정 API(`adc_cali`)를 쓰고, ADC1 채널만 쓴다. 전원 저하처럼 빠른 판단은 ADC 폴링에만 의존하지 말고, 외부 전압 감시 IC나 비교기 출력을 GPIO 인터럽트로 받는다.
4. **부팅 스트래핑 핀을 피한다.** GPIO0, GPIO3, GPIO45, GPIO46은 부팅 모드에 영향을 준다. Jetson 리셋·전원 제어선에 쓰지 않는다.
5. **신호 전압을 확인한다.** ESP32는 3.3V다. Jetson 모듈 쪽 핀이 1.8V인 경우 레벨 시프터를 둔다. Jetson 재시작·전원 버튼 제어는 오픈 드레인으로 연결한다.
6. **태스크 우선순위를 지킨다.** 전원 감시 > Jetson 감시 > UWB > UART > CAN 순. 태스크 워치독과 브라운아웃 감지를 켠다 (`sdkconfig.defaults`).
7. **UWB 드라이버 이식 부담을 일찍 확인한다.** Qorvo 예제는 nRF·STM32 중심이라 ESP32로 옮기는 작업이 필요할 수 있다. 개발 초기에 SPI 통신과 방향 측정을 먼저 검증한다.
8. **산업용 온도 등급 모듈을 고른다** (-40°C 이상). 양산 전 보안 부팅과 플래시 암호화를 켠다.

## 8. DB 저장 규칙 (Supabase)

- 테이블: `devices`(기기 등록, 토큰은 SHA-256 해시만), `zone_stats`(공정 단위 집계).
- **기기는 DB에 직접 쓰지 않는다.** telemetry → Edge Function `ingest-stats`(헤더 `x-device-token`) → 함수 안에서만 service role로 insert.
- `zone_stats`에 넣을 수 있는 값: 기기 ID, 구역, 기간, 관찰 시간, 자세 유형별 시간, 알림 수. **태그 ID·좌표·개인 기록은 넣지 않는다.**
- 스키마 변경은 `code/DB-main/supabase/migrations/`에 새 파일(타임스탬프 접두사)로 추가하고, 기존 마이그레이션을 고치지 않는다.
- 같은 Supabase 프로젝트에 홈페이지 FAQ RAG(`faqs`, `rag-search`)가 있다. 통계 테이블과 섞지 않는다.
- 연결이 끊기면 telemetry가 로컬 큐에 쌓았다가 재전송한다. 큐에도 집계값만 둔다.

## 9. CI

- `ci.yml`: push·PR마다 `ruff check module ml` → `posture_preprocess` 테스트 → 메시지 형식 테스트.
- `firmware.yml`: `firmware/module-mcu/` 변경 시 ESP-IDF(esp32s3) 빌드.
- CI가 실패한 상태로 main에 합치지 않는다. 테스트를 지우거나 건너뛰어 통과시키지 않는다.
- 새 판정 로직이나 메시지 형식을 추가하면 테스트도 함께 추가한다. 테스트는 카메라·GPU 없이 합성 데이터로 돈다.

## 10. 자주 쓰는 명령

```bash
# 린트
ruff check module ml

# 전처리·후처리 테스트
cd module/libs/posture_preprocess && python -m pytest tests -q

# 메시지 형식 테스트
cd module && python -m pytest shared -q

# 학습 (학습 PC)
python ml/pose/scripts/train.py --data ml/pose/configs/data.yaml
python ml/pose/scripts/export_onnx.py runs/pose/stage2/weights/best.pt

# ESP32 펌웨어 빌드
cd firmware/module-mcu && idf.py set-target esp32s3 && idf.py build

# Jetson에서 컨테이너 실행
docker compose -f module/compose/docker-compose.yml up -d

# 홈페이지 미리보기
python -m http.server 8000   # http://localhost:8000
```

## 11. 작업 규칙

**코드**
- Python 3.10, ruff 통과. 설정값은 코드에 하드코딩하지 말고 `config.py`나 `ml/pose/configs/*.yaml`에 둔다.
- 주석과 문서는 한국어로 쓴다.
- 판정 임계값(예: 목 각도 +10°, 30초 지속)은 아직 **초기값**이다. 바꿀 때는 이유를 커밋 메시지에 적는다.

**문서·홈페이지**
- 수치나 통계를 지어내지 않는다. 출처가 없으면 `[출처 필요]` 같은 표시를 남긴다.
- 홈페이지 기술 소개 글은 `<article class="inference-report">` 스타일로 통일한다 (글꼴은 페이지 상속, 제목 28px, 소제목 22px).
- 개발 중인 기능은 "목표", "(계획)", "개발 중"으로 표시한다.

**Git**
- `git push --force`를 쓰지 않는다. (README의 예시 명령에 포함되어 있지만 협업 기록을 지울 수 있다)
- 커밋은 작게, 메시지는 한국어로 무엇을 왜 바꿨는지 쓴다.
- 데이터셋, 모델 가중치(.pt/.onnx/.engine), 촬영 이미지는 커밋하지 않는다.

**결정이 필요한 변경**
- 3장 절대 원칙, 2장 방향, `docs/decisions.md`의 확정 항목을 바꾸는 변경은 먼저 사용자에게 확인한다.

## 12. 열린 질문

- [ ] PRD를 로봇 모듈 기준으로 갱신할지 (결정 #15)
- [ ] YOLO11 상용 라이선스 구매 vs RTMPose/RTMO 전환 (결정 #11)
- [ ] 협력할 로봇 제조사와 ROS2 인터페이스, CAN 사양(클래식 CAN / CAN FD)
- [ ] UWB 매칭 오전송률 실측 (두 사람이 나란히 있을 때 1% 미만 목표)
- [ ] 사무용 보급형에 Orin Nano 8GB가 충분한지 벤치마크
