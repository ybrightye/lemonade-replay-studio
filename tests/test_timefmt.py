import pytest

from lemonade_replay_studio.timefmt import fmt_seconds, parse_timecode, slug_time


def test_fmt_seconds_uses_mm_ss_under_one_hour():
    assert fmt_seconds(0) == "00:00"
    assert fmt_seconds(118.5) == "01:58"
    assert fmt_seconds(125.6) == "02:06"


def test_fmt_seconds_uses_hh_mm_ss_over_one_hour():
    assert fmt_seconds(3661) == "01:01:01"


def test_slug_time_is_filename_friendly():
    assert slug_time(615.39) == "10m15s"


def test_parse_timecode_accepts_seconds_minutes_and_hours():
    assert parse_timecode("83") == 83
    assert parse_timecode("01:23") == 83
    assert parse_timecode("1:02:03") == 3723
    assert parse_timecode("10:16.5") == 616.5


def test_parse_timecode_rejects_invalid_text():
    with pytest.raises(ValueError):
        parse_timecode("not-time")
