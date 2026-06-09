from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil

from .cache import AnalysisCache
from .media import export_moments, extract_wav, find_audio_candidates, make_reel, probe_duration
from .models import Candidate, Moment
from .providers import AIProvider
from .prompts import DEFAULT_GOAL
from .report import write_html, write_json, write_markdown
from .speech_bounds import refine_moments_to_spoken_boundaries
from .timefmt import fmt_seconds, parse_timecode
from .visual import attach_visual_evidence, find_visual_candidates


@dataclass
class AnalysisResult:
    output_dir: Path
    html_path: Path
    json_path: Path
    markdown_path: Path
    reel_path: Path | None


def analyze_recording(
    input_path: Path,
    output_dir: Path,
    provider: AIProvider,
    *,
    max_candidates: int = 16,
    top_clips: int = 3,
    candidate_window_seconds: float = 30.0,
    candidate_mode: str = "context",
    context_stride_seconds: float = 45.0,
    pre_roll_seconds: float = 4.0,
    post_roll_seconds: float = 6.0,
    snap_to_silence: bool = True,
    max_snap_seconds: float = 8.0,
    speech_boundary_refine: bool = False,
    min_clip_spacing_seconds: float = 10.0,
    fade_seconds: float = 1.0,
    goal: str = DEFAULT_GOAL,
    visual_events: bool = False,
    visual_roi: str = "top_left",
    visual_signals: list[str] | None = None,
    visual_sample_interval_seconds: float = 2.0,
    visual_max_candidates: int = 8,
    visual_start_seconds: float = 30.0,
    visual_require_hud: bool = False,
    visual_min_clips: int = 0,
    include_ranges: list[str] | None = None,
    keep_temp: bool = False,
    keep_candidates: bool = False,
) -> AnalysisResult:
    input_path = input_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    cache = AnalysisCache(output_dir / "cache" / "analysis_cache.json")

    candidates = find_candidates(
        input_path,
        max_candidates=max_candidates,
        candidate_window_seconds=candidate_window_seconds,
        candidate_mode=candidate_mode,
        context_stride_seconds=context_stride_seconds,
    )
    visual_candidates: list[Candidate] = []
    if visual_events:
        signals = visual_signals or [visual_roi]
        per_signal_max = max(1, visual_max_candidates)
        for signal in signals:
            visual_candidates.extend(
                find_visual_candidates(
                    input_path,
                    output_dir / "visual",
                    signal=signal,
                    max_candidates=per_signal_max,
                    sample_interval_seconds=visual_sample_interval_seconds,
                    window_seconds=candidate_window_seconds,
                    min_spacing_seconds=min_clip_spacing_seconds,
                    start_seconds=visual_start_seconds,
                    require_hud=visual_require_hud,
                )
            )
    # Tag every candidate with a stable id before any dropping, so --keep-candidates
    # can report where each one fell out (dedupe / ranking / spacing / selected).
    pre_dedupe_pool = candidates + visual_candidates
    for cand_id, candidate in enumerate(pre_dedupe_pool, start=1):
        candidate.metadata["cand_id"] = cand_id
    if visual_events:
        candidates = dedupe_candidates(
            pre_dedupe_pool,
            max_candidates=max_candidates + visual_max_candidates * len(signals or []),
        )
    else:
        candidates = pre_dedupe_pool
    if not candidates:
        raise RuntimeError("No candidate moments found.")

    transcripts: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        cache_key = cache.transcript_key(
            input_path=input_path,
            start=candidate.start,
            end=candidate.end,
            provider=provider.name,
            model=getattr(provider, "stt_model", None),
        )
        transcript = cache.get_transcript(cache_key)
        segments = cache.get_segments(cache_key)
        if transcript is None:
            wav_path = temp_dir / f"candidate_{index:02d}.wav"
            extract_wav(input_path, wav_path, candidate.start, candidate.end)
            transcript, segments = provider.transcribe_detailed(wav_path)
            cache.set_transcript(cache_key, transcript)
            cache.set_segments(cache_key, segments)
            cache.save()
        if segments:
            # STT segment times are relative to the extracted clip; shift to
            # absolute source seconds so clip boundaries align with the source.
            candidate.metadata["segments"] = _to_absolute_segments(segments, candidate.start)
        transcripts.append(transcript)

    # Reserved moments are force-included regardless of LLM ranking: manual
    # --include-range entries, plus the top visual events when --visual-min-clips
    # is set (so a detected HP/visual moment is guaranteed in the reel with its
    # before/after evidence instead of losing at ranking to funnier banter).
    visual_reserved_moments = _reserve_visual_moments(
        visual_candidates, candidates, transcripts, count=min(max(0, visual_min_clips), top_clips)
    )
    reserved_moments = parse_manual_ranges(include_ranges or []) + visual_reserved_moments
    ranked_moments = provider.rank_moments(candidates, transcripts, top_k=max(top_clips, top_clips * 2), goal=goal)
    if not ranked_moments and not reserved_moments:
        raise RuntimeError("Provider returned no moments.")

    # Reserve slots within top_clips; fill the rest with the ranked transcript
    # moments. select_spaced_moments tags dropped moments in place, so keep the
    # full ranked list for the candidates report.
    transcript_slots = max(0, top_clips - len(reserved_moments)) if reserved_moments else top_clips
    moments = (
        select_spaced_moments(
            ranked_moments,
            top_clips=transcript_slots,
            min_spacing_seconds=min_clip_spacing_seconds,
            pre_roll_seconds=pre_roll_seconds + fade_seconds,
            post_roll_seconds=post_roll_seconds + fade_seconds,
        )
        if ranked_moments and transcript_slots > 0
        else []
    )
    if reserved_moments:
        moments = merge_manual_moments(
            moments,
            reserved_moments,
            min_spacing_seconds=min_clip_spacing_seconds,
            pre_roll_seconds=pre_roll_seconds + fade_seconds,
            post_roll_seconds=post_roll_seconds + fade_seconds,
        )
    if not moments:
        raise RuntimeError("No moments remained after spacing filter.")

    if visual_candidates:
        attach_visual_evidence(moments, visual_candidates, output_dir)

    if speech_boundary_refine and provider.name != "mock":
        refine_moments_to_spoken_boundaries(
            input_path,
            temp_dir,
            moments,
            provider,
            pre_roll_seconds=pre_roll_seconds,
            post_roll_seconds=post_roll_seconds,
        )

    export_moments(
        input_path,
        output_dir,
        moments,
        pre_roll_seconds=pre_roll_seconds,
        post_roll_seconds=post_roll_seconds,
        snap_to_silence=snap_to_silence,
        max_snap_seconds=max_snap_seconds,
        fade_seconds=fade_seconds,
    )
    reel_path = make_reel(output_dir, moments)
    resolved_chat_model = getattr(provider, "chat_model", None) or next(
        (moment.metadata.get("model") for moment in moments if moment.metadata.get("model")),
        None,
    )
    run_metadata = {
        "input_path": str(input_path),
        "provider": provider.name,
        "stt_model": getattr(provider, "stt_model", None),
        "chat_model": resolved_chat_model,
        "ranking_profile": getattr(provider, "ranking_profile", None),
        "ranking_prompt_version": getattr(provider, "ranking_prompt_version", None),
        "interest_dict": getattr(provider, "interest_dict_name", None),
        "llm_trust": getattr(provider, "llm_trust", None),
        "candidate_mode": candidate_mode,
        "candidate_window_seconds": candidate_window_seconds,
        "context_stride_seconds": context_stride_seconds,
        "max_candidates": max_candidates,
        "top_clips": top_clips,
        "pre_roll_seconds": pre_roll_seconds,
        "post_roll_seconds": post_roll_seconds,
        "snap_to_silence": snap_to_silence,
        "max_snap_seconds": max_snap_seconds,
        "speech_boundary_refine": speech_boundary_refine,
        "min_clip_spacing_seconds": min_clip_spacing_seconds,
        "fade_seconds": fade_seconds,
        "goal": goal,
        "visual_events": visual_events,
        "visual_roi": visual_roi if visual_events and not visual_signals else None,
        "visual_signals": visual_signals if visual_events else None,
        "visual_sample_interval_seconds": visual_sample_interval_seconds if visual_events else None,
        "visual_max_candidates": visual_max_candidates if visual_events else None,
        "visual_start_seconds": visual_start_seconds if visual_events else None,
        "visual_require_hud": visual_require_hud if visual_events else None,
        "visual_min_clips": visual_min_clips,
        "include_ranges": include_ranges or [],
    }
    json_path = write_json(output_dir, moments, run_metadata=run_metadata)
    markdown_path = write_markdown(output_dir, moments)
    html_path = write_html(output_dir, moments, reel_path=reel_path)
    if keep_candidates:
        report = _build_candidates_report(
            pre_dedupe_pool=pre_dedupe_pool,
            ranking_pool=candidates,
            transcripts=transcripts,
            ranked_moments=ranked_moments,
            selected_moments=moments,
        )
        (output_dir / "candidates.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not keep_temp:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return AnalysisResult(
        output_dir=output_dir,
        html_path=html_path,
        json_path=json_path,
        markdown_path=markdown_path,
        reel_path=reel_path,
    )


def _build_candidates_report(
    *,
    pre_dedupe_pool: list[Candidate],
    ranking_pool: list[Candidate],
    transcripts: list[str],
    ranked_moments: list[Moment],
    selected_moments: list[Moment],
) -> dict:
    """Assemble the --keep-candidates report: every candidate, annotated with
    the stage at which it dropped out (dedupe / ranking / spacing) or that it
    was selected (dropped_at = null).
    """
    ranking_ids = {c.metadata.get("cand_id") for c in ranking_pool}
    transcript_by_id = {c.metadata.get("cand_id"): t for c, t in zip(ranking_pool, transcripts)}
    selected_by_id = {m.metadata.get("cand_id"): m for m in selected_moments if m.metadata.get("cand_id") is not None}
    selected_ids = set(selected_by_id)
    ranked_by_id = {m.metadata.get("cand_id"): m for m in ranked_moments if m.metadata.get("cand_id") is not None}

    counts = {"selected": 0, "dropped_dedupe": 0, "dropped_ranking": 0, "dropped_spacing": 0}
    entries: list[dict] = []
    for candidate in pre_dedupe_pool:
        cand_id = candidate.metadata.get("cand_id")
        entry: dict = {
            "cand_id": cand_id,
            "source": candidate.metadata.get("source", "transcript"),
            "start": round(candidate.start, 2),
            "end": round(candidate.end, 2),
            "candidate_score": round(candidate.score, 3),
            "visual_score": candidate.metadata.get("visual_score"),
            "visual_event_timestamp": candidate.metadata.get("visual_event_timestamp"),
            "transcript": _truncate(transcript_by_id.get(cand_id, ""), 200),
        }
        if cand_id not in ranking_ids:
            entry["dropped_at"] = "dedupe"
            entry["dropped_reason"] = "removed as an overlapping duplicate before ranking"
            counts["dropped_dedupe"] += 1
        elif cand_id in selected_ids:
            moment = ranked_by_id.get(cand_id) or selected_by_id.get(cand_id)
            entry["dropped_at"] = None
            entry["selected"] = True
            if moment is not None:
                entry["title"] = moment.title
                entry["llm_score"] = moment.metadata.get("llm_score")
                if moment.metadata.get("source") == "visual_reserved":
                    entry["reserved"] = True
            counts["selected"] += 1
        elif cand_id in ranked_by_id:
            moment = ranked_by_id[cand_id]
            entry["dropped_at"] = "spacing"
            entry["dropped_reason"] = moment.metadata.get("dropped_reason", "dropped during spacing/selection")
            entry["title"] = moment.title
            entry["llm_score"] = moment.metadata.get("llm_score")
            counts["dropped_spacing"] += 1
        else:
            entry["dropped_at"] = "ranking"
            entry["dropped_reason"] = "not chosen by the LLM ranking (lost in the batch shortlist or final re-rank)"
            counts["dropped_ranking"] += 1
        entries.append(entry)

    entries.sort(key=lambda item: (item["cand_id"] is None, item["cand_id"]))
    return {"summary": {"total": len(entries), **counts}, "candidates": entries}


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _reserve_visual_moments(
    visual_candidates: list[Candidate],
    ranking_pool: list[Candidate],
    transcripts: list[str],
    *,
    count: int,
    clip_seconds: float = 15.0,
) -> list[Moment]:
    """Build forced moments from the top `count` visual candidates (by visual
    score), centered on each event so its before/after evidence attaches."""
    if count <= 0 or not visual_candidates:
        return []
    transcript_by_id = {c.metadata.get("cand_id"): t for c, t in zip(ranking_pool, transcripts)}
    ranked = sorted(
        visual_candidates,
        key=lambda c: float(c.metadata.get("visual_score", 0.0) or 0.0),
        reverse=True,
    )[:count]
    moments: list[Moment] = []
    for index, candidate in enumerate(ranked):
        event = float(candidate.metadata.get("visual_event_timestamp", (candidate.start + candidate.end) / 2))
        # Bias the clip before the event (build-up/commentary) with a little after.
        start = max(candidate.start, event - clip_seconds * 0.6)
        end = min(candidate.end, start + clip_seconds)
        if end - start < clip_seconds:
            start = max(candidate.start, end - clip_seconds)
        transcript = (transcript_by_id.get(candidate.metadata.get("cand_id")) or "").strip()
        signal = candidate.metadata.get("visual_signal", "visual")
        moments.append(
            Moment(
                start=start,
                end=end,
                score=998.0 - index / 1000,
                title=_reserve_title(transcript, signal),
                reason=f"Reserved to showcase the {signal} visual signal near {fmt_seconds(event)}.",
                quote=transcript,
                metadata={
                    "source": "visual_reserved",
                    "cand_id": candidate.metadata.get("cand_id"),
                    "visual_signal": signal,
                    "visual_event_timestamp": event,
                    "clip_start_override": start,
                    "clip_end_override": end,
                    "boundary_method": "visual_reserved",
                },
            )
        )
    return moments


def _reserve_title(transcript: str, signal: str) -> str:
    words = transcript.split()
    if words:
        title = " ".join(words[:7]).strip(" -—.,")
        if title:
            return title[:60]
    return f"{signal} moment"


def _to_absolute_segments(segments: list, clip_start: float) -> list[dict]:
    absolute: list[dict] = []
    for seg in segments:
        try:
            start = clip_start + float(seg["start"])
            end = clip_start + float(seg["end"])
        except (KeyError, TypeError, ValueError):
            continue
        absolute.append({"start": start, "end": end, "text": str(seg.get("text", ""))})
    return absolute


def find_candidates(
    input_path: Path,
    *,
    max_candidates: int,
    candidate_window_seconds: float,
    candidate_mode: str,
    context_stride_seconds: float,
) -> list[Candidate]:
    if candidate_mode == "audio":
        return find_audio_candidates(
            input_path,
            max_candidates=max_candidates,
            window_seconds=candidate_window_seconds,
        )
    context_candidates = find_context_candidates(
        input_path,
        max_candidates=max_candidates,
        window_seconds=candidate_window_seconds,
        stride_seconds=context_stride_seconds,
    )
    if candidate_mode == "context":
        return context_candidates
    if candidate_mode == "hybrid":
        audio_candidates = find_audio_candidates(
            input_path,
            max_candidates=max(4, max_candidates // 2),
            window_seconds=candidate_window_seconds,
        )
        return dedupe_candidates(audio_candidates + context_candidates, max_candidates=max_candidates)
    raise ValueError(f"Unknown candidate mode: {candidate_mode}")


def find_context_candidates(
    input_path: Path,
    *,
    max_candidates: int,
    window_seconds: float,
    stride_seconds: float,
) -> list[Candidate]:
    duration = probe_duration(input_path)
    candidates: list[Candidate] = []
    start = 0.0
    index = 0
    while start < duration:
        end = min(duration, start + window_seconds)
        if end - start >= 5:
            candidates.append(
                Candidate(
                    start=start,
                    end=end,
                    score=max(0.1, 1.0 - index * 0.001),
                    reason="transcript context window",
                )
            )
        start += stride_seconds
        index += 1
    return candidates[:max_candidates]


def parse_manual_ranges(specs: list[str]) -> list[Moment]:
    moments: list[Moment] = []
    for index, spec in enumerate(specs, start=1):
        range_text, _, title_text = spec.partition("|")
        delimiter = ".." if ".." in range_text else "-"
        if delimiter not in range_text:
            raise ValueError(f"manual include range must look like START-END: {spec}")
        start_text, end_text = [part.strip() for part in range_text.split(delimiter, 1)]
        start = parse_timecode(start_text)
        end = parse_timecode(end_text)
        if end <= start:
            raise ValueError(f"manual include range end must be after start: {spec}")
        title = title_text.strip() or f"Manual Clip {index}"
        moments.append(
            Moment(
                start=start,
                end=end,
                score=999.0 - index / 1000,
                title=title,
                reason=f"Included by manual source range {fmt_seconds(start)}-{fmt_seconds(end)}.",
                metadata={
                    "source": "manual_include",
                    "manual_range": f"{fmt_seconds(start)}-{fmt_seconds(end)}",
                    "clip_start_override": start,
                    "clip_end_override": end,
                    "boundary_method": "manual_range",
                },
            )
        )
    return moments


def merge_manual_moments(
    ai_moments: list[Moment],
    manual_moments: list[Moment],
    *,
    min_spacing_seconds: float,
    pre_roll_seconds: float = 0.0,
    post_roll_seconds: float = 0.0,
) -> list[Moment]:
    if not manual_moments:
        return sorted(ai_moments, key=lambda item: item.start)
    if min_spacing_seconds <= 0:
        return sorted(manual_moments + ai_moments, key=lambda item: item.start)

    kept_ai: list[Moment] = []
    for ai_moment in ai_moments:
        if _too_close_to_any(
            ai_moment,
            manual_moments,
            min_spacing_seconds=min_spacing_seconds,
            pre_roll_seconds=pre_roll_seconds,
            post_roll_seconds=post_roll_seconds,
        ):
            ai_moment.metadata["dropped_reason"] = f"within {min_spacing_seconds:g}s of a manual include range"
            continue
        kept_ai.append(ai_moment)
    return sorted(manual_moments + kept_ai, key=lambda item: item.start)


def _too_close_to_any(
    moment: Moment,
    others: list[Moment],
    *,
    min_spacing_seconds: float,
    pre_roll_seconds: float,
    post_roll_seconds: float,
) -> bool:
    moment_start = max(0.0, moment.start - pre_roll_seconds)
    moment_end = moment.end + post_roll_seconds
    for existing in others:
        existing_start = max(0.0, existing.start - pre_roll_seconds)
        existing_end = existing.end + post_roll_seconds
        gap = max(existing_start, moment_start) - min(existing_end, moment_end)
        overlap = max(0.0, min(existing_end, moment_end) - max(existing_start, moment_start))
        if overlap > 0 or gap < min_spacing_seconds:
            return True
    return False


def dedupe_candidates(candidates: list[Candidate], *, max_candidates: int) -> list[Candidate]:
    selected: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.start)):
        overlap_too_high = False
        for existing in selected:
            overlap = max(0.0, min(candidate.end, existing.end) - max(candidate.start, existing.start))
            if overlap / max(1.0, min(candidate.duration, existing.duration)) > 0.5:
                overlap_too_high = True
                break
        if not overlap_too_high:
            selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    return sorted(selected, key=lambda item: item.start)


def select_spaced_moments(
    moments: list[Moment],
    *,
    top_clips: int,
    min_spacing_seconds: float,
    pre_roll_seconds: float = 0.0,
    post_roll_seconds: float = 0.0,
) -> list[Moment]:
    if min_spacing_seconds <= 0:
        return sorted(moments[:top_clips], key=lambda item: item.start)

    selected = []
    for moment in sorted(moments, key=lambda item: (-item.score, item.start)):
        too_close = False
        for existing in selected:
            moment_start = max(0.0, moment.start - pre_roll_seconds)
            moment_end = moment.end + post_roll_seconds
            existing_start = max(0.0, existing.start - pre_roll_seconds)
            existing_end = existing.end + post_roll_seconds
            gap = max(existing_start, moment_start) - min(existing_end, moment_end)
            overlap = max(0.0, min(existing_end, moment_end) - max(existing_start, moment_start))
            if overlap > 0 or gap < min_spacing_seconds:
                too_close = True
                break
        if too_close:
            moment.metadata["dropped_reason"] = f"within {min_spacing_seconds:g}s of a stronger moment"
            continue
        selected.append(moment)
        if len(selected) >= top_clips:
            break
    return sorted(selected, key=lambda item: item.start)
