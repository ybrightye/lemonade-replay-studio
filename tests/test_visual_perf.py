"""Equivalence tests pinning the vectorized pixel scorers to the original
per-pixel logic, so the numpy rewrite cannot silently drift the thresholds.
"""

import numpy as np
import pytest
from PIL import Image

from lemonade_replay_studio.visual import hud_bar_presence_score, red_bar_coverage


def _varied_image(tmp_path):
    # Deterministic, varied RGB so all threshold branches get exercised.
    height, width = 48, 200
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            arr[y, x] = ((x * 7) % 256, (y * 13) % 256, (x * y) % 256)
    path = tmp_path / "sample.png"  # PNG is lossless, so pixels survive round-trip
    Image.fromarray(arr).save(path)
    return path


def _ref_red_bar_coverage(path):
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((180, 36))
        pixels = rgb.load()
        width, height = rgb.size
        red_pixels = 0
        for y in range(height):
            for x in range(width):
                red, green, blue = pixels[x, y]
                if red > 85 and green < 105 and blue < 105 and red > green * 1.2:
                    red_pixels += 1
        return red_pixels / (width * height)


def _ref_hud_bar_presence_score(path):
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((160, 60))
        pixels = rgb.load()
        width, height = rgb.size
        colored = 0
        for y in range(height):
            for x in range(width):
                red, green, blue = pixels[x, y]
                is_red_bar = red > 90 and green < 95 and blue < 95 and red > green * 1.25
                is_green_bar = green > 85 and red < 120 and blue < 120 and green > red * 1.15
                is_blue_or_purple_bar = blue > 85 and red > 45 and green < 110
                if is_red_bar or is_green_bar or is_blue_or_purple_bar:
                    colored += 1
        return colored / (width * height)


def test_red_bar_coverage_matches_reference(tmp_path):
    path = _varied_image(tmp_path)
    assert red_bar_coverage(path) == pytest.approx(_ref_red_bar_coverage(path))


def test_hud_bar_presence_matches_reference(tmp_path):
    path = _varied_image(tmp_path)
    assert hud_bar_presence_score(path) == pytest.approx(_ref_hud_bar_presence_score(path))


def test_scores_are_nonzero_on_varied_input(tmp_path):
    # Guard against a degenerate all-false mask making the test vacuous.
    path = _varied_image(tmp_path)
    assert red_bar_coverage(path) > 0.0
    assert hud_bar_presence_score(path) > 0.0
