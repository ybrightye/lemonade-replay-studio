from pathlib import Path

from PIL import Image

from lemonade_replay_studio.analyzer import dedupe_candidates
from lemonade_replay_studio.models import Candidate, Moment
from lemonade_replay_studio.visual import (
    attach_visual_evidence,
    hud_bar_presence_score,
    image_delta_score,
    red_bar_delta_score,
    red_bar_coverage,
    resolve_visual_signal,
    roi_crop_pixels,
)


def test_roi_crop_pixels_stays_inside_frame():
    x, y, width, height = roi_crop_pixels("top_left", 1920, 1080)

    assert x == 0
    assert y == 0
    assert 1 <= width <= 1920
    assert 1 <= height <= 1080


def test_image_delta_score_detects_visual_change(tmp_path):
    before = tmp_path / "before.jpg"
    after = tmp_path / "after.jpg"
    Image.new("RGB", (64, 64), "black").save(before)
    Image.new("RGB", (64, 64), "white").save(after)

    assert image_delta_score(before, after) > 0.9


def test_hud_bar_presence_score_detects_colored_bars(tmp_path):
    plain = tmp_path / "plain.jpg"
    hud = tmp_path / "hud.jpg"
    Image.new("RGB", (160, 60), "black").save(plain)
    image = Image.new("RGB", (160, 60), "black")
    for x in range(20, 140):
        for y in range(12, 18):
            image.putpixel((x, y), (160, 30, 30))
        for y in range(22, 28):
            image.putpixel((x, y), (40, 140, 50))
    image.save(hud)

    assert hud_bar_presence_score(hud) > hud_bar_presence_score(plain)


def test_hp_bar_signal_uses_red_bar_scorer():
    signal = resolve_visual_signal("hp_bar")

    assert signal.scorer == "red_bar_delta"
    assert signal.require_hud
    assert signal.roi[2] < 0.36


def test_red_bar_delta_score_detects_health_change(tmp_path):
    full = tmp_path / "full.jpg"
    low = tmp_path / "low.jpg"
    full_image = Image.new("RGB", (180, 36), "black")
    low_image = Image.new("RGB", (180, 36), "black")
    for x in range(10, 170):
        for y in range(10, 18):
            full_image.putpixel((x, y), (155, 25, 25))
    for x in range(10, 80):
        for y in range(10, 18):
            low_image.putpixel((x, y), (155, 25, 25))
    full_image.save(full)
    low_image.save(low)

    assert red_bar_coverage(full) > red_bar_coverage(low)
    assert red_bar_delta_score(full, low) > 0.01


def test_visual_candidates_are_additive_in_dedupe():
    transcript = Candidate(start=0, end=24, score=1.0, reason="transcript context window")
    visual = Candidate(
        start=100,
        end=124,
        score=0.2,
        reason="visual HUD change",
        metadata={"source": "visual"},
    )

    selected = dedupe_candidates([transcript, visual], max_candidates=2)

    assert selected == [transcript, visual]


def test_visual_evidence_attaches_near_clip_boundary(tmp_path):
    before = tmp_path / "before.jpg"
    after = tmp_path / "after.jpg"
    before.write_text("before", encoding="utf-8")
    after.write_text("after", encoding="utf-8")
    moments = [
        Moment(
            start=969.7,
            end=987.5,
            score=10,
            title="Friend Dies",
            reason="funny panic",
        )
    ]
    visual_candidates = [
        Candidate(
            start=978,
            end=1002,
            score=1,
            reason="red HP bar changed near 16:30",
            metadata={
                "source": "visual",
                "visual_signal": "hp_bar",
                "visual_roi": "hp_bar",
                "visual_event_timestamp": 990.0,
                "visual_score": 0.05,
                "visual_before_path": str(before),
                "visual_after_path": str(after),
            },
        )
    ]

    attach_visual_evidence(moments, visual_candidates, tmp_path)

    assert moments[0].metadata["visual"]["signal"] == "hp_bar"
    assert moments[0].metadata["visual"]["event_timestamp"] == 990.0
