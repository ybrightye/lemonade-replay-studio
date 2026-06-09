from __future__ import annotations


def fmt_seconds(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_timecode(value: str) -> float:
    text = value.strip()
    if not text:
        raise ValueError("empty timecode")
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return max(0.0, float(parts[0]))
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return max(0.0, minutes * 60 + seconds)
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return max(0.0, hours * 3600 + minutes * 60 + seconds)
    except ValueError as exc:
        raise ValueError(f"invalid timecode: {value}") from exc
    raise ValueError(f"invalid timecode: {value}")


def slug_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m:02d}m{s:02d}s"
