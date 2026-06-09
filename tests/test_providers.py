import pytest

from lemonade_replay_studio.models import Candidate
from lemonade_replay_studio.providers import (
    LemonadeProvider,
    ProviderError,
    _coerce_time,
    _is_chat_model,
    _candidate_id_matching_quote,
    _parse_json_object,
    _phrase_bounds_from_quote,
    _rank_transcript_moments,
)


def test_parse_json_object_extracts_json_from_extra_text():
    parsed = _parse_json_object('prefix {"moments":[{"id":1}]} suffix')

    assert parsed == {"moments": [{"id": 1}]}


def test_parse_json_object_raises_when_missing_json():
    with pytest.raises(ProviderError):
        _parse_json_object("no structured response here")


def test_phrase_bounds_from_quote_picks_matching_sentence():
    candidate = Candidate(start=0, end=30, score=1, reason="test")
    transcript = "quiet setup. You parry him. That was nice. unrelated outro."

    bounds = _phrase_bounds_from_quote(candidate, transcript, "You parry him. That was nice.")

    assert bounds is not None
    start, end = bounds
    assert 0 <= start < end <= 30
    assert end - start <= 24


@pytest.mark.parametrize(
    ("base_url", "normalized"),
    [
        ("http://localhost:13305", "http://localhost:13305"),
        ("http://localhost:13305/", "http://localhost:13305"),
        ("http://localhost:13305/api/v1", "http://localhost:13305"),
        ("http://localhost:13305/api/v1/", "http://localhost:13305"),
        ("http://localhost:13305/v1", "http://localhost:13305"),
    ],
)
def test_lemonade_provider_accepts_versioned_base_urls(base_url, normalized):
    provider = LemonadeProvider(base_url=base_url)

    assert provider.base_url == normalized


def test_current_lemonade_llamacpp_models_are_chat_models():
    assert _is_chat_model({"id": "Qwen3-0.6B-GGUF", "recipe": "llamacpp", "labels": ["llamacpp"]})


def test_lemonade_embedding_models_are_not_chat_models():
    assert not _is_chat_model({"id": "Qwen3-Embedding-0.6B-GGUF", "recipe": "llamacpp", "labels": []})


def test_coerce_time_accepts_range_strings():
    assert _coerce_time("960.0-984.0", default=0) == 960.0
    assert _coerce_time("960.0-984.0", default=0, prefer_end=True) == 984.0
    assert _coerce_time("not a time", default=12.5) == 12.5


def test_transcript_fallback_prefers_reaction_moments():
    candidates = [
        Candidate(start=0, end=24, score=1, reason="context"),
        Candidate(start=30, end=54, score=1, reason="context"),
    ]
    transcripts = [
        "Welcome everyone. We are playing Dark Souls today.",
        "They died and they are hitting me after I die. Oh no. Everyone laughs.",
    ]

    moments = _rank_transcript_moments(candidates, transcripts, top_k=1, provider="lemonade", model="test")

    assert len(moments) == 1
    assert moments[0].start >= 30
    assert "death" in moments[0].reason
    assert moments[0].metadata["rank_fallback"] == "transcript_interest"


def test_candidate_id_matching_quote_repairs_model_id_mismatch():
    candidates = [
        Candidate(start=0, end=24, score=1, reason="intro"),
        Candidate(start=180, end=204, score=1, reason="joke"),
    ]
    transcripts = [
        "Welcome to the video. We are playing Dark Souls.",
        "The reclusive lord of the profane capital says something absurd and everyone laughs.",
    ]

    repaired = _candidate_id_matching_quote(candidates, transcripts, "reclusive lord profane capital laughs", current_id=1)

    assert repaired == 2
