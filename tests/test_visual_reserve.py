from lemonade_replay_studio.analyzer import _reserve_visual_moments, merge_manual_moments, select_spaced_moments
from lemonade_replay_studio.models import Candidate, Moment


def _visual(cand_id, event, score):
    start = event - 12
    return Candidate(start=start, end=start + 24, score=5.0, reason="hp",
                     metadata={"cand_id": cand_id, "source": "visual", "visual_signal": "hp_bar",
                               "visual_event_timestamp": float(event), "visual_score": score})


def test_reserve_picks_top_by_visual_score_and_centers_on_event():
    pool = [_visual(1, 990, 0.17), _visual(2, 1160, 0.09), _visual(3, 700, 0.30)]
    transcripts = ["died and dropped souls", "camel move", "took a hit"]

    reserved = _reserve_visual_moments(pool, pool, transcripts, count=2, clip_seconds=15.0)

    assert len(reserved) == 2
    # highest visual_score first: event 700 (0.30), then 990 (0.17)
    assert [round(m.metadata["visual_event_timestamp"]) for m in reserved] == [700, 990]
    m = reserved[0]
    assert m.metadata["source"] == "visual_reserved"
    assert m.start <= 700 <= m.end  # clip contains the event
    assert abs((m.end - m.start) - 15.0) < 0.01
    assert m.title  # derived from transcript


def test_reserve_count_zero_returns_nothing():
    pool = [_visual(1, 990, 0.17)]
    assert _reserve_visual_moments(pool, pool, ["x"], count=0) == []


def test_visual_min_clips_should_be_capped_by_caller_top_clips():
    pool = [_visual(index, 100 + index * 40, 1.0 / index) for index in range(1, 6)]
    top_clips = 2

    reserved = _reserve_visual_moments(pool, pool, ["x"] * len(pool), count=min(10, top_clips))

    assert len(reserved) == top_clips


def test_reserved_moment_forces_into_reel_over_ranked():
    # one reserved HP moment + ranked transcript moments, top_clips style merge
    reserved = _reserve_visual_moments([_visual(1, 990, 0.3)], [_visual(1, 990, 0.3)], ["died souls"], count=1)
    ranked = [Moment(start=100, end=112, score=9, title="banter1", reason="r", metadata={"cand_id": 9}),
              Moment(start=300, end=312, score=8, title="banter2", reason="r", metadata={"cand_id": 8})]
    # reserve 1 slot, fill 1 with ranked, total top_clips=2
    transcript_selected = select_spaced_moments(ranked, top_clips=1, min_spacing_seconds=10)
    final = merge_manual_moments(transcript_selected, reserved, min_spacing_seconds=10)

    times = sorted(round(m.metadata.get("visual_event_timestamp", m.start)) for m in final)
    assert any(m.metadata.get("source") == "visual_reserved" for m in final)  # HP moment guaranteed in
    assert 990 in [round(m.metadata["visual_event_timestamp"]) for m in final if m.metadata.get("source") == "visual_reserved"]
