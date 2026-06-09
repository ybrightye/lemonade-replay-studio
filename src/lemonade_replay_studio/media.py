from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import Candidate, Moment
from .timefmt import fmt_seconds, slug_time


class MediaError(RuntimeError):
    pass


def which_ffmpeg() -> tuple[str | None, str | None]:
    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def require_ffmpeg() -> None:
    ffmpeg, ffprobe = which_ffmpeg()
    if not ffmpeg or not ffprobe:
        raise MediaError(
            "FFmpeg and FFprobe must be installed and discoverable on PATH. "
            "macOS: brew install ffmpeg. Windows: install via winget/choco/scoop or add ffmpeg.exe to PATH. "
            "Linux: install via your package manager."
        )


def probe_duration(path: Path) -> float:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or f"Could not probe {path}")
    try:
        data = json.loads(proc.stdout)
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError(f"Could not parse ffprobe duration for {path}") from exc


def probe_has_audio(path: Path) -> bool:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or f"Could not probe audio streams for {path}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"Could not parse ffprobe audio streams for {path}") from exc
    return bool(data.get("streams"))


def extract_wav(input_path: Path, output_path: Path, start: float, end: float) -> Path:
    require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or f"Could not extract audio from {input_path}")
    return output_path


def _chunk_loudness(input_path: Path, start: float, duration: float) -> float:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(input_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stderr
    max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    if not max_match or not mean_match:
        return 0.0
    max_vol = float(max_match.group(1))
    mean_vol = float(mean_match.group(1))
    if max_vol <= -45:
        return 0.0
    loudness = (max_vol + 45) / 45
    dynamics = min(2.0, abs(mean_vol - max_vol) / max(1.0, abs(mean_vol)))
    return max(0.0, loudness * (1.0 + dynamics))


def find_silence_boundaries(
    input_path: Path,
    *,
    start: float,
    end: float,
    noise_db: float = -35.0,
    min_silence_seconds: float = 0.35,
) -> list[float]:
    require_ffmpeg()
    duration = max(0.1, end - start)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(input_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence_seconds}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stderr
    boundaries: list[float] = []
    for match in re.finditer(r"silence_(?:start|end):\s*([0-9.]+)", text):
        boundaries.append(start + float(match.group(1)))
    return sorted(boundaries)


def snap_clip_bounds(
    input_path: Path,
    *,
    selected_start: float,
    selected_end: float,
    duration: float,
    pre_roll_seconds: float,
    post_roll_seconds: float,
    max_snap_seconds: float = 8.0,
    noise_db: float = -35.0,
    min_silence_seconds: float = 0.35,
) -> tuple[float, float, str]:
    padded_start = max(0.0, selected_start - pre_roll_seconds)
    padded_end = min(duration, selected_end + post_roll_seconds)
    search_start = max(0.0, selected_start - max(pre_roll_seconds, max_snap_seconds))
    search_end = min(duration, selected_end + max(post_roll_seconds, max_snap_seconds))
    boundaries = find_silence_boundaries(
        input_path,
        start=search_start,
        end=search_end,
        noise_db=noise_db,
        min_silence_seconds=min_silence_seconds,
    )

    start_options = [point for point in boundaries if search_start <= point <= selected_start]
    end_options = [point for point in boundaries if selected_end <= point <= search_end]
    snapped_start = max(start_options) if start_options else padded_start
    snapped_end = min(end_options) if end_options else padded_end

    min_duration = max(8.0, selected_end - selected_start)
    if snapped_end - snapped_start < min_duration:
        snapped_start, snapped_end = padded_start, padded_end
        method = "padding"
    elif start_options or end_options:
        method = "silence"
    else:
        method = "padding"

    return max(0.0, snapped_start), min(duration, snapped_end), method


def find_audio_candidates(
    input_path: Path,
    *,
    max_candidates: int = 24,
    chunk_seconds: float = 10.0,
    window_seconds: float = 30.0,
) -> list[Candidate]:
    duration = probe_duration(input_path)
    chunks: list[Candidate] = []
    steps = max(1, math.ceil(duration / chunk_seconds))
    for index in range(steps):
        chunk_start = index * chunk_seconds
        chunk_end = min(duration, chunk_start + chunk_seconds)
        if chunk_end - chunk_start < 1:
            continue
        score = _chunk_loudness(input_path, chunk_start, chunk_end - chunk_start)
        if score <= 0:
            continue
        center = (chunk_start + chunk_end) / 2
        start = max(0.0, center - window_seconds / 2)
        end = min(duration, start + window_seconds)
        start = max(0.0, end - window_seconds)
        chunks.append(Candidate(start=start, end=end, score=score, reason="audio energy spike"))
    chunks.sort(key=lambda item: item.score, reverse=True)
    return _dedupe_candidates(chunks[: max_candidates * 2], max_candidates=max_candidates)


def _dedupe_candidates(candidates: list[Candidate], *, max_candidates: int) -> list[Candidate]:
    selected: list[Candidate] = []
    for candidate in candidates:
        overlaps = False
        for existing in selected:
            overlap = max(0.0, min(candidate.end, existing.end) - max(candidate.start, existing.start))
            if overlap / max(1.0, min(candidate.duration, existing.duration)) > 0.5:
                overlaps = True
                break
        if not overlaps:
            selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    return sorted(selected, key=lambda item: item.start)


def cut_clip(
    input_path: Path,
    output_path: Path,
    start: float,
    end: float,
    *,
    overlay_text: str | None = None,
    fade_seconds: float = 1.0,
) -> Path:
    require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    overlay_path = _make_timestamp_overlay(output_path.with_suffix(".timestamp.png"), overlay_text) if overlay_text else None
    fade = min(max(0.0, fade_seconds), max(0.0, duration / 3))
    has_audio = probe_has_audio(input_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(input_path),
    ]
    filter_parts = []
    video_label = "0:v"
    output_video_label = "v"
    video_filters = []
    if fade > 0:
        video_filters.extend([f"fade=t=in:st=0:d={fade:.3f}", f"fade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}"])
    if video_filters:
        filter_parts.append(f"[{video_label}]{','.join(video_filters)}[vfade]")
        video_label = "vfade"
    if overlay_path:
        cmd.extend(["-loop", "1", "-i", str(overlay_path)])
        filter_parts.append(f"[{video_label}][1:v]overlay=W-w-18:H-h-14:format=auto[{output_video_label}]")
    elif video_filters:
        output_video_label = video_label

    output_audio_label = None
    if has_audio and fade > 0:
        output_audio_label = "a"
        filter_parts.append(
            f"[0:a]afade=t=in:st=0:d={fade:.3f}:curve=exp,"
            f"afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}:curve=exp[{output_audio_label}]"
        )

    if filter_parts:
        cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", f"[{output_video_label}]"])
        if output_audio_label:
            cmd.extend(["-map", f"[{output_audio_label}]"])
        elif has_audio:
            cmd.extend(["-map", "0:a?"])
        cmd.append("-shortest")
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or f"Could not cut clip {output_path}")
    return output_path


def export_moments(
    input_path: Path,
    output_dir: Path,
    moments: list[Moment],
    *,
    pre_roll_seconds: float = 4.0,
    post_roll_seconds: float = 6.0,
    snap_to_silence: bool = True,
    max_snap_seconds: float = 8.0,
    silence_noise_db: float = -35.0,
    min_silence_seconds: float = 0.35,
    fade_seconds: float = 1.0,
) -> list[Moment]:
    clips_dir = output_dir / "clips"
    duration = probe_duration(input_path)
    for index, moment in enumerate(moments, start=1):
        if "clip_start_override" in moment.metadata and "clip_end_override" in moment.metadata:
            clip_start = max(0.0, float(moment.metadata["clip_start_override"]))
            clip_end = min(duration, float(moment.metadata["clip_end_override"]))
            boundary_method = str(moment.metadata.get("boundary_method", "override"))
        elif snap_to_silence:
            clip_start, clip_end, boundary_method = snap_clip_bounds(
                input_path,
                selected_start=moment.start,
                selected_end=moment.end,
                duration=duration,
                pre_roll_seconds=pre_roll_seconds,
                post_roll_seconds=post_roll_seconds,
                max_snap_seconds=max_snap_seconds,
                noise_db=silence_noise_db,
                min_silence_seconds=min_silence_seconds,
            )
        else:
            clip_start = max(0.0, moment.start - pre_roll_seconds)
            clip_end = min(duration, moment.end + post_roll_seconds)
            boundary_method = "padding"
        fade_pad_seconds = min(max(0.0, fade_seconds), max(0.0, (clip_end - clip_start) / 3))
        clip_start = max(0.0, clip_start - fade_pad_seconds)
        clip_end = min(duration, clip_end + fade_pad_seconds)
        moment.metadata["selected_start"] = moment.start
        moment.metadata["selected_end"] = moment.end
        moment.metadata["pre_roll_seconds"] = pre_roll_seconds
        moment.metadata["post_roll_seconds"] = post_roll_seconds
        moment.metadata["fade_pad_seconds"] = fade_pad_seconds
        moment.metadata["boundary_method"] = boundary_method
        moment.start = clip_start
        moment.end = clip_end
        filename = f"{index:02d}_{slug_time(moment.start)}.mp4"
        overlay_text = f"source {fmt_seconds(moment.start)}-{fmt_seconds(moment.end)}"
        moment.metadata["overlay_text"] = overlay_text
        moment.metadata["fade_seconds"] = fade_seconds
        moment.clip_path = cut_clip(
            input_path,
            clips_dir / filename,
            moment.start,
            moment.end,
            overlay_text=overlay_text,
            fade_seconds=fade_seconds,
        )
    return moments


def _make_timestamp_overlay(output_path: Path, text: str | None) -> Path | None:
    if not text:
        return None

    font = _load_timestamp_font(18)
    padding_x = 10
    padding_y = 6
    temp_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_image)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + padding_x * 2
    height = bbox[3] - bbox[1] + padding_y * 2

    image = Image.new("RGBA", (width, height), (0, 0, 0, 52))
    draw = ImageDraw.Draw(image)
    draw.text((padding_x, padding_y - bbox[1]), text, font=font, fill=(255, 255, 255, 115))
    image.save(output_path)
    return output_path


def _load_timestamp_font(size: int) -> ImageFont.ImageFont:
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_reel(output_dir: Path, moments: list[Moment]) -> Path | None:
    require_ffmpeg()
    clip_paths = [moment.clip_path for moment in moments if moment.clip_path]
    if not clip_paths:
        return None
    list_file = output_dir / "clips" / "reel_inputs.txt"
    with list_file.open("w", encoding="utf-8") as handle:
        for clip_path in clip_paths:
            handle.write(f"file '{clip_path.resolve()}'\n")
    reel_path = output_dir / "highlight_reel.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(reel_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or "Could not create combined highlight reel")
    return reel_path
