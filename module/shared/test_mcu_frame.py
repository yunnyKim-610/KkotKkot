import pytest

from shared.mcu_frame import (
    SOLO_TAG_ID,
    T_ALERT,
    T_HEARTBEAT,
    FrameParser,
    alert_frame,
    crc16,
    encode_frame,
    heartbeat_frame,
)


def test_crc16_ccitt_false_check_value():
    # CRC-16/CCITT-FALSE 표준 검증값
    assert crc16(b"123456789") == 0x29B1


def test_alert_frame_layout():
    f = alert_frame("4F2A", 2)
    assert f[:3] == bytes([0xAA, T_ALERT, 3])
    assert f[3:6] == bytes([0x2A, 0x4F, 2])        # tag_id 리틀 엔디언, level
    assert len(f) == 8


def test_parser_roundtrip_and_split_feed():
    data = alert_frame(SOLO_TAG_ID, 1) + heartbeat_frame()
    p = FrameParser()
    got = []
    for i in range(len(data)):                      # 한 바이트씩 나눠 들어와도 동작
        got += p.feed(data[i:i + 1])
    assert got == [(T_ALERT, bytes([0, 0, 1])), (T_HEARTBEAT, b"")]


def test_parser_skips_garbage_and_bad_crc():
    good = heartbeat_frame()
    bad = bytearray(alert_frame("0001", 1)); bad[-1] ^= 0xFF
    assert FrameParser().feed(b"\x00\x13log text" + bytes(bad) + good) == [(T_HEARTBEAT, b"")]


def test_parser_resyncs_after_stray_sof():
    # 잡음 속 0xAA가 그럴듯한 길이를 만들어도, 뒤따르는 데이터가 쌓이면 CRC로 걸러지고 다시 맞춰진다
    p = FrameParser()
    got = p.feed(b"\xaa\x05\x10")
    for _ in range(6):
        got += p.feed(heartbeat_frame())
    assert len(got) >= 3 and all(g == (T_HEARTBEAT, b"") for g in got)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        alert_frame("10000", 1)
    with pytest.raises(ValueError):
        alert_frame("0001", 3)
    with pytest.raises(ValueError):
        encode_frame(0x01, bytes(65))
