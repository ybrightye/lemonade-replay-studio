"""Deterministic regression tests for the LLM ranking pipeline.

These mock only the HTTP layer (``_post_first``) with recorded model responses,
so the real parse -> id-repair -> boundary -> score-blend -> selection path is
exercised end to end without a live Lemonade server.
"""

import json

import pytest

from lemonade_replay_studio.interest import blend_scores, load_interest_dictionary
from lemonade_replay_studio.models import Candidate
from lemonade_replay_studio.providers import LemonadeProvider


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _chat_response(moments_payload):
    content = json.dumps({"moments": moments_payload})
    return FakeResponse({"choices": [{"message": {"content": content}}]})


def test_rank_maps_model_choice_to_correct_candidate():
    candidates = [
        Candidate(start=0, end=24, score=1, reason="context"),
        Candidate(start=60, end=84, score=1, reason="context"),
        Candidate(start=120, end=144, score=1, reason="context"),
    ]
    transcripts = [
        "Just walking around the hub area calmly.",
        "Oh no I died right there and everyone started laughing hard.",
        "Reading the menu and checking inventory.",
    ]
    payload = [
        {
            "id": 2,
            "start": 62,
            "end": 74,
            "score": 8,
            "title": "The death",
            "reason": "died and everyone laughed",
            "quote": "I died right there and everyone started laughing",
        }
    ]
    provider = LemonadeProvider(chat_model="test-model")
    provider._post_first = lambda *args, **kwargs: _chat_response(payload)

    moments = provider.rank_moments(candidates, transcripts, top_k=1)

    assert len(moments) == 1
    moment = moments[0]
    assert moment.metadata["candidate_id"] == 2
    assert 60 <= moment.start < moment.end <= 84  # stays inside the chosen candidate
    assert moment.metadata["llm_score"] == 8.0


def test_pure_llm_score_when_no_interest_dict():
    candidates = [Candidate(start=0, end=24, score=1, reason="context")]
    transcripts = ["I totally died there, what a disaster."]
    payload = [{"id": 1, "start": 2, "end": 14, "score": 2, "title": "x", "reason": "y", "quote": "I totally died there"}]
    provider = LemonadeProvider(chat_model="test-model")  # interest_dict defaults to None
    provider._post_first = lambda *args, **kwargs: _chat_response(payload)

    moment = provider.rank_moments(candidates, transcripts, top_k=1)[0]

    assert moment.metadata["keyword_score"] is None
    assert moment.score == pytest.approx(2.0)  # exactly the LLM score, no keyword nudge


def test_low_trust_blend_pulls_score_toward_keyword():
    candidates = [Candidate(start=0, end=24, score=1, reason="context")]
    transcripts = ["I totally died there, what a disaster."]
    payload = [{"id": 1, "start": 2, "end": 14, "score": 2, "title": "x", "reason": "y", "quote": "I totally died there"}]
    provider = LemonadeProvider(
        chat_model="test-model",
        interest_dict=load_interest_dictionary("dark-souls"),
        llm_trust=0.0,
    )
    provider._post_first = lambda *args, **kwargs: _chat_response(payload)

    moment = provider.rank_moments(candidates, transcripts, top_k=1)[0]

    keyword_score = moment.metadata["keyword_score"]
    assert keyword_score is not None
    # llm_trust=0 => final score is the keyword score, ignoring the low LLM score.
    assert moment.score == pytest.approx(blend_scores(2.0, keyword_score, llm_trust=0.0))


def test_large_candidate_set_uses_single_comparable_rerank():
    candidates = [Candidate(start=i * 60, end=i * 60 + 24, score=1, reason="context") for i in range(24)]
    transcripts = [f"moment number {i} where I died and everyone laughed" for i in range(24)]
    calls = []

    def fake_post(paths, *, timeout, json_body=None, **kwargs):
        calls.append(json_body)
        user = json_body["messages"][1]["content"]
        ids = [int(line.split(".")[0]) for line in user.splitlines() if line[:1].isdigit()]
        chosen = ids[:4]
        payload = [
            {"id": cid, "start": 0, "end": 12, "score": 5, "title": "t", "reason": "r", "quote": transcripts[0]}
            for cid in chosen
        ]
        return _chat_response(payload)

    provider = LemonadeProvider(chat_model="test-model")
    provider._post_first = fake_post

    moments = provider.rank_moments(candidates, transcripts, top_k=3)

    # 24 candidates -> 3 shortlist batches of 8 + 1 final comparable re-rank = 4 calls.
    assert len(calls) == 4
    final_user = calls[-1]["messages"][1]["content"]
    final_lines = [line for line in final_user.splitlines() if line[:1].isdigit()]
    assert 0 < len(final_lines) <= provider.SINGLE_CALL_LIMIT
    assert len(moments) <= 3
