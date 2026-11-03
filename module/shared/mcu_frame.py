"""Jetson ↔ ESP32-S3 UART 프레임 (firmware/module-mcu/main/mcu_frame.c 와 같은 규칙)

프레임: [0xAA][type 1B][len 1B][payload len B][crc16 2B, 리틀 엔디언]
- CRC는 CRC-16/CCITT-FALSE (다항식 0x1021, 초기값 0xFFFF), 범위는 type·len·payload.
- 형식을 바꾸면 펌웨어 쪽과 firmware/module-mcu/README.md 를 함께 고친다.
"""
from __future__ import annotations

import struct

SOF = 0xAA
MAX_PAYLOAD = 64

# 프레임 종류 (README 표와 같게 유지)
T_UWB = 0x01          # MCU → Jetson
T_IMU = 0x02          # MCU → Jetson
T_POWER = 0x03        # MCU → Jetson
T_ALERT = 0x10        # Jetson → MCU: tag_id u16 LE, level u8
T_CAMERA_POWER = 0x11  # Jetson → MCU
T_HEARTBEAT = 0x12    # Jetson → MCU

# 예약 태그 번호: 태그 없이 모듈 자체(보드 LED)로 알림. 단독 테스트 모드에서만 쓴다.
SOLO_TAG_ID = "0000"


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def encode_frame(ftype: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload가 너무 깁니다: {len(payload)} > {MAX_PAYLOAD}")
    body = bytes([ftype, len(payload)]) + payload
    return bytes([SOF]) + body + struct.pack("<H", crc16(body))


def alert_frame(tag_id: str, level: int) -> bytes:
    """AlertCommand(tag_id 16진수 문자열, level) → 0x10 프레임"""
    tag = int(tag_id, 16)
    if not 0 <= tag <= 0xFFFF:
        raise ValueError(f"tag_id 범위 밖: {tag_id}")
    if level not in (1, 2):
        raise ValueError(f"level은 1 또는 2: {level}")
    return encode_frame(T_ALERT, struct.pack("<HB", tag, level))


def heartbeat_frame() -> bytes:
    return encode_frame(T_HEARTBEAT)


class FrameParser:
    """바이트 흐름에서 프레임을 꺼낸다. 깨진 프레임은 버리고 다음 SOF부터 다시 찾는다."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self._buf += data
        out: list[tuple[int, bytes]] = []
        while True:
            start = self._buf.find(SOF)
            if start < 0:
                self._buf.clear()
                return out
            del self._buf[:start]
            if len(self._buf) < 3:
                return out
            ftype, length = self._buf[1], self._buf[2]
            if length > MAX_PAYLOAD:
                del self._buf[:1]
                continue
            total = 3 + length + 2
            if len(self._buf) < total:
                return out
            body = bytes(self._buf[1:3 + length])
            (crc,) = struct.unpack("<H", self._buf[3 + length:total])
            if crc == crc16(body):
                out.append((ftype, body[2:]))
                del self._buf[:total]
            else:
                del self._buf[:1]
