# Contributing

Thanks for checking out Lemonade Replay Studio. The project is early and very open to practical feedback from people with real recordings.

## Useful Feedback

The most helpful issue reports include:

- operating system
- CPU/GPU/RAM
- Lemonade version
- chat model and STT model
- command you ran
- whether `lrs doctor` passed
- what the output got right
- what important moments it missed

If you can share `moments.json`, that is often enough to debug selection behavior without sharing the source video.

## Development Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

If Windows blocks the default pytest temp directory, set a repo-local temp/cache directory before running tests:

```powershell
New-Item -ItemType Directory -Force -Path .\.tmp | Out-Null
$env:TMP=(Resolve-Path .\.tmp)
$env:TEMP=(Resolve-Path .\.tmp)
.\.venv\Scripts\python.exe -m pytest -q
```

## Adding A Visual Signal

Named visual signals live in `src/lemonade_replay_studio/visual.py`.

A good first contribution is a new signal preset:

1. Pick a game UI element, such as HP, kill feed, KDA, minimap, or damage numbers.
2. Add a `VisualSignal` entry with a normalized screen region.
3. Choose or add a scorer.
4. Add a small test in `tests/test_visual.py`.
5. Run a real recording and check `visual/visual_events.json`.

Signals should be conservative. It is better to add a few useful candidates than flood the LLM with noisy visual changes.

## Pull Request Checklist

- Keep the default path local and Lemonade-first.
- Do not commit generated media in `demo-runs/`.
- Run `pytest`.
- Update README or roadmap docs for user-facing behavior.
- Avoid claims about AMD performance unless measured on AMD hardware.
