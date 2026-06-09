from lemonade_replay_studio.analyzer import _build_candidates_report
from lemonade_replay_studio.models import Candidate, Moment


def _cand(cand_id, start, source="transcript", **meta):
    return Candidate(start=start, end=start + 20, score=1.0, reason="ctx",
                     metadata={"cand_id": cand_id, "source": source, **meta})


def _moment(cand_id, start, **meta):
    return Moment(start=start, end=start + 12, score=5.0, title=f"m{cand_id}", reason="r",
                  metadata={"cand_id": cand_id, "llm_score": 8.0, **meta})


def test_report_labels_every_drop_stage():
    pre = [_cand(1, 0), _cand(2, 40), _cand(3, 80), _cand(4, 120),
           _cand(5, 130, source="visual", visual_score=0.3, visual_event_timestamp=140.0)]
    # cand 5 removed at dedupe (not in ranking pool); 1-4 ranked.
    ranking_pool = [pre[0], pre[1], pre[2], pre[3]]
    transcripts = ["a", "b", "c", "d"]
    # LLM ranked 1,2,3 (4 lost in ranking). Of ranked, 1&2 selected; 3 dropped by spacing.
    ranked = [_moment(1, 0), _moment(2, 40),
              _moment(3, 80, dropped_reason="within 10s of a stronger moment")]
    selected = [ranked[0], ranked[1]]

    report = _build_candidates_report(
        pre_dedupe_pool=pre, ranking_pool=ranking_pool, transcripts=transcripts,
        ranked_moments=ranked, selected_moments=selected,
    )

    by_id = {e["cand_id"]: e for e in report["candidates"]}
    assert by_id[1]["dropped_at"] is None and by_id[1]["selected"] is True
    assert by_id[2]["dropped_at"] is None
    assert by_id[3]["dropped_at"] == "spacing"
    assert "stronger moment" in by_id[3]["dropped_reason"]
    assert by_id[4]["dropped_at"] == "ranking"
    assert by_id[5]["dropped_at"] == "dedupe"
    # visual metadata is carried through for inspection
    assert by_id[5]["source"] == "visual" and by_id[5]["visual_score"] == 0.3

    assert report["summary"] == {
        "total": 5, "selected": 2,
        "dropped_dedupe": 1, "dropped_ranking": 1, "dropped_spacing": 1,
    }
