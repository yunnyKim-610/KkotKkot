"""mcu-bridge 컨테이너 진입점 (뼈대)

ESP32-S3 ↔ Jetson UART 프레임: [0xAA][type][len][payload...][crc16]
- MCU → Jetson: UWB 측정, IMU, 전원 이벤트
- Jetson → MCU: 알림 명령, 카메라 전원 제어, 생존 신호(하트비트)
프로토콜 정의는 firmware/module-mcu/README.md 와 같이 관리한다.
"""
import os

UART_DEV = os.environ.get("MCU_UART", "/dev/ttyTHS1")
BAUD = int(os.environ.get("MCU_BAUD", "921600"))


def main():
    # TODO: pyserial로 UART 열기 → 프레임 파싱 → shared.messages 로 변환해 core에 전달
    # TODO: 하트비트를 1초마다 MCU로 전송 (끊기면 MCU가 Jetson 재시작)
    raise NotImplementedError("mcu-bridge 구현 예정", UART_DEV, BAUD)


if __name__ == "__main__":
    main()
