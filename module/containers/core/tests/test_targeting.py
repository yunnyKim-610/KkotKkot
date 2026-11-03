from types import SimpleNamespace as NS

from src.targeting import SOLO_TAG_ID, select_targets, solo_mode_enabled


def person(track_id, bearing, dist):
    return NS(track_id=track_id, bearing_deg=bearing, distance_m=dist)


def tag(tag_id, bearing, dist):
    return NS(tag_id=tag_id, bearing_deg=bearing, distance_m=dist)


def test_solo_flag_default_off():
    assert solo_mode_enabled({}) is False
    assert solo_mode_enabled({"KKOT_SOLO_TEST": "0"}) is False
    assert solo_mode_enabled({"KKOT_SOLO_TEST": "1"}) is True


def test_normal_mode_drops_untagged_people():
    frames = [person(1, 0.0, 2.0), person(2, 30.0, 3.0)]
    got = select_targets(frames, [tag("4F2A", 1.0, 2.1)])
    assert [(f.track_id, t) for f, t in got] == [(1, "4F2A")]


def test_normal_mode_without_tags_selects_nobody():
    assert select_targets([person(1, 0.0, 2.0)], []) == []


def test_normal_mode_ambiguous_match_not_sent():
    frames = [person(1, 0.0, 2.0), person(2, 2.0, 2.1)]   # 두 사람이 나란히
    assert select_targets(frames, [tag("4F2A", 1.0, 2.05)]) == []


def test_solo_mode_picks_only_nearest_person():
    frames = [person(1, 0.0, 3.0), person(2, 5.0, 1.5), person(3, 9.0, None)]
    got = select_targets(frames, [], solo=True)
    assert [(f.track_id, t) for f, t in got] == [(2, SOLO_TAG_ID)]


def test_solo_mode_no_people():
    assert select_targets([], [], solo=True) == []
