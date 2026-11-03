"""core 컨테이너 진입점 (뼈대)

입력: KeypointFrame(vision), UwbMeasurement·PowerEvent(mcu-bridge), RobotState(robot-bridge)
출력: AlertCommand(mcu-bridge), ZoneStats(telemetry)
판정 로직은 module/libs/posture_preprocess 의 temporal·postprocess 를 그대로 쓴다.
분석 대상 고르기는 targeting.py (운영: 태그 매칭, 단독 테스트: 가장 가까운 1명).
"""
import logging

from .targeting import SOLO_ENV, select_targets, solo_mode_enabled  # noqa: F401

log = logging.getLogger("core")


def main():
    logging.basicConfig(level=logging.INFO)
    solo = solo_mode_enabled()
    if solo:
        log.warning("%s=1: 단독 테스트 모드. 태그 매칭 없이 가장 가까운 1명만 분석, 알림은 모듈 LED로. "
                    "운영 환경에서 켜지 말 것.", SOLO_ENV)
    # TODO: 소켓 서버 열기 → 메시지 수신 → select_targets(frames, uwbs, solo) → 판정 → 알림·통계 전송
    raise NotImplementedError("core 이벤트 루프 구현 예정")


if __name__ == "__main__":
    main()
