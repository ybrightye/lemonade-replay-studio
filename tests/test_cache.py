from pathlib import Path

from lemonade_replay_studio.cache import AnalysisCache


def test_cache_round_trip(tmp_path):
    cache = AnalysisCache(tmp_path / "cache.json")
    key = cache.transcript_key(
        input_path=Path("recording.mp4"),
        start=1.23456,
        end=9.87654,
        provider="lemonade",
        model="Whisper-Tiny",
    )
    cache.set_transcript(key, "hello there")
    cache.save()

    reloaded = AnalysisCache(tmp_path / "cache.json")
    assert reloaded.get_transcript(key) == "hello there"


def test_cache_ignores_corrupt_json(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json", encoding="utf-8")

    cache = AnalysisCache(path)

    assert cache.data == {"transcripts": {}}
