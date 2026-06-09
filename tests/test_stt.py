import pytest

from lemonade_replay_studio.models import Candidate
from lemonade_replay_studio.providers import (
    AIProvider,
    _parse_stt_segments,
    _phrase_bounds_from_quote,
)


def test_parse_stt_segments_keeps_valid_and_drops_bad():
    payload = {
        "text": "hello world",
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " hello "},
            {"start": 2.0, "end": 2.0, "text": "zero length"},  # dropped: end <= start
            {"start": "x", "end": 3.0, "text": "bad number"},  # dropped: unparseable
            {"start": 3.0, "end": 4.2, "text": "world"},
        ],
    }

    segments = _parse_stt_segments(payload)

    assert segments == [
        {"start": 0.0, "end": 1.5, "text": "hello"},
        {"start": 3.0, "end": 4.2, "text": "world"},
    ]


def test_parse_stt_segments_absent_returns_empty():
    assert _parse_stt_segments({"text": "no segments here"}) == []


def test_phrase_bounds_uses_real_segment_times_when_present():
    candidate = Candidate(
        start=0,
        end=30,
        score=1,
        reason="context",
        metadata={
            "segments": [
                {"start": 1.0, "end": 3.0, "text": "quiet intro here"},
                {"start": 5.0, "end": 9.0, "text": "you parry him nicely"},
                {"start": 11.0, "end": 14.0, "text": "calm outro talk"},
            ]
        },
    )

    bounds = _phrase_bounds_from_quote(candidate, "ignored fallback transcript", "you parry him")

    # Boundaries come straight from real segment edges (1.0 .. 14.0), not from
    # token-proportional interpolation over the candidate window.
    assert bounds is not None
    start, end = bounds
    assert start == pytest.approx(1.0)
    assert end == pytest.approx(14.0)


def test_transcribe_detailed_default_has_no_segments():
    class DummyProvider(AIProvider):
        name = "dummy"

        def transcribe(self, audio_path):
            return "plain text"

        def rank_moments(self, candidates, transcripts, *, top_k, goal=None):
            return []

    text, segments = DummyProvider().transcribe_detailed("ignored.wav")
    assert text == "plain text"
    assert segments == []
