from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AnalysisCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {"transcripts": {}}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except json.JSONDecodeError:
                pass

    def transcript_key(self, *, input_path: Path, start: float, end: float, provider: str, model: str | None) -> str:
        return "|".join(
            [
                str(input_path.resolve()),
                f"{start:.3f}",
                f"{end:.3f}",
                provider,
                model or "",
            ]
        )

    def get_transcript(self, key: str) -> str | None:
        value = self.data.setdefault("transcripts", {}).get(key)
        return value if isinstance(value, str) else None

    def set_transcript(self, key: str, transcript: str) -> None:
        self.data.setdefault("transcripts", {})[key] = transcript

    def get_segments(self, key: str) -> list | None:
        value = self.data.setdefault("segments", {}).get(key)
        return value if isinstance(value, list) else None

    def set_segments(self, key: str, segments: list) -> None:
        self.data.setdefault("segments", {})[key] = segments

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
