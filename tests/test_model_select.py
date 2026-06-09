from lemonade_replay_studio.model_select import HardwareInfo, _loaded_chat_model, _recommend_chat, _recommend_stt


def test_recommend_chat_picks_best_preferred_model_that_fits():
    models = [
        {"id": "Qwen3-14B-GGUF", "recipe": "llamacpp", "size": 8.54, "downloaded": False},
        {"id": "Qwen3-8B-GGUF", "recipe": "llamacpp", "size": 5.25, "downloaded": True},
        {"id": "Qwen3-4B-GGUF", "recipe": "llamacpp", "size": 2.38, "downloaded": True},
    ]
    hardware = HardwareInfo(gpu_name="RTX", gpu_memory_total_mb=8192, gpu_memory_free_mb=8000)

    rec = _recommend_chat(models, hardware, explicit=None)

    assert rec.model_id == "Qwen3-8B-GGUF"
    assert rec.downloaded


def test_recommend_chat_falls_back_when_preferred_model_does_not_fit():
    models = [
        {"id": "Qwen3-8B-GGUF", "recipe": "llamacpp", "size": 5.25, "downloaded": True},
        {"id": "Qwen3-4B-GGUF", "recipe": "llamacpp", "size": 2.38, "downloaded": True},
    ]
    hardware = HardwareInfo(gpu_name="small", gpu_memory_total_mb=4096, gpu_memory_free_mb=3800)

    rec = _recommend_chat(models, hardware, explicit=None)

    assert rec.model_id == "Qwen3-4B-GGUF"


def test_recommend_chat_keeps_currently_loaded_model_even_when_free_vram_is_low():
    models = [
        {"id": "Qwen3-8B-GGUF", "recipe": "llamacpp", "size": 5.25, "downloaded": True},
        {"id": "Qwen3-4B-GGUF", "recipe": "llamacpp", "size": 2.38, "downloaded": True},
    ]
    hardware = HardwareInfo(gpu_name="RTX", gpu_memory_total_mb=8192, gpu_memory_free_mb=1900)

    rec = _recommend_chat(models, hardware, explicit=None, loaded_model="Qwen3-8B-GGUF")

    assert rec.model_id == "Qwen3-8B-GGUF"
    assert rec.detail == "currently loaded in Lemonade"


def test_recommend_stt_prefers_whisper_tiny():
    models = [
        {"id": "Whisper-Base", "recipe": "whispercpp", "downloaded": True},
        {"id": "Whisper-Tiny", "recipe": "whispercpp", "downloaded": False},
    ]

    rec = _recommend_stt(models, explicit=None)

    assert rec.model_id == "Whisper-Tiny"
    assert rec.command == "lemonade pull Whisper-Tiny"


def test_loaded_chat_model_uses_all_models_loaded_not_last_model_loaded():
    health = {
        "model_loaded": "Whisper-Tiny",
        "all_models_loaded": [
            {"model_name": "Whisper-Tiny", "type": "transcription"},
            {"model_name": "Qwen3-8B-GGUF", "type": "llm"},
        ],
    }

    assert _loaded_chat_model(health) == "Qwen3-8B-GGUF"
