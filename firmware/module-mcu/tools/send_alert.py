"""PC에서 ESP32-S3로 알림 프레임을 보내 보드 LED를 시험한다 (Jetson 없이 단독 테스트).

펌웨어는 sdkconfig.solo 로 빌드해야 USB(COM 포트)로 프레임을 받는다.

    python firmware/module-mcu/tools/send_alert.py COM5 --level 1
    python firmware/module-mcu/tools/send_alert.py COM5 --level 2 --repeat 3

필요: pip install pyserial
"""
import argparse
import sys
import time
from pathlib import Path

import serial

# module/shared/mcu_frame.py 를 그대로 써서 Jetson과 같은 프레임 형식으로 보낸다
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "module"))
from shared.mcu_frame import SOLO_TAG_ID, alert_frame, heartbeat_frame  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="ESP32-S3 COM 포트 (예: COM5)")
    ap.add_argument("--level", type=int, choices=(1, 2), default=1, help="1 보통(노랑), 2 강하게(빨강)")
    ap.add_argument("--tag", default=SOLO_TAG_ID, help="태그 번호(16진수). 0000이면 보드 LED")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--interval", type=float, default=3.0, help="반복 간격(초)")
    args = ap.parse_args()

    # DTR/RTS를 건드리면 보드가 리셋되므로 열 때 끈 상태로 둔다
    with serial.Serial() as s:
        s.port, s.baudrate, s.dtr, s.rts = args.port, 115200, False, False
        s.open()
        for i in range(args.repeat):
            s.write(heartbeat_frame() + alert_frame(args.tag, args.level))
            print(f"[{i + 1}/{args.repeat}] 알림 전송: tag={args.tag} level={args.level}")
            if i + 1 < args.repeat:
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
