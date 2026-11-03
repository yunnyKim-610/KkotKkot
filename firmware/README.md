# firmware

| 폴더 | 대상 | 칩 | 빌드 |
| --- | --- | --- | --- |
| module-mcu | 센싱 모듈 보조 MCU | ESP32-S3 | ESP-IDF (`idf.py build`) |
| tag | 근로자 UWB 태그 | Qorvo DWM3001C (nRF52833 내장) | Nordic SDK / Qorvo 예제 기반 (예정) |

## module-mcu (ESP32-S3) 역할
전원 감시와 안전 종료 요청, Jetson 하트비트 감시와 재시작, UWB 방향 측정 처리, Jetson과 UART 통신, 로봇과 CAN(TWAI) 통신.

### UART 프레임 (Jetson ↔ MCU)
`[0xAA][type 1B][len 1B][payload][crc16 2B]`

| type | 방향 | 내용 |
| --- | --- | --- |
| 0x01 | MCU→Jetson | UWB 측정 (tag_id, bearing, distance) |
| 0x02 | MCU→Jetson | IMU 기울기 |
| 0x03 | MCU→Jetson | 전원 이벤트 (brownout, shutdown_request) |
| 0x10 | Jetson→MCU | 알림 명령 (tag_id, level) |
| 0x11 | Jetson→MCU | 카메라 전원 on/off |
| 0x12 | Jetson→MCU | 하트비트 |

### ESP32 사용 시 주의할 점은 CLAUDE.md 의 "ESP32 주의사항" 참고
