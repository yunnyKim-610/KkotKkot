"""core 컨테이너 진입점 (뼈대)

입력: KeypointFrame(vision), UwbMeasurement·PowerEvent(mcu-bridge), RobotState(robot-bridge)
출력: AlertCommand(mcu-bridge), ZoneStats(telemetry)
판정 로직은 module/libs/posture_preprocess 의 temporal·postprocess 를 그대로 쓴다.
"""


def match_person_to_tag(frame, uwb, max_bearing_diff=10.0, max_dist_diff=0.5):
    """카메라가 본 사람과 UWB 태그를 방향·거리 차이로 매칭 (초기 허용값은 현장 시험 후 확정)"""
    if frame.bearing_deg is None or frame.distance_m is None:
        return False
    return (abs(frame.bearing_deg - uwb.bearing_deg) <= max_bearing_diff
            and abs(frame.distance_m - uwb.distance_m) <= max_dist_diff)


def main():
    # TODO: 소켓 서버 열기 → 메시지 수신 → 태그 보유자만 판정 → 알림·통계 전송
    raise NotImplementedError("core 이벤트 루프 구현 예정")


if __name__ == "__main__":
    main()
