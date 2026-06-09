from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile

from .media import extract_wav, which_ffmpeg
from .model_select import format_model_plan, recommend_models
from .models import Candidate
from .providers import LemonadeProvider, _is_chat_model


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(Check(name=name, ok=ok, detail=detail))


def run_doctor(*, provider: str, base_url: str, chat_model: str | None = None, stt_model: str | None = None) -> DoctorReport:
    report = DoctorReport()
    ffmpeg, ffprobe = which_ffmpeg()
    report.add(
        "ffmpeg",
        bool(ffmpeg and ffprobe),
        f"ffmpeg={ffmpeg or 'missing'}, ffprobe={ffprobe or 'missing'}",
    )
    if provider == "mock":
        report.add("provider", True, "mock provider selected; Lemonade checks skipped")
        return report

    lemonade = LemonadeProvider(base_url=base_url, chat_model=chat_model, stt_model=stt_model, timeout=60)
    try:
        health = lemonade.health()
        version = health.get("version", "unknown") if isinstance(health, dict) else "unknown"
        loaded = health.get("model_loaded", "none") if isinstance(health, dict) else "unknown"
        report.add("lemonade health", True, f"version={version}, loaded={loaded}")
    except Exception as exc:
        report.add("lemonade health", False, f"{type(exc).__name__}: {exc}")
        return report

    models: list[dict] = []
    try:
        models = lemonade.models()
        report.add("lemonade models", bool(models), f"{len(models)} model(s) visible")
    except Exception as exc:
        report.add("lemonade models", False, f"{type(exc).__name__}: {exc}")

    llm_visible = _models_matching(models, wanted=("llm", "chat"), explicit=chat_model)
    stt_visible = _models_matching(models, wanted=("transcription", "stt"), explicit=stt_model)
    llm_models = _models_matching(models, wanted=("llm", "chat"), explicit=chat_model, require_downloaded=True)
    stt_models = _models_matching(models, wanted=("transcription", "stt"), explicit=stt_model, require_downloaded=True)
    report.add("chat model", bool(llm_models), _model_detail(llm_models, chat_model, "LLM/chat", visible=llm_visible))
    report.add("stt model", bool(stt_models), _model_detail(stt_models, stt_model, "transcription", visible=stt_visible))
    try:
        plan = recommend_models(base_url=base_url, prefer_chat_model=chat_model, prefer_stt_model=stt_model)
        report.add("recommended models", bool(plan.chat.model_id and plan.stt.model_id), _compact_model_plan(plan))
    except Exception as exc:
        report.add("recommended models", False, f"{type(exc).__name__}: {exc}")

    if llm_models:
        try:
            moments = lemonade.rank_moments(
                [Candidate(start=0.0, end=12.0, score=1.0, reason="doctor structured output test")],
                ["A player barely survives and everyone laughs about the clutch moment."],
                top_k=1,
            )
            report.add("structured LLM test", bool(moments), f"{len(moments)} valid moment(s) returned")
        except Exception as exc:
            report.add("structured LLM test", False, f"{type(exc).__name__}: {exc}")

    if stt_models and ffmpeg:
        try:
            with tempfile.TemporaryDirectory(prefix="lrs-doctor-") as temp_name:
                temp_dir = Path(temp_name)
                tone_path = _create_tiny_audio(temp_dir)
                wav_path = temp_dir / "tiny.wav"
                extract_wav(tone_path, wav_path, 0.0, 1.0)
                transcript = lemonade.transcribe(wav_path)
            report.add("stt endpoint test", isinstance(transcript, str), f"returned {len(transcript)} character(s)")
        except Exception as exc:
            report.add("stt endpoint test", False, f"{type(exc).__name__}: {exc}")
    return report


def format_doctor(report: DoctorReport) -> str:
    lines = ["Lemonade Replay Studio doctor", ""]
    for check in report.checks:
        status = "ok" if check.ok else "fail"
        lines.append(f"[{status}] {check.name}: {check.detail}")
    if not report.ok:
        lines.extend(
            [
                "",
                "If FFmpeg is missing:",
                "- macOS: brew install ffmpeg",
                "- Windows: install with winget/choco/scoop or add ffmpeg.exe and ffprobe.exe to PATH",
                "- Linux: install ffmpeg with your package manager",
            ]
        )
    return "\n".join(lines)


def write_doctor(path: Path, report: DoctorReport) -> Path:
    path.write_text(format_doctor(report), encoding="utf-8")
    return path


def _compact_model_plan(plan) -> str:
    lines = format_model_plan(plan).splitlines()
    return "; ".join(line for line in lines if line and not line.startswith("Lemonade model plan"))


def _models_matching(
    models: list[dict],
    *,
    wanted: tuple[str, ...],
    explicit: str | None,
    require_downloaded: bool = False,
) -> list[str]:
    if explicit:
        return [
            str(model.get("id") or model.get("name"))
            for model in models
            if explicit in {str(model.get("id")), str(model.get("name"))} and (not require_downloaded or bool(model.get("downloaded")))
        ]
    matches = []
    for model in models:
        if require_downloaded and not model.get("downloaded"):
            continue
        labels = {str(label).lower() for label in model.get("labels", [])}
        model_type = str(model.get("type", "")).lower()
        if "llm" in wanted and _is_chat_model(model):
            matches.append(str(model.get("id") or model.get("name")))
        elif any(label in labels or label in model_type for label in wanted):
            matches.append(str(model.get("id") or model.get("name")))
    return matches


def _model_detail(models: list[str], explicit: str | None, kind: str, *, visible: list[str] | None = None) -> str:
    if models:
        shown = ", ".join(models[:3])
        suffix = "" if len(models) <= 3 else f" (+{len(models) - 3} more)"
        return f"{shown}{suffix}"
    if visible:
        return _download_detail(visible, explicit, kind)
    if explicit:
        return f"requested {kind} model not visible: {explicit}"
    return f"no {kind} model detected"


def _download_detail(models: list[str], explicit: str | None, kind: str) -> str:
    if explicit:
        return f"requested {kind} model is visible but not downloaded: {explicit}. Run: lemonade pull {explicit}"
    if kind == "transcription" and "Whisper-Tiny" in models:
        return "transcription models are visible but not downloaded. Run: lemonade pull Whisper-Tiny"
    shown = ", ".join(models[:3])
    return f"{kind} models are visible but not downloaded. Run: lemonade pull {shown}"


def _create_tiny_audio(temp_dir: Path) -> Path:
    import subprocess

    path = temp_dir / "tone.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=1",
        "-f",
        "lavfi",
        "-i",
        "color=black:s=160x90:d=1",
        "-shortest",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "could not create tiny doctor audio")
    return path
