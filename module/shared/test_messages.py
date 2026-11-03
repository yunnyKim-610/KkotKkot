from shared.messages import AlertCommand, KeypointFrame, ZoneStats, decode, encode


def test_roundtrip():
    for m in (
        KeypointFrame(t=1.0, track_id=3, kpts3d=[[0.0, 0.0, 1.0]] * 17, conf=[0.9] * 17, bearing_deg=12.0, distance_m=2.1),
        AlertCommand(t=2.0, tag_id="4F2A", level=1, reason="허리 숙임"),
        ZoneStats(period_start=0, period_end=3600, zone="3번 라인", observed_sec=1200, bad_sec_by_reason={"거북목": 90.0}, alerts=2),
    ):
        assert decode(encode(m)) == m


def test_unknown_fields_ignored():
    line = b'{"kind": "alert", "v": 2, "t": 1.0, "tag_id": "A", "level": 1, "reason": "x", "new_field": 5}\n'
    assert decode(line).tag_id == "A"
