"""Tests for HUD-gated scoring: scene cuts (bar appears/vanishes) must not be
scored as HP changes, so they neither get selected nor inflate the threshold.
"""

from PIL import Image

from lemonade_replay_studio.visual import _score_sample_pairs, hud_bar_presence_score, red_bar_coverage


def _bar(path, red_fraction):
    # A wide ROI strip: left `red_fraction` is pure red (HP bar), rest black.
    w, h = 200, 16
    img = Image.new("RGB", (w, h), (0, 0, 0))
    px = img.load()
    for x in range(int(w * red_fraction)):
        for y in range(h):
            px[x, y] = (220, 20, 20)
    img.save(path)
    return path


def test_hud_presence_distinguishes_bar_from_blank(tmp_path):
    full = _bar(tmp_path / "full.png", 0.8)
    blank = _bar(tmp_path / "blank.png", 0.0)
    assert hud_bar_presence_score(full) >= 0.01
    assert hud_bar_presence_score(blank) < 0.01


def test_cut_is_gated_to_zero_but_real_loss_is_scored(tmp_path):
    full = _bar(tmp_path / "s0_full.png", 0.8)
    half = _bar(tmp_path / "s1_half.png", 0.4)
    blank = _bar(tmp_path / "s2_blank.png", 0.0)  # cut to non-HUD footage

    # full -> half (real HP loss, HUD present in both) then half -> blank (cut).
    scored = _score_sample_pairs(
        [full, half, blank], scorer="red_bar_delta", require_hud=True, sample_interval_seconds=2.0
    )
    real_loss = scored[0][0]
    cut = scored[1][0]
    assert real_loss > 0.0  # genuine in-gameplay change keeps its signal
    assert cut == 0.0  # cut to non-HUD footage is gated out


def test_without_require_hud_the_cut_is_not_gated(tmp_path):
    full = _bar(tmp_path / "f.png", 0.8)
    blank = _bar(tmp_path / "b.png", 0.0)
    scored = _score_sample_pairs(
        [full, blank], scorer="red_bar_delta", require_hud=False, sample_interval_seconds=2.0
    )
    # No HUD requirement -> the big coverage delta is scored normally.
    assert scored[0][0] > 0.0
    assert scored[0][0] == abs(red_bar_coverage(blank) - red_bar_coverage(full))
