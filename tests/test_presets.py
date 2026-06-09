from lemonade_replay_studio.cli import build_parser, resolve_analysis_options


def _parse(argv):
    return build_parser().parse_args(argv)


def test_gameplay_preset_is_default_for_analyze():
    args = _parse(["analyze", "recording.mp4"])

    resolved = resolve_analysis_options(args)

    assert args.provider == "lemonade"
    assert args.preset == "gameplay"
    assert resolved["top_clips"] == 5
    assert resolved["candidate_window_seconds"] == 24.0
    assert resolved["snap_to_silence"] is False
    assert resolved["interest_dict"] is None


def test_dark_souls_preset_enables_visual_and_dictionary():
    args = _parse(["analyze", "recording.mp4", "--preset", "dark-souls"])

    resolved = resolve_analysis_options(args)

    assert resolved["interest_dict"] == "dark-souls"
    assert resolved["llm_trust"] == 0.6
    assert resolved["visual_events"] is True
    assert resolved["visual_signals"] == ["hp_bar"]
    assert resolved["visual_min_clips"] == 2


def test_explicit_flags_override_preset_values():
    args = _parse(
        [
            "analyze",
            "recording.mp4",
            "--preset",
            "dark-souls",
            "--top-clips",
            "2",
            "--interest-dict",
            "none",
            "--no-visual-events",
            "--goal",
            "Find the one good joke.",
        ]
    )

    resolved = resolve_analysis_options(args)

    assert resolved["top_clips"] == 2
    assert resolved["interest_dict"] == "none"
    assert resolved["visual_events"] is False
    assert resolved["goal"] == "Find the one good joke."


def test_watch_accepts_preset_and_uses_same_resolution():
    args = _parse(["watch", "Recordings", "--preset", "league"])

    resolved = resolve_analysis_options(args)

    assert resolved["interest_dict"] == "league"
    assert "League of Legends" in resolved["goal"]
