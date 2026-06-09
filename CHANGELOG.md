# Changelog

All notable changes to Lemonade Replay Studio will be documented here.

## Unreleased

### Added

- `--preset gameplay|dark-souls|league|none` for short first-run commands and game-specific tuning bundles.
- `--interest-dict` opt-in keyword lexicon for moment ranking (off by default; builtins `dark-souls` and `league`, or a path to a custom JSON file). A selected dictionary replaces the game-agnostic baseline so franchise vocabulary from one game cannot mis-fire on another.
- `--llm-trust` (0..1) weight controlling how much the local LLM score outweighs the interest-dict score when a dictionary is active.
- `--visual-min-clips N` reserves up to N reel slots for the top visual events (e.g. `hp_bar`), so a detected HP-drop moment is guaranteed in the reel with its before/after evidence instead of losing to funnier banter at LLM ranking. The Dark Souls demo sets it to 2.
- `--keep-candidates` writes `candidates.json`: every candidate with its `source`, `visual_score`, transcript, and the stage it dropped out at (`dedupe` / `ranking` / `spacing`) or that it was selected (`dropped_at: null`). Makes the ranking side as inspectable as the `visual/` artifacts already make the detection side.

### Changed

- Lemonade is now the default provider for CLI commands; use `--provider mock` for dev smoke tests.
- The `hp_bar` visual ROI is tightened to just the red health bar (it previously included the souls icon and the blue/green bars plus background, leaving the HP bar a tiny fraction of the box), and scene cuts to/from non-HUD footage are gated out of change detection so they neither register as HP changes nor inflate the adaptive threshold and suppress real in-gameplay losses.
- Clip boundaries now use real Whisper segment timestamps (requested via STT `verbose_json`) when the server returns them, instead of interpolating phrase times by token count. Falls back to the previous interpolation when no segments are available, so it degrades rather than breaks. Segment timings are cached alongside transcripts; the boundary method is recorded per moment as `stt_segment` vs `phrase_estimate`.
- Large candidate sets (above 16) are now ranked with per-batch shortlisting followed by a single comparable final ranking pass, instead of merging non-comparable per-batch scores.
- Visual ROI scoring (`red_bar_coverage`, `hud_bar_presence_score`) is vectorized with numpy instead of per-pixel Python loops, with equivalence tests pinning the output to the original logic. Adds a `numpy` dependency.
- Moment scores now combine the LLM score and the optional keyword score with an explicit `--llm-trust` weighted blend instead of `max(llm, keyword)`. The blend can move a score in either direction, so the keyword heuristic can no longer silently override the model, and by default (no dictionary) ranking is pure local-LLM judgment.
- Keyword matching now uses word boundaries, so terms like `die` no longer fire inside words such as `studied` and `souls` is no longer matched as a substring of unrelated words.
- The game-agnostic fallback ranker no longer carries Dark Souls-specific vocabulary or labels; franchise terms live in the opt-in dictionaries.

## 0.1.0 - Initial Public Release

### Added

- CLI workflow for analyzing local recordings with `lrs analyze`.
- Manual `--include-range` override for source ranges that must appear in the final reel.
- Lemonade-first AI provider for local STT and local LLM moment ranking.
- `lrs doctor` for checking FFmpeg, Lemonade health, model visibility, structured LLM output, and STT reachability.
- `lrs models` for recommending and optionally pulling Lemonade models.
- `lrs demo` for generating a tiny local fixture.
- `lrs watch` for folder-based automatic processing when new recordings appear.
- FFmpeg media pipeline for WAV extraction, MP4 clip export, timestamp overlays, audio/video fades, and combined highlight reels.
- HTML moment map report with embedded reel, individual clips, quotes, reasons, and download links.
- `moments.json` and `recap.md` exports.
- Natural-language `--goal` support for steering moment selection.
- Optional visual-signal candidates with `--visual-events`, including the initial `hp_bar` signal.
- Before/after visual evidence in the HTML report when selected moments align with visual events.
- Transcription cache for faster reruns.
- Regression tests for provider parsing, prompt versioning, model recommendation, reports, visual signals, cache behavior, and clip selection rules.

### Validated

- macOS local Lemonade path with Lemonade Server 10.6.0, `Qwen3-14B-GGUF`, and `Whisper-Tiny`.
- Windows local Lemonade path with Lemonade Server 10.6.0, `Qwen3-8B-GGUF`, and `Whisper-Tiny`.
- H.264/AAC `yuv420p` highlight reel export for broad playback compatibility.

### Known Limitations

- Current selection is commentary/transcript-first.
- Visual analysis is named ROI/signal detection, not full VLM screen understanding.
- Clip boundaries are approximate, though fades, padding, and spacing rules make outputs easier to watch.
- AMD-specific performance claims still need measurement on AMD hardware.
