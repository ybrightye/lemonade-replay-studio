from __future__ import annotations

import json
from pathlib import Path

from .models import Moment
from .timefmt import fmt_seconds


def write_json(output_dir: Path, moments: list[Moment], *, run_metadata: dict | None = None) -> Path:
    path = output_dir / "moments.json"
    data = [
        {
            "start": moment.start,
            "end": moment.end,
            "score": moment.score,
            "title": moment.title,
            "reason": moment.reason,
            "quote": moment.quote,
            "clip_path": str(moment.clip_path) if moment.clip_path else None,
            "metadata": moment.metadata,
        }
        for moment in moments
    ]
    payload = {"run": run_metadata or {}, "moments": data}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_markdown(output_dir: Path, moments: list[Moment]) -> Path:
    path = output_dir / "recap.md"
    lines = ["# Replay Recap", ""]
    for index, moment in enumerate(moments, start=1):
        lines.append(f"{index}. **{moment.title}** ({fmt_seconds(moment.start)}-{fmt_seconds(moment.end)})")
        lines.append(f"   {moment.reason}")
        if moment.quote:
            lines.append(f"   Quote: {moment.quote}")
        if moment.clip_path:
            lines.append(f"   Clip: `{moment.clip_path.name}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_html(output_dir: Path, moments: list[Moment], *, reel_path: Path | None) -> Path:
    path = output_dir / "moment_map.html"
    total_clip_seconds = sum(moment.duration for moment in moments)
    cards = []
    for index, moment in enumerate(moments, start=1):
        video = ""
        if moment.clip_path:
            rel = moment.clip_path.relative_to(output_dir)
            video = f'<video controls src="{rel.as_posix()}"></video>'
        clip_link = ""
        if moment.clip_path:
            rel = moment.clip_path.relative_to(output_dir)
            clip_link = f'<a class="download" href="{rel.as_posix()}" download>Download clip</a>'
        quote = f"<blockquote>{_esc(moment.quote)}</blockquote>" if moment.quote else ""
        visual = _visual_html(output_dir, moment)
        cards.append(
            f"""
            <article>
              <div class="card-head">
                <span class="rank">#{index}</span>
                <span class="time">{fmt_seconds(moment.start)} - {fmt_seconds(moment.end)}</span>
                <span class="score">score {moment.score:g}</span>
              </div>
              <h2>{_esc(moment.title)}</h2>
              <p>{_esc(moment.reason)}</p>
              {quote}
              {visual}
              {clip_link}
              {video}
            </article>
            """
        )
    reel = ""
    if reel_path:
        reel_rel = reel_path.relative_to(output_dir)
        reel = f"""
        <section class="reel">
          <div class="section-head">
            <h2>Combined Highlight Reel</h2>
            <a class="download" href="{reel_rel.as_posix()}" download>Download reel</a>
          </div>
          <video controls src="{reel_rel.as_posix()}"></video>
        </section>
        """
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lemonade Replay Studio Moment Map</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; background: #101214; color: #f2f4f8; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ font-size: 32px; margin: 0 0 8px; }}
    h2 {{ font-size: 20px; margin: 8px 0 8px; }}
    .sub {{ color: #a8b0bd; margin: 0 0 24px; }}
    .stats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 18px 0 26px; }}
    .stat {{ border: 1px solid #2b333d; border-radius: 8px; padding: 12px; background: #171a1f; }}
    .stat strong {{ display: block; font-size: 22px; }}
    .stat span {{ color: #a8b0bd; font-size: 13px; }}
    article, .reel {{ border: 1px solid #2b333d; border-radius: 8px; padding: 18px; margin: 16px 0; background: #171a1f; }}
    .section-head, .card-head {{ display: flex; align-items: center; gap: 10px; justify-content: space-between; flex-wrap: wrap; }}
    .card-head {{ justify-content: flex-start; color: #a8b0bd; font-size: 14px; }}
    .rank {{ color: #f6c85f; font-weight: 700; }}
    .time {{ color: #8fd6ff; }}
    .score {{ color: #9ed6b5; }}
    p {{ color: #dce2ea; line-height: 1.5; }}
    blockquote {{ margin: 12px 0; color: #d6dde8; border-left: 3px solid #f6c85f; padding-left: 12px; }}
    .download {{ color: #8fd6ff; text-decoration: none; font-size: 14px; }}
    .download:hover {{ text-decoration: underline; }}
    .visual {{ margin: 14px 0; border-top: 1px solid #2b333d; padding-top: 12px; }}
    .visual h3 {{ margin: 0 0 8px; font-size: 15px; color: #f2f4f8; }}
    .visual p {{ margin: 0 0 10px; color: #a8b0bd; font-size: 13px; }}
    .visual-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .visual-grid figure {{ margin: 0; }}
    .visual-grid img {{ width: 100%; border-radius: 6px; border: 1px solid #2b333d; background: #000; }}
    .visual-grid figcaption {{ margin-top: 4px; font-size: 12px; color: #a8b0bd; }}
    video {{ width: 100%; max-height: 560px; background: #000; border-radius: 6px; margin-top: 12px; }}
    @media (max-width: 720px) {{
      .stats {{ grid-template-columns: 1fr; }}
      .visual-grid {{ grid-template-columns: 1fr; }}
      main {{ padding: 24px 14px 40px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Lemonade Replay Studio</h1>
    <p class="sub">Local replay map generated from recording analysis. Source timestamps are burned into each clip.</p>
    <section class="stats" aria-label="summary">
      <div class="stat"><strong>{len(moments)}</strong><span>selected moments</span></div>
      <div class="stat"><strong>{fmt_seconds(total_clip_seconds)}</strong><span>highlight reel length</span></div>
      <div class="stat"><strong>local</strong><span>Lemonade STT + LLM workflow</span></div>
    </section>
    {reel}
    {''.join(cards)}
  </main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _visual_html(output_dir: Path, moment: Moment) -> str:
    visual = moment.metadata.get("visual")
    if not isinstance(visual, dict):
        return ""
    before = str(visual.get("before") or "")
    after = str(visual.get("after") or "")
    if not before or not after:
        return ""
    signal = _esc(str(visual.get("signal") or visual.get("roi") or "region"))
    score = visual.get("score")
    score_text = f", score {float(score):.3f}" if isinstance(score, (int, float)) else ""
    timestamp = visual.get("event_timestamp")
    time_text = f" near {fmt_seconds(float(timestamp))}" if isinstance(timestamp, (int, float)) else ""
    reason = _esc(str(visual.get("reason") or "ROI visual change"))
    return f"""
      <section class="visual">
        <h3>Visual Event Evidence</h3>
        <p>{reason} ({signal}{time_text}{score_text})</p>
        <div class="visual-grid">
          <figure><img src="{_esc(before)}" alt="Visual ROI before change"><figcaption>Before ROI crop</figcaption></figure>
          <figure><img src="{_esc(after)}" alt="Visual ROI after change"><figcaption>After ROI crop</figcaption></figure>
        </div>
      </section>
    """
