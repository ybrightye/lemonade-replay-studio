from __future__ import annotations

from dataclasses import dataclass, field

from .prompts import DEFAULT_GOAL


@dataclass(frozen=True)
class AnalysisPreset:
    name: str
    goal: str = DEFAULT_GOAL
    max_candidates: int = 32
    top_clips: int = 5
    candidate_window_seconds: float = 24.0
    candidate_mode: str = "context"
    context_stride_seconds: float = 30.0
    pre_roll_seconds: float = 1.5
    post_roll_seconds: float = 2.5
    snap_to_silence: bool = False
    max_snap_seconds: float = 8.0
    speech_boundary_refine: bool = False
    min_clip_spacing_seconds: float = 10.0
    fade_seconds: float = 1.0
    interest_dict: str | None = None
    llm_trust: float = 0.85
    visual_events: bool = False
    visual_roi: str = "top_left"
    visual_signals: list[str] | None = None
    visual_sample_interval_seconds: float = 2.0
    visual_max_candidates: int = 8
    visual_start_seconds: float = 30.0
    visual_require_hud: bool = False
    visual_min_clips: int = 0


PRESETS: dict[str, AnalysisPreset] = {
    "none": AnalysisPreset(
        name="none",
        max_candidates=16,
        top_clips=3,
        candidate_window_seconds=30.0,
        candidate_mode="context",
        context_stride_seconds=45.0,
        pre_roll_seconds=4.0,
        post_roll_seconds=6.0,
        snap_to_silence=True,
        visual_events=False,
    ),
    "gameplay": AnalysisPreset(name="gameplay"),
    "dark-souls": AnalysisPreset(
        name="dark-souls",
        goal="Make a funny Dark Souls replay. Prioritize deaths, panic, HP drops, insults, and moments friends would want to rewatch.",
        max_candidates=40,
        top_clips=6,
        interest_dict="dark-souls",
        llm_trust=0.6,
        visual_events=True,
        visual_signals=["hp_bar"],
        visual_start_seconds=600.0,
        visual_min_clips=2,
    ),
    "league": AnalysisPreset(
        name="league",
        goal="Make a League of Legends replay. Prioritize funny reactions, deaths, clutch fights, objective steals, flashes, ults, throws, and moments friends would want to rewatch.",
        max_candidates=40,
        top_clips=6,
        interest_dict="league",
        llm_trust=0.65,
    ),
}


def get_preset(name: str | None) -> AnalysisPreset:
    key = name or "gameplay"
    try:
        return PRESETS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown preset: {name}. Choose one of: {choices}") from exc


def preset_choices() -> list[str]:
    return sorted(PRESETS)
