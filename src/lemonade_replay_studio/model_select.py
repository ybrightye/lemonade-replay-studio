from __future__ import annotations

from dataclasses import dataclass
import re
import shutil
import subprocess
from typing import Any

from .providers import LemonadeProvider, _is_chat_model


PREFERRED_CHAT_MODELS = [
    "Qwen3-8B-GGUF",
    "Qwen3-4B-GGUF",
    "Qwen3-1.7B-GGUF",
    "Qwen3-0.6B-GGUF",
]
PREFERRED_STT_MODELS = ["Whisper-Tiny", "Whisper-Base", "Whisper-Small"]


@dataclass
class HardwareInfo:
    gpu_name: str | None = None
    gpu_memory_total_mb: int | None = None
    gpu_memory_free_mb: int | None = None
    system_memory_total_mb: int | None = None
    system_memory_free_mb: int | None = None


@dataclass
class ModelRecommendation:
    model_id: str | None
    downloaded: bool
    detail: str
    command: str | None = None


@dataclass
class ModelPlan:
    hardware: HardwareInfo
    chat: ModelRecommendation
    stt: ModelRecommendation


def recommend_models(*, base_url: str, prefer_chat_model: str | None = None, prefer_stt_model: str | None = None) -> ModelPlan:
    lemonade = LemonadeProvider(base_url=base_url)
    models = lemonade.models()
    try:
        health = lemonade.health()
        loaded_model = _loaded_chat_model(health) if isinstance(health, dict) else ""
    except Exception:
        loaded_model = ""
    hardware = detect_hardware()
    return ModelPlan(
        hardware=hardware,
        chat=_recommend_chat(models, hardware, prefer_chat_model, loaded_model=loaded_model),
        stt=_recommend_stt(models, prefer_stt_model),
    )


def format_model_plan(plan: ModelPlan) -> str:
    lines = ["Lemonade model plan", ""]
    hw = plan.hardware
    if hw.gpu_name:
        total = f"{hw.gpu_memory_total_mb} MiB" if hw.gpu_memory_total_mb is not None else "unknown"
        free = f"{hw.gpu_memory_free_mb} MiB" if hw.gpu_memory_free_mb is not None else "unknown"
        lines.append(f"GPU: {hw.gpu_name}, total={total}, free={free}")
    else:
        lines.append("GPU: not detected")
    if hw.system_memory_total_mb is not None:
        lines.append(f"System RAM: total={hw.system_memory_total_mb} MiB, free={hw.system_memory_free_mb or 'unknown'} MiB")
    lines.extend(
        [
            "",
            f"Chat: {_format_rec(plan.chat)}",
            f"STT: {_format_rec(plan.stt)}",
        ]
    )
    return "\n".join(lines)


def detect_hardware() -> HardwareInfo:
    hardware = HardwareInfo()
    _detect_nvidia_smi(hardware)
    _detect_windows_memory(hardware)
    return hardware


def _recommend_chat(
    models: list[dict[str, Any]],
    hardware: HardwareInfo,
    explicit: str | None,
    *,
    loaded_model: str = "",
) -> ModelRecommendation:
    chat_models = [model for model in models if _is_chat_model(model)]
    if explicit:
        model = _find_model(chat_models, explicit)
        if not model:
            return ModelRecommendation(None, False, f"requested chat model not visible: {explicit}")
        return _chat_recommendation_for_model(model, hardware, explicit=True, loaded_model=loaded_model)

    downloaded = [_chat_recommendation_for_model(model, hardware, loaded_model=loaded_model) for model in _ordered_models(chat_models) if model.get("downloaded")]
    for rec in downloaded:
        if _is_fit_detail(rec.detail):
            return rec

    for model in _ordered_models(chat_models):
        rec = _chat_recommendation_for_model(model, hardware, loaded_model=loaded_model)
        if _is_fit_detail(rec.detail):
            return rec

    if chat_models:
        model = _ordered_models(chat_models)[0]
        return _chat_recommendation_for_model(model, hardware, loaded_model=loaded_model)
    return ModelRecommendation(None, False, "no Lemonade chat model detected")


def _recommend_stt(models: list[dict[str, Any]], explicit: str | None) -> ModelRecommendation:
    stt_models = [model for model in models if _is_stt_model(model)]
    if explicit:
        model = _find_model(stt_models, explicit)
        if not model:
            return ModelRecommendation(None, False, f"requested transcription model not visible: {explicit}")
        return _stt_recommendation_for_model(model)
    for model_id in PREFERRED_STT_MODELS:
        model = _find_model(stt_models, model_id)
        if model:
            return _stt_recommendation_for_model(model)
    if stt_models:
        return _stt_recommendation_for_model(stt_models[0])
    return ModelRecommendation(None, False, "no Lemonade transcription model detected")


def _chat_recommendation_for_model(
    model: dict[str, Any],
    hardware: HardwareInfo,
    *,
    explicit: bool = False,
    loaded_model: str = "",
) -> ModelRecommendation:
    model_id = str(model.get("id") or model.get("name"))
    downloaded = bool(model.get("downloaded"))
    size_mb = _model_size_mb(model)
    command = None if downloaded else f"lemonade pull {model_id}"
    if model_id == loaded_model:
        return ModelRecommendation(model_id, downloaded, "currently loaded in Lemonade", command=command)
    fit, detail = _fits_hardware(model_id, size_mb, hardware)
    prefix = "requested " if explicit else ""
    if not fit and explicit:
        detail = f"{prefix}{detail}"
    return ModelRecommendation(model_id, downloaded, detail, command=command)


def _stt_recommendation_for_model(model: dict[str, Any]) -> ModelRecommendation:
    model_id = str(model.get("id") or model.get("name"))
    downloaded = bool(model.get("downloaded"))
    command = None if downloaded else f"lemonade pull {model_id}"
    detail = "downloaded" if downloaded else "visible but not downloaded"
    return ModelRecommendation(model_id, downloaded, detail, command=command)


def _fits_hardware(model_id: str, size_mb: int | None, hardware: HardwareInfo) -> tuple[bool, str]:
    if size_mb is None:
        return True, "visible; size unknown"
    required_mb = size_mb + _headroom_mb(size_mb)
    if hardware.gpu_memory_total_mb:
        total = hardware.gpu_memory_total_mb
        if hardware.gpu_memory_free_mb is not None and required_mb > hardware.gpu_memory_free_mb:
            return False, (
                f"{model_id} may not fit currently free GPU VRAM: model={size_mb} MiB, "
                f"free={hardware.gpu_memory_free_mb} MiB, needs about {required_mb} MiB"
            )
        if required_mb <= total:
            headroom = total - size_mb
            return True, f"fits GPU VRAM: model={size_mb} MiB, total={total} MiB, estimated headroom={headroom} MiB"
        return False, f"{model_id} may not fit GPU VRAM: model={size_mb} MiB, total={total} MiB, needs about {required_mb} MiB"
    if hardware.system_memory_total_mb:
        required_ram = size_mb + 4096
        if required_ram <= hardware.system_memory_total_mb:
            return True, f"fits system RAM with CPU fallback: model={size_mb} MiB, total RAM={hardware.system_memory_total_mb} MiB"
        return False, f"{model_id} may not fit system RAM: model={size_mb} MiB, total RAM={hardware.system_memory_total_mb} MiB"
    return True, f"visible; no hardware memory data available"


def _headroom_mb(size_mb: int) -> int:
    if size_mb >= 5000:
        return 1500
    if size_mb >= 2000:
        return 1200
    return 800


def _model_size_mb(model: dict[str, Any]) -> int | None:
    size = model.get("size")
    if isinstance(size, (int, float)):
        return int(float(size) * 1024)
    return None


def _ordered_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(model.get("id") or model.get("name")): model for model in models}
    ordered = [by_id[model_id] for model_id in PREFERRED_CHAT_MODELS if model_id in by_id]
    preferred = {str(model.get("id") or model.get("name")) for model in ordered}
    remaining = [model for model in models if str(model.get("id") or model.get("name")) not in preferred]
    remaining.sort(key=lambda model: float(model.get("size") or 0), reverse=True)
    return ordered + remaining


def _find_model(models: list[dict[str, Any]], model_id: str) -> dict[str, Any] | None:
    for model in models:
        if model_id in {str(model.get("id")), str(model.get("name"))}:
            return model
    return None


def _is_stt_model(model: dict[str, Any]) -> bool:
    labels = {str(label).lower() for label in model.get("labels", [])}
    recipe = str(model.get("recipe", "")).lower()
    model_type = str(model.get("type", "")).lower()
    return recipe == "whispercpp" or "transcription" in labels or "stt" in labels or "transcription" in model_type


def _is_fit_detail(detail: str) -> bool:
    return not any(phrase in detail for phrase in ("may not fit", "not visible"))


def _format_rec(rec: ModelRecommendation) -> str:
    if not rec.model_id:
        return rec.detail
    state = "downloaded" if rec.downloaded else "not downloaded"
    suffix = f"; run `{rec.command}`" if rec.command else ""
    return f"{rec.model_id} ({state}) - {rec.detail}{suffix}"


def _detect_nvidia_smi(hardware: HardwareInfo) -> None:
    if not shutil.which("nvidia-smi"):
        return
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return
    first = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    parts = [part.strip() for part in first.split(",")]
    if len(parts) < 3:
        return
    hardware.gpu_name = parts[0]
    hardware.gpu_memory_total_mb = _parse_int(parts[1])
    hardware.gpu_memory_free_mb = _parse_int(parts[2])


def _detect_windows_memory(hardware: HardwareInfo) -> None:
    if not shutil.which("powershell"):
        return
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return
    total_match = re.search(r'"TotalVisibleMemorySize"\s*:\s*(\d+)', proc.stdout)
    free_match = re.search(r'"FreePhysicalMemory"\s*:\s*(\d+)', proc.stdout)
    if total_match:
        hardware.system_memory_total_mb = int(total_match.group(1)) // 1024
    if free_match:
        hardware.system_memory_free_mb = int(free_match.group(1)) // 1024


def _parse_int(text: str) -> int | None:
    try:
        return int(float(text))
    except ValueError:
        return None


def _loaded_chat_model(health: dict[str, Any]) -> str:
    for item in health.get("all_models_loaded") or []:
        if isinstance(item, dict) and str(item.get("type", "")).lower() in {"llm", "chat"}:
            return str(item.get("model_name") or "")
    return str(health.get("model_loaded") or "")
