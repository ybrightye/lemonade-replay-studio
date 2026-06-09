import pytest

from lemonade_replay_studio.analyzer import merge_manual_moments, parse_manual_ranges, select_spaced_moments
from lemonade_replay_studio.models import Moment


def _moment(start, end, score, title):
    return Moment(start=start, end=end, score=score, title=title, reason="test")


def test_select_spaced_moments_drops_nearby_lower_score():
    moments = [
        _moment(100, 110, 9, "strong"),
        _moment(116, 126, 8, "too close after padding"),
        _moment(200, 210, 7, "far enough"),
    ]

    selected = select_spaced_moments(
        moments,
        top_clips=3,
        min_spacing_seconds=10,
        pre_roll_seconds=1,
        post_roll_seconds=1,
    )

    assert [moment.title for moment in selected] == ["strong", "far enough"]
    assert moments[1].metadata["dropped_reason"] == "within 10s of a stronger moment"


def test_select_spaced_moments_keeps_chronological_output():
    moments = [
        _moment(50, 55, 7, "second"),
        _moment(10, 15, 9, "first"),
    ]

    selected = select_spaced_moments(moments, top_clips=2, min_spacing_seconds=10)

    assert [moment.title for moment in selected] == ["first", "second"]


def test_parse_manual_ranges_supports_optional_title():
    moments = parse_manual_ranges(["10:16-10:28|Boss panic"])

    assert len(moments) == 1
    assert moments[0].start == 616
    assert moments[0].end == 628
    assert moments[0].title == "Boss panic"
    assert moments[0].metadata["source"] == "manual_include"
    assert moments[0].metadata["clip_start_override"] == 616
    assert moments[0].metadata["clip_end_override"] == 628


def test_parse_manual_ranges_rejects_inverted_range():
    with pytest.raises(ValueError):
        parse_manual_ranges(["10:28-10:16"])


def test_merge_manual_moments_keeps_manual_and_drops_nearby_ai():
    ai_moments = [
        _moment(100, 110, 9, "ai too close"),
        _moment(200, 210, 8, "ai far"),
    ]
    manual = parse_manual_ranges(["01:42-01:50|manual"])

    selected = merge_manual_moments(
        ai_moments,
        manual,
        min_spacing_seconds=10,
        pre_roll_seconds=1,
        post_roll_seconds=1,
    )

    assert [moment.title for moment in selected] == ["manual", "ai far"]
    assert ai_moments[0].metadata["dropped_reason"] == "within 10s of a manual include range"
