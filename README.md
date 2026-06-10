# Lemonade Replay Studio

Turn long gameplay recordings into local AI highlight reels and moment maps, powered by [Lemonade](https://github.com/lemonade-sdk/lemonade/tree/main).

Lemonade Replay Studio analyzes a local recording, finds replay-worthy moments from commentary, exports short clips, builds a combined highlight reel, and writes a timestamped HTML moment map. The default AI path is local Lemonade STT plus local Lemonade LLM reasoning. FFmpeg handles deterministic media operations like probing, audio extraction, fades, overlays, and MP4 cutting.

**Watch the demo:** [Lemonade Replay Studio on YouTube](https://youtu.be/dDbVivzlOs0)

The current demo is gameplay-focused: give it a recording, a goal like "find funny deaths, panic, HP drops, and insults," and it produces a shareable replay report without cloud APIs or SaaS uploads.

## Why Local AI For Replays

Gameplay recordings are a great fit for local AI because the raw data is already on the user's machine and it is huge. A single long OBS recording can be gigabytes. Uploading that to a cloud clipping service is slow, costs bandwidth, and often turns a quick "what happened in this session?" question into a SaaS workflow.

Replay Studio keeps the bulky media local. The app only extracts short candidate audio windows, screen-region samples, and compact transcripts before asking Lemonade to rank the moments. That makes local AI useful for the part humans actually need help with: finding the funny, surprising, or important moments hidden inside a long recording.

Local processing also protects creator trust. Raw footage, transcripts, goal prompts, HUD samples, and rough cuts can include private conversations, unreleased content, or competitive tricks. With the intended Lemonade path, those stay on the user's machine unless they choose to share the final report or clips.

This is especially natural for PC gamers and creators. They often already have the recording, the GPU, the RAM, and the reason to review hours of footage. Replay Studio turns that existing local machine into a replay scout instead of requiring another cloud upload pipeline.

The local path also makes the workflow feel automatic: watch mode can monitor a recordings folder and start analysis once a new file stops changing. A session ends, the replay scout starts working, and the user gets a report plus highlight reel without uploading the full video anywhere.

## Why Lemonade

Lemonade is a good fit because Replay Studio is a PC-local AI workload, not just a generic chat wrapper.

- **AMD PC fit:** Lemonade targets the kind of local Windows/PC hardware many gamers already own or upgrade toward. Replay analysis benefits from that: the media is local, the workload is bursty, and stronger local models can improve judgment without changing the app.
- **Local STT + LLM in one workflow:** Lemonade transcribes candidate audio windows and then ranks, titles, quotes, and explains the best moments with a local chat model.
- **Multimodal input today:** Replay Studio does not only listen to audio. With `--visual-events`, it samples named game HUD regions such as `hp_bar`, detects visual-change spikes, merges those with transcript candidates, and lets Lemonade rank the final moment list with both transcript and visual evidence.
- **Multimodal roadmap tomorrow:** Future Lemonade vision models can help identify game type, HUD layout, KDA/kill-feed/minimap regions, and other visual signals from representative frames.
- **Runtime checks:** `lrs doctor` checks Lemonade health, visible models, STT reachability, and structured-output behavior so setup problems are easier to diagnose.

No cloud API key, upload, or SaaS subscription is required for the intended path.

Replay Studio also demonstrates a practical PC-local scaling story: a modest Windows machine with an 8 GB GPU can complete the end-to-end Lemonade STT plus LLM workflow, while systems with more memory can use larger local models for better clip judgment without changing the app.

## Current Status

- End-to-end local Lemonade workflow validated on macOS and Windows.
- Outputs HTML reports, individual MP4 clips, a combined highlight reel, JSON, and a Markdown recap.
- Optional visual-signal path can track game HUD signals such as `hp_bar` and attach before/after evidence to selected moments.
- Looking for feedback from gamers, streamers, local-AI builders, and anyone with long recordings.

## How It Works

Replay Studio is a local media pipeline with Lemonade as the AI runtime:

1. **Find candidates cheaply.** The app scans the recording into context windows and can also add local audio-energy candidates. With `--visual-events`, it samples named screen regions such as `hp_bar` and turns meaningful HUD changes into extra candidates.
2. **Transcribe locally.** Candidate audio windows are extracted with FFmpeg and sent to Lemonade STT, usually `Whisper-Tiny` for the demo path. When the STT response includes segment timestamps, those real spoken-segment times are used to place clip boundaries; otherwise the app falls back to estimating phrase times. Transcripts and segment timings are cached so reruns do not repeat STT work.
3. **Rank with a local LLM.** Replay Studio sends compact candidate summaries, transcripts, visual metadata, and the user's `--goal` to a Lemonade chat model. The model returns structured JSON with titles, scores, reasons, quotes, and suggested clip ranges.
4. **Repair and filter.** The app validates local LLM output, falls back when JSON is malformed, repairs quote/candidate mismatches, and applies minimum spacing so adjacent moments do not crowd the reel.
5. **Export media.** FFmpeg cuts clips, adds faint source timestamp overlays, applies audio/video fades, encodes H.264/AAC `yuv420p` MP4s, and concatenates the final highlight reel.
6. **Write artifacts.** The run produces `moment_map.html`, `moments.json`, `recap.md`, individual clips, and optional before/after visual evidence images.

The boundary is intentional: Lemonade handles local AI work; FFmpeg handles deterministic media operations. This keeps the workflow portable while still demonstrating a real local STT + LLM + multimodal-input application.

## Feedback Wanted

If you try Replay Studio, the most useful feedback is:

- Did the chosen clips feel replay-worthy?
- Which moments did it miss?
- Which game/UI signals should be added next, such as kill feed, KDA, minimap, quest log, chat, or damage numbers?
- Did setup work on your machine?
- Which model and hardware did you use?

## Quick Start

Replay Studio needs Python 3.10+, FFmpeg/FFprobe, and Lemonade Server for the local AI workflow. Use the setup block for your OS first, then run the common Lemonade checks below.

### macOS / Linux

```bash
# macOS
brew install ffmpeg

# Linux: use your distro package manager, for example:
# sudo apt install ffmpeg

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
lrs doctor --provider mock
```

### Windows PowerShell

```powershell
winget install --id Gyan.FFmpeg --source winget

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m lemonade_replay_studio.cli doctor --provider mock
```

If you install FFmpeg another way, make sure both `ffmpeg` and `ffprobe` are on `PATH`.

## Lemonade Setup

Start Lemonade Server and make sure a chat model plus an STT model are available. Replay Studio defaults to `Qwen3-8B-GGUF` and `Whisper-Tiny` for the demo scripts.

### Windows Lemonade

```powershell
winget install --id AMD.LemonadeServer --source winget --accept-package-agreements --accept-source-agreements
Start-Process -FilePath "$env:LOCALAPPDATA\lemonade_server\bin\LemonadeServer.exe" -WindowStyle Hidden
& "$env:LOCALAPPDATA\lemonade_server\bin\lemonade.exe" status
.\.venv\Scripts\python.exe -m lemonade_replay_studio.cli models --base-url http://127.0.0.1:13305/api/v1 --pull
```

If `lemonade pull Whisper-Tiny` fails with `CURL error: SSL connect error`, download the model into Lemonade's Hugging Face cache and rerun the pull:

```powershell
$snapshot="$env:USERPROFILE\.cache\huggingface\hub\models--ggerganov--whisper.cpp\snapshots\5359861c739e955e79d9a303bcbc70fb988958b1"
New-Item -ItemType Directory -Force -Path $snapshot | Out-Null
curl.exe --tlsv1.2 -L --fail -o "$snapshot\ggml-tiny.bin" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin?download=true"
& "$env:LOCALAPPDATA\lemonade_server\bin\lemonade.exe" pull Whisper-Tiny
```

### macOS / Linux Lemonade

Install and start Lemonade Server using the current Lemonade instructions for your platform, then run:

```bash
lrs models --base-url http://127.0.0.1:13305/api/v1 --pull
```

## Run With Lemonade

Health check:

```bash
lrs doctor \
  --provider lemonade \
  --base-url http://127.0.0.1:13305 \
  --chat-model Qwen3-8B-GGUF \
  --stt-model Whisper-Tiny
```

Analyze a recording:

```bash
lrs analyze path/to/recording.mp4 \
  --preset gameplay \
  --goal "Find funny gameplay highlights"
```

Replay Studio defaults to `--preset gameplay`, so the shortest form is:

```bash
lrs analyze path/to/recording.mp4
```

Add `--chat-model` and `--stt-model` when you want to pin exact models, for example in a reproducible demo.

If you already know a specific moment must be included, add a manual range:

```bash
lrs analyze path/to/recording.mp4 \
  --preset gameplay \
  --include-range "10:16-10:28|Boss panic"
```

Game-specific presets bundle the tuning flags used by the demo. For example, `dark-souls` enables the `hp_bar` visual signal, Dark Souls interest dictionary, tighter clip padding, and two reserved visual moments:

```bash
lrs analyze path/to/recording.mp4 \
  --preset dark-souls
```

Outputs:

- `moment_map.html`: watch the combined reel and individual clips
- `highlight_reel.mp4`: one-shot reel for demos/sharing
- `clips/*.mp4`: individual faded clips with burned-in source timestamp ranges
- `moments.json`: reproducible structured artifact with run settings, model, ranking profile, and prompt version
- `recap.md`: paste-ready Markdown summary for Discord, Slack, GitHub, or notes
- `cache/analysis_cache.json`: cached transcriptions for faster reruns
- `visual/`: optional ROI samples, before/after visual-event crops, and `visual_events.json` when `--visual-events` is enabled

## Watch Mode

Watch mode is the intended "it just starts working" demo path:

```bash
lrs watch ~/Recordings \
  --preset gameplay
```

When a new recording appears and stops changing, Replay Studio analyzes it into `lrs-watch-output/<recording-name>/`.

## Tuning Notes

- Compare demo runs only when the commit, model, `moments.json` run settings, `ranking_profile`, and `ranking_prompt_version` match. Prompt changes are product changes, not neutral test variation.
- `--preset gameplay` is the recommended default. `--preset dark-souls` adds the Dark Souls dictionary plus `hp_bar` visual events. `--preset league` adds a League-focused dictionary without visual HUD detection yet. `--preset none` uses the older low-touch defaults.
- `--goal` lets the user steer the replay. For example: `--goal "Find funny friend reactions, deaths, HP drops, and insults."`
- `--interest-dict` adds an optional keyword lexicon to nudge ranking toward game-specific moments. It is **off by default** (`none`), so a fresh run is pure local-LLM judgment. Pass a builtin (`--interest-dict dark-souls`, `--interest-dict league`) or a path to your own JSON (`--interest-dict ./my-game.json`). A dictionary file is a list of weighted word `groups`, each with a `label` used in the recap reason. See `src/lemonade_replay_studio/dictionaries/` for examples. A selected dictionary *replaces* the built-in baseline, so franchise words from one game never leak into another.
- `--llm-trust` (0..1, default `0.85`) sets how much the local LLM's own score outweighs the `--interest-dict` score when a dictionary is active. `1.0` ignores the dictionary entirely; `0.0` ignores the LLM. Lower it when running a small/weak local model whose raw judgment you trust less; raise it for a strong model. It has no effect when `--interest-dict` is `none`.
- `--include-range START-END` is the manual override when you already know a moment must appear in the reel. Use `mm:ss`, `hh:mm:ss`, or raw seconds. Add an optional title after a pipe, for example: `--include-range "10:16-10:28|Boss panic"`. Repeat it for multiple guaranteed clips.
- Local model size affects curation taste. On an 8 GB GPU, `Qwen3-8B-GGUF` can run the full Lemonade workflow and find real reaction/comedy moments, but it may make weaker judgment calls than larger models. That is an expected local-AI trade-off: the app remains usable on modest PCs, while higher-memory machines can run stronger local models for better moment selection.
- `--visual-events` is an experimental multimodal-input path. It does not require a vision-language model: Replay Studio samples named visual signals, detects visual-change spikes, turns them into candidates, then lets Lemonade rank them with transcript context.
- `--visual-signal hp_bar` is useful for Dark Souls-like red health bars. Generic visual signals also include `top_left`, `top_right`, `top_center`, `bottom_right`, `bottom_center`, and `center`. Repeat `--visual-signal` to track multiple signals.
- `--visual-start-seconds` can skip intro/cutscene sections before the relevant game UI appears. Future Lemonade vision setup can turn a natural-language request like "use my HP bar and KDA" into approved visual signal boxes.
- `--min-clip-spacing-seconds 10` prevents adjacent moments from crowding the reel.
- `--fade-seconds 1` is the default. Replay Studio adds matching fade padding, so fades do not consume the selected clip content.
- `--speech-boundary-refine` is experimental. It uses extra Lemonade STT calls to look for spoken boundaries, but it can make clips too long when commentary is continuous.
- Reruns reuse cached candidate transcripts when the input path, provider, STT model, and candidate window are unchanged.

## Demo Fixture

The current development demo uses a Creative Commons licensed Dark Souls III commentary video from Wikimedia Commons. See `examples/dark-souls/` for the reproducible example and `DEMO_FOOTAGE.md` for attribution notes.

For implementation details and smoke-test notes, see `docs/architecture.md` and `docs/validation.md`.

## Example Workflow

The fastest full demo path is the Dark Souls example:

```bash
scripts/run_dark_souls_demo.sh /path/to/recording.mp4 demo-runs/dark-souls-example
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_dark_souls_demo.ps1 -Recording C:\path\to\recording.mp4 -OutputDir demo-runs\dark-souls-example
```

Then open `demo-runs/dark-souls-example/moment_map.html`. See `examples/dark-souls/` for source-footage attribution, expected outputs, and model overrides.

The repo also includes lightweight sample artifacts under `examples/dark-souls/sample-report/`. These are committed for inspection, but the generated HTML report is best viewed after running the demo locally because GitHub shows the HTML source instead of opening it as an interactive report.

## Development Checks

Install test dependencies:

```bash
pip install -e ".[dev]"
pytest
```

Fast local smoke test without Lemonade:

```bash
lrs doctor --provider mock
lrs demo --provider mock --output-dir /tmp/lrs-mock-demo
```

Replay Studio defaults to the Lemonade provider for real runs. Use `--provider mock` only for offline development smoke tests.

## Source Layout

- `src/lemonade_replay_studio/`: CLI, media pipeline, Lemonade provider, reports, watch mode
- `tests/`: small regression tests for cache, spacing, JSON parsing, reports, and time formatting
- `scripts/run_dark_souls_demo.sh`: reproducible Lemonade demo command
- `examples/dark-souls/`: public example workflow and expected outputs
- `docs/architecture.md`: pipeline and extension notes
- `docs/validation.md`: macOS and Windows smoke-test notes
- `DEMO_FOOTAGE.md`: demo fixture attribution notes
- `CONTRIBUTING.md`: contribution guide and extension ideas
- `ROADMAP.md`: community roadmap
- `CHANGELOG.md`: release notes

Generated media should live in `demo-runs/` or another output directory and is ignored by default.

## License

Mozilla Public License 2.0. See `LICENSE`.

## Known Limitations

- Current selection is commentary/transcript-first, with optional named visual-signal candidates such as `hp_bar`. Rich VLM-based screen understanding is future work.
- The app is file-based, not real-time stream capture.
- Clip boundaries align to real STT segment timestamps when the STT server returns them, and fall back to interpolated phrase times otherwise. Fades and padding make cuts easier to watch, but this is not a full editing timeline.
- `--speech-boundary-refine` is experimental and may over-expand clips when people talk continuously.
- AMD-specific performance claims should be measured on AMD hardware before making hardware-speed claims.
