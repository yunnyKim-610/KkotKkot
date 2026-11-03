# module: 로봇 장착 센싱 모듈 소프트웨어 (Jetson Orin NX)

```
module/
├── libs/posture_preprocess/  전처리·판정·후처리 라이브러리 (테스트 17개, 설정은 config.py 한 곳)
├── shared/messages.py        컨테이너 간 메시지 형식 (버전 포함, 영상 필드 없음)
├── containers/               역할별 컨테이너 5개 (vision, core, mcu-bridge, robot-bridge, telemetry)
└── compose/docker-compose.yml  실행 구성 (vision 네트워크 차단, 비특권, 읽기 전용)
```

| 컨테이너 | 역할 | 네트워크 | GPU |
| --- | --- | --- | --- |
| vision | 카메라 → 포즈 추정 → 3D 복원, 좌표만 출력 | 없음 | 사용 |
| core | UWB 매칭, 자세 판정, 알림 결정, 통계 집계 | 없음 | 미사용 |
| mcu-bridge | ESP32-S3와 UART | 없음 | 미사용 |
| robot-bridge | 로봇과 ROS2 | 로봇 이더넷 | 미사용 |
| telemetry | 공정 단위 통계 → Supabase | 서버 방향만 | 미사용 |

컨테이너끼리는 `/run/kkotkkot` 의 유닉스 도메인 소켓으로 줄 단위 JSON을 주고받는다.
