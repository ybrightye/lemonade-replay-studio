from __future__ import annotations

import re
from pathlib import Path

from .media import extract_wav, probe_duration
from .models import Moment
from .providers import AIProvider


def refine_moments_to_spoken_boundaries(
    input_path: Path,
    temp_dir: Path,
    moments: list[Moment],
    provider: AIProvider,
    *,
    pre_roll_seconds: float,
    post_roll_seconds: float,
    search_margin_seconds: float = 5.0,
    chunk_seconds: float = 1.5,
    max_clip_seconds: float = 18.0,
) -> None:
    duration = probe_duration(input_path)
    for index, moment in enumerate(moments, start=1):
        refined = refine_moment_to_spoken_boundaries(
            input_path,
            temp_dir,
            moment,
            provider,
            duration=duration,
            index=index,
            pre_roll_seconds=pre_roll_seconds,
            post_roll_seconds=post_roll_seconds,
            search_margin_seconds=search_margin_seconds,
            chunk_seconds=chunk_seconds,
            max_clip_seconds=max_clip_seconds,
        )
        if refined:
            start, end, method = refined
            moment.metadata["clip_start_override"] = start
            moment.metadata["clip_end_override"] = end
            moment.metadata["boundary_method"] = method


def refine_moment_to_spoken_boundaries(
    input_path: Path,
    temp_dir: Path,
    moment: Moment,
    provider: AIProvider,
    *,
    duration: float,
    index: int,
    pre_roll_seconds: float,
    post_roll_seconds: float,
    search_margin_seconds: float,
    chunk_seconds: float,
    max_clip_seconds: float,
) -> tuple[float, float, str] | None:
    selected_start = moment.start
    selected_end = moment.end
    padded_start = max(0.0, selected_start - pre_roll_seconds)
    padded_end = min(duration, selected_end + post_roll_seconds)
    search_start = max(0.0, selected_start - max(pre_roll_seconds, search_margin_seconds))
    search_end = min(duration, selected_end + max(post_roll_seconds, search_margin_seconds))

    chunks = []
    cursor = search_start
    chunk_index = 0
    while cursor < search_end - 0.25:
        chunk_start = cursor
        chunk_end = min(search_end, cursor + chunk_seconds)
        wav_path = temp_dir / f"boundary_{index:02d}_{chunk_index:03d}.wav"
        extract_wav(input_path, wav_path, chunk_start, chunk_end)
        transcript = provider.transcribe(wav_path)
        chunks.append(
            {
                "start": chunk_start,
                "end": chunk_end,
                "transcript": transcript,
                "has_speech": _has_speech(transcript),
            }
        )
        cursor += chunk_seconds
        chunk_index += 1

    if not chunks:
        return None

    anchor_indices = [
        chunk_index
        for chunk_index, chunk in enumerate(chunks)
        if chunk["has_speech"] and chunk["end"] >= selected_start and chunk["start"] <= selected_end
    ]
    if not anchor_indices:
        return None

    start_index = min(anchor_indices)
    end_index = max(anchor_indices)
    while start_index > 0 and chunks[start_index - 1]["has_speech"]:
        start_index -= 1
    while end_index + 1 < len(chunks) and chunks[end_index + 1]["has_speech"]:
        end_index += 1

    refined_start = float(chunks[start_index]["start"])
    refined_end = float(chunks[end_index]["end"])

    refined_start = min(refined_start, padded_start)
    refined_end = max(refined_end, padded_end)

    if refined_end - refined_start > max_clip_seconds:
        center = (selected_start + selected_end) / 2
        refined_start = max(search_start, center - max_clip_seconds / 2)
        refined_end = min(search_end, refined_start + max_clip_seconds)
        refined_start = max(search_start, refined_end - max_clip_seconds)

    if refined_end - refined_start < 4.0:
        return None
    return refined_start, refined_end, "spoken_boundary"


def _has_speech(transcript: str) -> bool:
    tokens = re.findall(r"[a-z0-9']+", transcript.lower())
    if len(tokens) < 2:
        return False
    joined = " ".join(tokens)
    hallucinated_fillers = {
        "thank you",
        "thanks for watching",
        "bye bye",
        "music",
    }
    return joined not in hallucinated_fillers
