from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    start: float
    end: float
    score: float
    reason: str
    metadata: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Moment:
    start: float
    end: float
    score: float
    title: str
    reason: str
    quote: str = ""
    clip_path: Path | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)
