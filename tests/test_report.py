from lemonade_replay_studio.models import Moment
from lemonade_replay_studio.report import write_html, write_json, write_markdown


def test_report_writers_create_expected_files(tmp_path):
    clip_dir = tmp_path / "clips"
    clip_dir.mkdir()
    clip_path = clip_dir / "clip.mp4"
    clip_path.write_bytes(b"fake")
    reel_path = tmp_path / "highlight_reel.mp4"
    reel_path.write_bytes(b"fake")
    moments = [
        Moment(
            start=1,
            end=4,
            score=8,
            title="Good moment",
            reason="Funny context",
            quote="nice",
            clip_path=clip_path,
            metadata={
                "visual": {
                    "roi": "top_left",
                    "event_timestamp": 2.0,
                    "score": 0.1,
                    "reason": "visual HUD change",
                    "before": "visual/before.jpg",
                    "after": "visual/after.jpg",
                }
            },
        )
    ]

    json_path = write_json(tmp_path, moments, run_metadata={"ranking_prompt_version": "test_v1"})
    markdown_path = write_markdown(tmp_path, moments)
    html_path = write_html(tmp_path, moments, reel_path=reel_path)

    assert json_path.exists()
    assert '"ranking_prompt_version": "test_v1"' in json_path.read_text(encoding="utf-8")
    assert markdown_path.exists()
    assert markdown_path.name == "recap.md"
    html = html_path.read_text(encoding="utf-8")
    assert "Combined Highlight Reel" in html
    assert "Download reel" in html
    assert "Good moment" in html
    assert "Visual Event Evidence" in html
