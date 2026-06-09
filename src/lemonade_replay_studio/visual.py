from __future__ import annotations

from dataclasses import dataclass
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageStat

from .media import MediaError, probe_duration, require_ffmpeg
from .models import Candidate, Moment
from .timefmt import fmt_seconds


ROI_BOXES = {
    "top_left": (0.0, 0.0, 0.36, 0.24),
    "top_right": (0.64, 0.0, 0.36, 0.24),
    "top_center": (0.25, 0.0, 0.50, 0.20),
    "bottom_right": (0.64, 0.64, 0.36, 0.36),
    "bottom_center": (0.20, 0.68, 0.60, 0.32),
    "center": (0.20, 0.20, 0.60, 0.55),
}


@dataclass(frozen=True)
class VisualSignal:
    name: str
    roi: tuple[float, float, float, float]
    scorer: str
    reason: str
    require_hud: bool = False


@dataclass(frozen=True)
class VisualEvent:
    timestamp: float
    score: float
    signal: str
    roi: str
    before_path: Path
    after_path: Path


VISUAL_SIGNALS = {
    **{
        name: VisualSignal(
            name=name,
            roi=box,
            scorer="image_delta",
            reason=f"visual change in {name} region",
        )
        for name, box in ROI_BOXES.items()
    },
    "hp_bar": VisualSignal(
        name="hp_bar",
        # Tightened to just the red HP bar (excludes the souls icon and the
        # blue/green bars), so coverage tracks actual HP, not surrounding HUD.
        roi=(0.10, 0.06, 0.16, 0.035),
        scorer="red_bar_delta",
        reason="red HP bar changed",
        require_hud=True,
    ),
}


def find_visual_candidates(
    input_path: Path,
    output_dir: Path,
    *,
    signal: str | None = None,
    max_candidates: int,
    sample_interval_seconds: float = 2.0,
    window_seconds: float = 24.0,
    min_spacing_seconds: float = 12.0,
    start_seconds: float = 30.0,
    require_hud: bool = False,
) -> list[Candidate]:
    events = detect_visual_events(
        input_path,
        output_dir,
        signal=signal,
        max_events=max_candidates,
        sample_interval_seconds=sample_interval_seconds,
        min_spacing_seconds=min_spacing_seconds,
        start_seconds=start_seconds,
        require_hud=require_hud,
    )
    duration = probe_duration(input_path)
    candidates: list[Candidate] = []
    for event in events:
        start = max(0.0, event.timestamp - window_seconds / 2)
        end = min(duration, start + window_seconds)
        start = max(0.0, end - window_seconds)
        candidates.append(
            Candidate(
                start=start,
                end=end,
                score=_candidate_score(event.score),
                reason=f"{_signal_reason(event.signal)} near {fmt_seconds(event.timestamp)}",
                metadata={
                    "source": "visual",
                    "visual_signal": event.signal,
                    "visual_roi": event.roi,
                    "visual_event_timestamp": event.timestamp,
                    "visual_score": event.score,
                    "visual_before_path": str(event.before_path),
                    "visual_after_path": str(event.after_path),
                },
            )
        )
    return candidates


def detect_visual_events(
    input_path: Path,
    output_dir: Path,
    *,
    signal: str | None = None,
    max_events: int,
    sample_interval_seconds: float = 2.0,
    min_spacing_seconds: float = 12.0,
    start_seconds: float = 30.0,
    require_hud: bool = False,
) -> list[VisualEvent]:
    visual_signal = resolve_visual_signal(signal or "top_left")
    if sample_interval_seconds <= 0:
        raise ValueError("visual sample interval must be greater than 0")
    output_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = output_dir / f"{visual_signal.name}_samples"
    crops_dir.mkdir(parents=True, exist_ok=True)
    for old in crops_dir.glob("*.jpg"):
        old.unlink()

    width, height = probe_video_size(input_path)
    crop = signal_crop_pixels(visual_signal, width, height)
    _extract_roi_sequence(input_path, crops_dir, crop, sample_interval_seconds)
    samples = sorted(crops_dir.glob("sample_*.jpg"))
    if len(samples) < 2:
        return []

    require_hud_active = require_hud or visual_signal.require_hud
    scored = _score_sample_pairs(
        samples,
        scorer=visual_signal.scorer,
        require_hud=require_hud_active,
        sample_interval_seconds=sample_interval_seconds,
    )

    threshold = _adaptive_threshold([score for score, _, _, _ in scored if score > 0.0], scorer=visual_signal.scorer)
    selected: list[tuple[float, float, Path, Path]] = []
    for score, timestamp, before, after in sorted(scored, key=lambda item: (-item[0], item[1])):
        if timestamp < start_seconds or score <= 0.0 or score < threshold:
            continue
        if any(abs(timestamp - existing_ts) < min_spacing_seconds for _, existing_ts, _, _ in selected):
            continue
        selected.append((score, timestamp, before, after))
        if len(selected) >= max_events:
            break

    events_dir = output_dir / f"{visual_signal.name}_events"
    events_dir.mkdir(parents=True, exist_ok=True)
    events: list[VisualEvent] = []
    manifest = []
    for index, (score, timestamp, before, after) in enumerate(sorted(selected, key=lambda item: item[1]), start=1):
        before_out = events_dir / f"{index:02d}_{int(timestamp):05d}_before.jpg"
        after_out = events_dir / f"{index:02d}_{int(timestamp):05d}_after.jpg"
        Image.open(before).save(before_out, quality=88)
        Image.open(after).save(after_out, quality=88)
        events.append(VisualEvent(timestamp=timestamp, score=score, signal=visual_signal.name, roi=visual_signal.name, before_path=before_out, after_path=after_out))
        manifest.append(
            {
                "timestamp": timestamp,
                "score": score,
                "signal": visual_signal.name,
                "roi": visual_signal.name,
                "before_path": str(before_out),
                "after_path": str(after_out),
            }
        )
    (output_dir / "visual_events.json").write_text(json.dumps({"events": manifest}, indent=2), encoding="utf-8")
    return events


def attach_visual_evidence(moments: list[Moment], visual_candidates: list[Candidate], output_dir: Path) -> None:
    grace_seconds = 6.0
    for moment in moments:
        overlaps = [
            candidate
            for candidate in visual_candidates
            if _visual_candidate_distance(moment, candidate) <= grace_seconds
        ]
        if not overlaps:
            continue
        best = max(
            overlaps,
            key=lambda item: (
                -_visual_candidate_distance(moment, item),
                float(item.metadata.get("visual_score", 0.0)),
            ),
        )
        before = Path(str(best.metadata.get("visual_before_path", "")))
        after = Path(str(best.metadata.get("visual_after_path", "")))
        moment.metadata["visual"] = {
            "source": "roi_delta",
            "signal": best.metadata.get("visual_signal"),
            "roi": best.metadata.get("visual_roi"),
            "event_timestamp": best.metadata.get("visual_event_timestamp"),
            "score": best.metadata.get("visual_score"),
            "reason": best.reason,
            "before": _relative_or_string(before, output_dir),
            "after": _relative_or_string(after, output_dir),
        }


def _visual_candidate_distance(moment: Moment, candidate: Candidate) -> float:
    timestamp = float(candidate.metadata.get("visual_event_timestamp", (candidate.start + candidate.end) / 2))
    if moment.start <= timestamp <= moment.end:
        return 0.0
    if timestamp < moment.start:
        return moment.start - timestamp
    return timestamp - moment.end


def _crop_pixels(box: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    x_pct, y_pct, w_pct, h_pct = box
    x = max(0, min(width - 1, int(width * x_pct)))
    y = max(0, min(height - 1, int(height * y_pct)))
    w = max(1, min(width - x, int(width * w_pct)))
    h = max(1, min(height - y, int(height * h_pct)))
    return x, y, w, h


def roi_crop_pixels(roi: str, width: int, height: int) -> tuple[int, int, int, int]:
    if roi not in ROI_BOXES:
        choices = ", ".join(sorted(ROI_BOXES))
        raise ValueError(f"Unknown visual ROI: {roi}. Choose one of: {choices}")
    return _crop_pixels(ROI_BOXES[roi], width, height)


def signal_crop_pixels(signal: VisualSignal, width: int, height: int) -> tuple[int, int, int, int]:
    return _crop_pixels(signal.roi, width, height)


def resolve_visual_signal(name: str) -> VisualSignal:
    try:
        return VISUAL_SIGNALS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(VISUAL_SIGNALS))
        raise ValueError(f"Unknown visual signal: {name}. Choose one of: {choices}") from exc


def _score_sample_pairs(
    samples: list[Path],
    *,
    scorer: str,
    require_hud: bool,
    sample_interval_seconds: float,
) -> list[tuple[float, float, Path, Path]]:
    """Score each consecutive ROI sample pair, gating scene cuts to zero.

    When ``require_hud`` is set, a pair where either frame lacks a visible HUD
    bar is treated as *no change* (score 0): such transitions are cuts to/from
    non-gameplay footage (e.g. reaction shots), and their large deltas would
    otherwise pass selection and inflate the adaptive threshold, drowning out
    the smaller real in-gameplay HP losses.
    """
    hud_cache: dict[Path, bool] = {}

    def _has_hud(path: Path) -> bool:
        if path not in hud_cache:
            hud_cache[path] = hud_bar_presence_score(path) >= 0.01
        return hud_cache[path]

    scored: list[tuple[float, float, Path, Path]] = []
    for index, (before, after) in enumerate(zip(samples, samples[1:]), start=1):
        timestamp = index * sample_interval_seconds
        if require_hud and not (_has_hud(before) and _has_hud(after)):
            score = 0.0
        else:
            score = score_visual_change(before, after, scorer)
        scored.append((score, timestamp, before, after))
    return scored


def score_visual_change(before_path: Path, after_path: Path, scorer: str) -> float:
    if scorer == "image_delta":
        return image_delta_score(before_path, after_path)
    if scorer == "red_bar_delta":
        return red_bar_delta_score(before_path, after_path)
    raise ValueError(f"Unknown visual scorer: {scorer}")


def image_delta_score(before_path: Path, after_path: Path) -> float:
    with Image.open(before_path) as before_image, Image.open(after_path) as after_image:
        before = before_image.convert("L").resize((96, 54))
        after = after_image.convert("L").resize((96, 54))
        diff = ImageChops.difference(before, after)
        stat = ImageStat.Stat(diff)
        return float(stat.mean[0]) / 255.0


def red_bar_delta_score(before_path: Path, after_path: Path) -> float:
    return abs(red_bar_coverage(after_path) - red_bar_coverage(before_path))


def red_bar_coverage(path: Path) -> float:
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((180, 36))
    red, green, blue = _rgb_channels(rgb)
    mask = (red > 85) & (green < 105) & (blue < 105) & (red > green * 1.2)
    return float(mask.mean())


def hud_bar_presence_score(path: Path) -> float:
    with Image.open(path) as image:
        rgb = image.convert("RGB").resize((160, 60))
    red, green, blue = _rgb_channels(rgb)
    is_red_bar = (red > 90) & (green < 95) & (blue < 95) & (red > green * 1.25)
    is_green_bar = (green > 85) & (red < 120) & (blue < 120) & (green > red * 1.15)
    is_blue_or_purple_bar = (blue > 85) & (red > 45) & (green < 110)
    mask = is_red_bar | is_green_bar | is_blue_or_purple_bar
    return float(mask.mean())


def _rgb_channels(image: Image.Image) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    arr = np.asarray(image, dtype=np.float64)
    return arr[..., 0], arr[..., 1], arr[..., 2]


def probe_video_size(path: Path) -> tuple[int, int]:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or f"Could not probe video size for {path}")
    try:
        stream = json.loads(proc.stdout)["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError(f"Could not parse ffprobe video size for {path}") from exc


def _extract_roi_sequence(input_path: Path, output_dir: Path, crop: tuple[int, int, int, int], sample_interval_seconds: float) -> None:
    require_ffmpeg()
    x, y, width, height = crop
    fps = 1.0 / sample_interval_seconds
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"fps={fps:.6f},crop={width}:{height}:{x}:{y},scale=240:-1",
        "-q:v",
        "3",
        str(output_dir / "sample_%05d.jpg"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or "Could not extract visual ROI samples")


def _adaptive_threshold(scores: list[float], *, scorer: str = "image_delta") -> float:
    if not scores:
        return math.inf
    mean = sum(scores) / len(scores)
    variance = sum((score - mean) ** 2 for score in scores) / len(scores)
    if scorer == "red_bar_delta":
        return max(0.025, mean + math.sqrt(variance) * 0.8)
    return max(0.045, mean + math.sqrt(variance) * 1.4)


def _candidate_score(delta_score: float) -> float:
    return max(1.0, min(10.0, 2.0 + delta_score * 10.0))


def _signal_reason(signal: str) -> str:
    return VISUAL_SIGNALS.get(signal, VISUAL_SIGNALS["top_left"]).reason


def _relative_or_string(path: Path, output_dir: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return str(path)
