"""분석 대상 고르기: 카메라가 본 사람 중 누구를 판정할지 정한다.

- 기본(운영) 모드: UWB 태그와 방향·거리가 맞는 사람만 대상. 나머지는 버린다 (CLAUDE.md 3장 3항).
- 단독 테스트 모드(KKOT_SOLO_TEST=1): 개발자 혼자 태그 없이 시험할 때만 쓴다.
  가장 가까운 1명만 대상으로 하고, 알림은 예약 태그(SOLO_TAG_ID)로 보내 모듈 보드 LED로 표시한다.
  운영 compose에서는 켜지 않는다 (docs/decisions.md #16).
"""
from __future__ import annotations

import math
import os

SOLO_ENV = "KKOT_SOLO_TEST"
SOLO_TAG_ID = "0000"   # shared/mcu_frame.py 의 SOLO_TAG_ID 와 같은 값


def solo_mode_enabled(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get(SOLO_ENV, "").strip() == "1"


def match_person_to_tag(frame, uwb, max_bearing_diff=10.0, max_dist_diff=0.5):
    """카메라가 본 사람과 UWB 태그를 방향·거리 차이로 매칭 (초기 허용값은 현장 시험 후 확정)"""
    if frame.bearing_deg is None or frame.distance_m is None:
        return False
    return (abs(frame.bearing_deg - uwb.bearing_deg) <= max_bearing_diff
            and abs(frame.distance_m - uwb.distance_m) <= max_dist_diff)


def select_targets(frames, uwbs, solo: bool = False):
    """같은 시점의 사람들(frames)과 태그 측정(uwbs)에서 (frame, tag_id) 목록을 돌려준다.

    목록에 없는 사람의 데이터는 호출한 쪽에서 즉시 버린다.
    """
    if solo:
        if not frames:
            return []
        nearest = min(frames, key=lambda f: (math.inf if f.distance_m is None else f.distance_m, f.track_id))
        return [(nearest, SOLO_TAG_ID)]

    targets = []
    used = set()
    for uwb in uwbs:
        cands = [f for f in frames if f.track_id not in used and match_person_to_tag(f, uwb)]
        if len(cands) != 1:
            continue   # 후보가 없거나 둘 이상이면 오전송을 막기 위해 보내지 않는다
        used.add(cands[0].track_id)
        targets.append((cands[0], uwb.tag_id))
    return targets
