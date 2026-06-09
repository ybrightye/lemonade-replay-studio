# Dark Souls Gameplay Example

This is the public reference example for Lemonade Replay Studio.

It demonstrates the intended workflow:

1. Start Lemonade Server.
2. Run the Dark Souls demo script on a local recording.
3. Open the generated `moment_map.html`.
4. Inspect the combined highlight reel, individual clips, quotes, timestamps, and optional HP-bar visual evidence.

## Source Footage

The development demo uses a local slice of this Wikimedia Commons file:

https://commons.wikimedia.org/wiki/File:TJ_Miller_and_Kumail_Nanjiani_play_Dark_Souls_III_(extended).webm

License shown on Wikimedia Commons:

- Creative Commons Attribution 3.0 Unported
- Author/source attribution: Bandai Namco Entertainment America

The source video and generated MP4 outputs are not committed to the repo. Keep local media under `work/`, `demo-runs/`, or another ignored output directory.

The repo does include a lightweight sample report in `sample-report/`:

- `sample-report/moment_map.html`
- `sample-report/moments.json`
- `sample-report/recap.md`
- `sample-report/visual_events.json`

The sample HTML is the actual generated report. Its video controls reference generated MP4 files that are not committed; rerun the demo locally to produce playable clips and the combined reel.

## Reproduce The Demo

Download or prepare a local recording, then run:

```bash
scripts/run_dark_souls_demo.sh /path/to/dark-souls-recording.mp4 demo-runs/dark-souls-example
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_dark_souls_demo.ps1 -Recording C:\path\to\dark-souls-recording.mp4 -OutputDir demo-runs\dark-souls-example
```

Then open:

```text
demo-runs/dark-souls-example/moment_map.html
```

## Expected Outputs

The run should create:

- `moment_map.html`
- `highlight_reel.mp4`
- `clips/*.mp4`
- `moments.json`
- `recap.md`
- `visual/visual_events.json`
- `visual/hp_bar_events/*_before.jpg`
- `visual/hp_bar_events/*_after.jpg`

## Demo Settings

The demo script uses:

- Lemonade provider
- `Whisper-Tiny` for STT by default
- `Qwen3-8B-GGUF` for chat/ranking by default
- a goal focused on funny deaths, panic, HP drops, insults, and moments friends would want to rewatch
- `--visual-events`
- `--visual-signal hp_bar`
- timestamp overlays, fades, and minimum clip spacing

Override models with:

```bash
LEMONADE_CHAT_MODEL=Qwen3-14B-GGUF \
LEMONADE_STT_MODEL=Whisper-Tiny \
scripts/run_dark_souls_demo.sh /path/to/dark-souls-recording.mp4 demo-runs/dark-souls-example
```

## What To Look For

The example is successful if:

- the report opens in a browser
- the combined reel plays
- individual clips have faint source timestamp ranges
- `moments.json` records `run.provider=lemonade`
- `moments.json` records `run.visual_signals=["hp_bar"]`
- at least one selected moment includes visual event evidence when an HP-bar change aligns with the transcript context
