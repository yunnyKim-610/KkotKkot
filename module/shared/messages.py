"""컨테이너 간 메시지 형식 (유닉스 도메인 소켓, 줄 단위 JSON)

- 모든 메시지에 버전(v)과 종류(kind)를 넣어, 컨테이너를 하나씩 업데이트해도 호환되게 한다.
- 형식을 바꿀 때는 VERSION을 올리고, 받는 쪽은 모르는 필드를 무시한다.
- 영상 프레임은 어떤 메시지에도 넣지 않는다. (vision 컨테이너 밖으로 영상 금지)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

VERSION = 1

# 소켓 경로 (compose에서 /run/kkotkkot 볼륨을 공유)
SOCKET_DIR = "/run/kkotkkot"
SOCK_VISION_TO_CORE = f"{SOCKET_DIR}/vision.sock"
SOCK_MCU_BRIDGE = f"{SOCKET_DIR}/mcu.sock"
SOCK_ROBOT_BRIDGE = f"{SOCKET_DIR}/robot.sock"
SOCK_TELEMETRY = f"{SOCKET_DIR}/telemetry.sock"


@dataclass
class KeypointFrame:
    """vision → core: 프레임별 관절 좌표 (영상 없음)"""
    t: float
    track_id: int
    kpts3d: list[list[float]]          # (17, 3) 미터 단위, 결측은 NaN 대신 None
    conf: list[float]                  # (17,)
    bearing_deg: float | None = None   # 카메라 기준 사람 방향 (UWB 매칭용)
    distance_m: float | None = None
    kind: str = "keypoint_frame"
    v: int = VERSION


@dataclass
class UwbMeasurement:
    """mcu-bridge → core: 태그 방향·거리"""
    t: float
    tag_id: str                        # 익명 태그 번호
    bearing_deg: float
    distance_m: float
    kind: str = "uwb"
    v: int = VERSION


@dataclass
class RobotState:
    """robot-bridge → core: 로봇 정차 여부와 위치"""
    t: float
    stopped: bool
    zone: str | None = None            # 지도상 구역 이름
    kind: str = "robot_state"
    v: int = VERSION


@dataclass
class PowerEvent:
    """mcu-bridge → core/호스트: 전원 이상, 종료 요청"""
    t: float
    event: str                         # "brownout" | "shutdown_request" | "recovered"
    voltage: float | None = None
    kind: str = "power"
    v: int = VERSION


@dataclass
class AlertCommand:
    """core → mcu-bridge: 특정 태그로 진동 알림"""
    t: float
    tag_id: str
    level: int                         # 1 보통, 2 강하게
    reason: str                        # 예: "허리 숙임"
    kind: str = "alert"
    v: int = VERSION


@dataclass
class ZoneStats:
    """core → telemetry: 공정 단위 집계 (개인 데이터 없음)"""
    period_start: float
    period_end: float
    zone: str
    observed_sec: float
    bad_sec_by_reason: dict[str, float] = field(default_factory=dict)
    alerts: int = 0
    kind: str = "zone_stats"
    v: int = VERSION


_TYPES = {cls.__dataclass_fields__["kind"].default: cls
          for cls in (KeypointFrame, UwbMeasurement, RobotState, PowerEvent, AlertCommand, ZoneStats)}


def encode(msg: Any) -> bytes:
    return (json.dumps(asdict(msg), ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes) -> Any:
    data = json.loads(line.decode("utf-8"))
    cls = _TYPES.get(data.get("kind"))
    if cls is None:
        raise ValueError(f"알 수 없는 메시지 종류: {data.get('kind')}")
    known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}  # 모르는 필드 무시
    return cls(**known)
