# Validation

This file records the practical smoke tests used before the initial public release. It is not a benchmark and does not make AMD performance claims.

## macOS Local Demo

Validated on macOS with Lemonade Server running locally.

- Provider: Lemonade
- STT model: `Whisper-Tiny`
- Chat model: `Qwen3-14B-GGUF`
- Input: 20 minute Dark Souls III commentary fixture
- Visual signals: `hp_bar`
- Output: 6 selected moments, individual MP4 clips, combined `highlight_reel.mp4`, `moment_map.html`, `moments.json`, and `recap.md`
- Sample public artifacts: `examples/dark-souls/sample-report/`

The sample report keeps the HTML, JSON, visual-event metadata, and Markdown recap in the repo. Generated MP4 clips are not committed.

## Windows Local Demo

Validated on Windows with Lemonade Server 10.6.0.

- Provider: Lemonade
- STT endpoint: passed
- Structured LLM endpoint: passed
- FFmpeg and FFprobe: found
- STT model: `Whisper-Tiny`
- Chat model: `Qwen3-8B-GGUF`
- Visual signals: `hp_bar`
- Output: `moment_map.html`, `highlight_reel.mp4`, `moments.json`, individual clips, and report media controls
- Combined reel: H.264 video, AAC stereo audio, about 77 seconds

The exact placeholder command shown in docs fails if `C:\path\to\recording.mp4` is not replaced with a real recording. The documented fixture command completed successfully.

## Tests

The Python test suite covers:

- cache behavior
- provider JSON parsing
- model recommendation logic
- moment spacing and selection helpers
- report output
- time formatting
- visual signal helpers

Run locally:

```bash
pip install -e ".[dev]"
pytest
```

On one Windows machine, the default pytest temp directory had a local ACL issue under `%LOCALAPPDATA%\Temp`. Running pytest with a repo-local temp/cache directory passed.

## Known Gaps

- AMD-specific speed and NPU/GPU behavior still need measurement on AMD hardware.
- Clip quality depends on local model size and the user's goal prompt.
- The current visual path uses named ROI change detection. Full vision-language understanding is future work.
