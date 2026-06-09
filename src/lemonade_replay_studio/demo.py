from __future__ import annotations

import subprocess
from pathlib import Path

from .media import require_ffmpeg


def create_demo_video(path: Path) -> Path:
    require_ffmpeg()
    path.parent.mkdir(parents=True, exist_ok=True)
    # A tiny synthetic fixture with three louder moments. This avoids shipping media.
    filter_complex = (
        "sine=frequency=440:duration=8[a0];"
        "sine=frequency=880:duration=3,volume=0.9[a1];"
        "sine=frequency=440:duration=8[a2];"
        "sine=frequency=1040:duration=3,volume=0.9[a3];"
        "sine=frequency=440:duration=8[a4];"
        "sine=frequency=660:duration=3,volume=0.9[a5];"
        "sine=frequency=440:duration=8[a6];"
        "[a0][a1][a2][a3][a4][a5][a6]concat=n=7:v=0:a=1[a]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=1280x720:rate=30:duration=41",
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Could not create demo video")
    return path

