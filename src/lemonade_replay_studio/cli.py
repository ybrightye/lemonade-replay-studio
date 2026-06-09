from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from .analyzer import analyze_recording
from .demo import create_demo_video
from .doctor import format_doctor, run_doctor
from .interest import load_interest_dictionary
from .model_select import format_model_plan, recommend_models
from .presets import get_preset, preset_choices
from .prompts import DEFAULT_GOAL
from .providers import get_provider
from .watch import watch_folder


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lrs", description="Lemonade Replay Studio")
    sub = parser.add_subparsers(required=True)

    doctor = sub.add_parser("doctor", help="check local dependencies and Lemonade readiness")
    add_provider_args(doctor, include_ranking_args=False)
    doctor.set_defaults(func=cmd_doctor)

    models = sub.add_parser("models", help="recommend and optionally pull Lemonade models for this machine")
    models.add_argument("--base-url", default="http://127.0.0.1:13305")
    models.add_argument("--chat-model")
    models.add_argument("--stt-model")
    models.add_argument("--pull", action="store_true", help="pull recommended models that are not downloaded")
    models.set_defaults(func=cmd_models)

    analyze = sub.add_parser("analyze", help="analyze one recording")
    analyze.add_argument("recording", type=Path)
    analyze.add_argument("--output-dir", type=Path)
    add_analysis_args(analyze)
    analyze.add_argument(
        "--include-range",
        action="append",
        help='force-include a source range, e.g. "10:16-10:28" or "10:16-10:28|Boss panic"; repeat for multiple manual clips',
    )
    add_visual_args(analyze)
    analyze.add_argument("--keep-temp", action="store_true")
    analyze.add_argument(
        "--keep-candidates",
        action="store_true",
        help="write candidates.json: every candidate with the stage it dropped at (dedupe/ranking/spacing) or that it was selected",
    )
    add_provider_args(analyze)
    analyze.set_defaults(func=cmd_analyze)

    demo = sub.add_parser("demo", help="create and analyze a generated demo fixture")
    demo.add_argument("--output-dir", type=Path, default=Path("lrs-demo-output"))
    add_analysis_args(demo, include_candidate_args=False)
    add_visual_args(demo)
    add_provider_args(demo)
    demo.set_defaults(func=cmd_demo)

    watch = sub.add_parser("watch", help="watch a folder and analyze new recordings")
    watch.add_argument("folder", type=Path)
    watch.add_argument("--output-root", type=Path, default=Path("lrs-watch-output"))
    watch.add_argument("--once", action="store_true")
    add_analysis_args(watch, include_candidate_args=False)
    add_provider_args(watch)
    watch.set_defaults(func=cmd_watch)
    return parser


def add_analysis_args(parser: argparse.ArgumentParser, *, include_candidate_args: bool = True) -> None:
    parser.add_argument("--preset", choices=preset_choices(), default="gameplay", help="recommended settings bundle; use 'none' for legacy low-touch defaults")
    parser.add_argument("--goal", help="natural-language instruction for what moments to include")
    if include_candidate_args:
        parser.add_argument("--max-candidates", type=int)
        parser.add_argument("--top-clips", type=int)
        parser.add_argument("--candidate-window-seconds", type=float)
        parser.add_argument("--candidate-mode", choices=["context", "audio", "hybrid"])
        parser.add_argument("--context-stride-seconds", type=float)
        parser.add_argument("--pre-roll-seconds", type=float)
        parser.add_argument("--post-roll-seconds", type=float)
        snap_group = parser.add_mutually_exclusive_group()
        snap_group.add_argument("--snap-to-silence", dest="snap_to_silence", action="store_true", default=None)
        snap_group.add_argument("--no-snap-to-silence", dest="snap_to_silence", action="store_false", default=None)
        parser.add_argument("--speech-boundary-refine", action="store_true", default=None)
        parser.add_argument("--max-snap-seconds", type=float)
        parser.add_argument("--min-clip-spacing-seconds", type=float)
        parser.add_argument("--fade-seconds", type=float)


def add_provider_args(parser: argparse.ArgumentParser, *, include_ranking_args: bool = True) -> None:
    parser.add_argument("--provider", choices=["mock", "lemonade"], default="lemonade")
    parser.add_argument("--base-url", default="http://127.0.0.1:13305")
    parser.add_argument("--chat-model")
    parser.add_argument("--stt-model")
    if not include_ranking_args:
        return
    parser.add_argument(
        "--interest-dict",
        help=(
            "keyword lexicon blended with LLM scores: 'none', "
            "a builtin like 'dark-souls' or 'league', or a path to a .json file"
        ),
    )
    parser.add_argument(
        "--llm-trust",
        type=float,
        help=(
            "0..1 weight favoring the LLM over the interest-dict score when a dict is set "
            "(1.0 = ignore dict, 0.0 = ignore LLM); no effect when --interest-dict is none"
        ),
    )


def add_visual_args(parser: argparse.ArgumentParser) -> None:
    visual_group = parser.add_mutually_exclusive_group()
    visual_group.add_argument("--visual-events", dest="visual_events", action="store_true", default=None, help="add visual ROI-change candidates from the video stream")
    visual_group.add_argument("--no-visual-events", dest="visual_events", action="store_false", default=None, help="disable visual ROI-change candidates from the selected preset")
    parser.add_argument("--visual-roi", help="screen region to track, e.g. top_left, top_right, center, bottom_right")
    parser.add_argument("--visual-signal", action="append", help="named visual signal to track; repeat for multiple signals, e.g. --visual-signal hp_bar")
    parser.add_argument("--visual-sample-interval-seconds", type=float)
    parser.add_argument("--visual-max-candidates", type=int)
    parser.add_argument("--visual-start-seconds", type=float, help="ignore visual changes before this source timestamp")
    parser.add_argument("--visual-require-hud", action="store_true", default=None, help="require visible colored HUD bars in before/after ROI crops")
    parser.add_argument("--visual-min-clips", type=int, help="reserve up to N reel slots for the top visual events (e.g. hp_bar) so they are guaranteed in regardless of LLM ranking")


def cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(provider=args.provider, base_url=args.base_url, chat_model=args.chat_model, stt_model=args.stt_model)
    print(format_doctor(report))
    return 0 if report.ok else 1


def cmd_models(args: argparse.Namespace) -> int:
    plan = recommend_models(base_url=args.base_url, prefer_chat_model=args.chat_model, prefer_stt_model=args.stt_model)
    print(format_model_plan(plan))
    if args.pull:
        import subprocess

        for rec in (plan.chat, plan.stt):
            if rec.model_id and rec.command and not rec.downloaded:
                print(f"\nPulling {rec.model_id}...")
                proc = subprocess.run([_lemonade_cli(), "pull", rec.model_id])
                if proc.returncode != 0:
                    return proc.returncode
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    resolved = resolve_analysis_options(args)
    provider = get_provider(
        args.provider,
        base_url=args.base_url,
        chat_model=args.chat_model,
        stt_model=args.stt_model,
        interest_dict=load_interest_dictionary(resolved["interest_dict"]),
        llm_trust=resolved["llm_trust"],
    )
    output_dir = args.output_dir or Path(f"{args.recording.stem}_lrs")
    result = analyze_recording(
        args.recording,
        output_dir,
        provider,
        max_candidates=resolved["max_candidates"],
        top_clips=resolved["top_clips"],
        candidate_window_seconds=resolved["candidate_window_seconds"],
        candidate_mode=resolved["candidate_mode"],
        context_stride_seconds=resolved["context_stride_seconds"],
        pre_roll_seconds=resolved["pre_roll_seconds"],
        post_roll_seconds=resolved["post_roll_seconds"],
        snap_to_silence=resolved["snap_to_silence"],
        max_snap_seconds=resolved["max_snap_seconds"],
        speech_boundary_refine=resolved["speech_boundary_refine"],
        min_clip_spacing_seconds=resolved["min_clip_spacing_seconds"],
        fade_seconds=resolved["fade_seconds"],
        goal=resolved["goal"],
        visual_events=resolved["visual_events"],
        visual_roi=resolved["visual_roi"],
        visual_signals=resolved["visual_signals"],
        visual_sample_interval_seconds=resolved["visual_sample_interval_seconds"],
        visual_max_candidates=resolved["visual_max_candidates"],
        visual_start_seconds=resolved["visual_start_seconds"],
        visual_require_hud=resolved["visual_require_hud"],
        visual_min_clips=resolved["visual_min_clips"],
        include_ranges=getattr(args, "include_range", None),
        keep_temp=args.keep_temp,
        keep_candidates=getattr(args, "keep_candidates", False),
    )
    print(f"moment map: {result.html_path}")
    print(f"json: {result.json_path}")
    print(f"recap: {result.markdown_path}")
    if result.reel_path:
        print(f"highlight reel: {result.reel_path}")
    return 0


def _lemonade_cli() -> str:
    executable = shutil.which("lemonade")
    if executable:
        return executable
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        bundled = Path(local_app_data) / "lemonade_server" / "bin" / "lemonade.exe"
        if bundled.exists():
            return str(bundled)
    return "lemonade"


def cmd_demo(args: argparse.Namespace) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    recording = create_demo_video(args.output_dir / "demo_recording.mp4")
    args.recording = recording
    args.preset = "none"
    args.max_candidates = 8
    args.top_clips = 3
    args.candidate_window_seconds = 12.0
    args.candidate_mode = "hybrid"
    args.context_stride_seconds = 10.0
    args.pre_roll_seconds = 4.0
    args.post_roll_seconds = 6.0
    args.speech_boundary_refine = False
    args.max_snap_seconds = 8.0
    args.min_clip_spacing_seconds = 10.0
    args.fade_seconds = 1.0
    args.include_range = None
    if not getattr(args, "goal", None):
        args.goal = DEFAULT_GOAL
    args.keep_temp = False
    args.keep_candidates = False
    print(f"created demo recording: {recording}")
    return cmd_analyze(args)


def cmd_watch(args: argparse.Namespace) -> int:
    provider_args = args
    resolved = resolve_analysis_options(args)

    def on_file(path: Path) -> None:
        print(f"detected stable recording: {path}")
        provider = get_provider(
            provider_args.provider,
            base_url=provider_args.base_url,
            chat_model=provider_args.chat_model,
            stt_model=provider_args.stt_model,
            interest_dict=load_interest_dictionary(resolved["interest_dict"]),
            llm_trust=resolved["llm_trust"],
        )
        output_dir = provider_args.output_root / path.stem
        result = analyze_recording(
            path,
            output_dir,
            provider,
            max_candidates=resolved["max_candidates"],
            top_clips=resolved["top_clips"],
            candidate_window_seconds=resolved["candidate_window_seconds"],
            candidate_mode=resolved["candidate_mode"],
            context_stride_seconds=resolved["context_stride_seconds"],
            pre_roll_seconds=resolved["pre_roll_seconds"],
            post_roll_seconds=resolved["post_roll_seconds"],
            snap_to_silence=resolved["snap_to_silence"],
            max_snap_seconds=resolved["max_snap_seconds"],
            speech_boundary_refine=resolved["speech_boundary_refine"],
            min_clip_spacing_seconds=resolved["min_clip_spacing_seconds"],
            fade_seconds=resolved["fade_seconds"],
            goal=resolved["goal"],
            visual_events=resolved["visual_events"],
            visual_roi=resolved["visual_roi"],
            visual_signals=resolved["visual_signals"],
            visual_sample_interval_seconds=resolved["visual_sample_interval_seconds"],
            visual_max_candidates=resolved["visual_max_candidates"],
            visual_start_seconds=resolved["visual_start_seconds"],
            visual_require_hud=resolved["visual_require_hud"],
            visual_min_clips=resolved["visual_min_clips"],
        )
        print(f"finished: {result.html_path}")

    print(f"watching {args.folder} for new recordings...")
    watch_folder(args.folder, on_file=on_file, once=args.once)
    return 0


def resolve_analysis_options(args: argparse.Namespace) -> dict:
    preset = get_preset(getattr(args, "preset", "gameplay"))
    return {
        "goal": _pick(args, "goal", preset.goal),
        "max_candidates": _pick(args, "max_candidates", preset.max_candidates),
        "top_clips": _pick(args, "top_clips", preset.top_clips),
        "candidate_window_seconds": _pick(args, "candidate_window_seconds", preset.candidate_window_seconds),
        "candidate_mode": _pick(args, "candidate_mode", preset.candidate_mode),
        "context_stride_seconds": _pick(args, "context_stride_seconds", preset.context_stride_seconds),
        "pre_roll_seconds": _pick(args, "pre_roll_seconds", preset.pre_roll_seconds),
        "post_roll_seconds": _pick(args, "post_roll_seconds", preset.post_roll_seconds),
        "snap_to_silence": _pick(args, "snap_to_silence", preset.snap_to_silence),
        "max_snap_seconds": _pick(args, "max_snap_seconds", preset.max_snap_seconds),
        "speech_boundary_refine": _pick(args, "speech_boundary_refine", preset.speech_boundary_refine),
        "min_clip_spacing_seconds": _pick(args, "min_clip_spacing_seconds", preset.min_clip_spacing_seconds),
        "fade_seconds": _pick(args, "fade_seconds", preset.fade_seconds),
        "interest_dict": _pick(args, "interest_dict", preset.interest_dict),
        "llm_trust": _pick(args, "llm_trust", preset.llm_trust),
        "visual_events": _pick(args, "visual_events", preset.visual_events),
        "visual_roi": _pick(args, "visual_roi", preset.visual_roi),
        "visual_signals": _pick(args, "visual_signal", preset.visual_signals),
        "visual_sample_interval_seconds": _pick(args, "visual_sample_interval_seconds", preset.visual_sample_interval_seconds),
        "visual_max_candidates": _pick(args, "visual_max_candidates", preset.visual_max_candidates),
        "visual_start_seconds": _pick(args, "visual_start_seconds", preset.visual_start_seconds),
        "visual_require_hud": _pick(args, "visual_require_hud", preset.visual_require_hud),
        "visual_min_clips": _pick(args, "visual_min_clips", preset.visual_min_clips),
    }


def _pick(args: argparse.Namespace, name: str, preset_value):
    value = getattr(args, name, None)
    return preset_value if value is None else value


if __name__ == "__main__":
    raise SystemExit(main())
