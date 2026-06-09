# Roadmap

Lemonade Replay Studio is intentionally small right now: local recordings go in, replay maps and clips come out. The best next steps are the ones that make it useful across more games, creators, and local AI setups.

## Near Term

- Improve game-specific visual signals:
  - `hp_bar` presets for more games
  - kill feed changes
  - KDA / scoreboard changes
  - minimap event spikes
  - chat/reaction overlays
- Add more demo fixtures and reports from different genres:
  - Souls-like games
  - MOBAs
  - shooters
  - strategy games
  - co-op party games
- Improve setup docs for Windows users.
- Add a report section that shows why each candidate was selected or rejected. (Started: `--keep-candidates` writes `candidates.json` with each candidate's `dropped_at` stage.)
- Done: `--visual-min-clips N` reserves up to N of the `top_clips` slots for the highest-scoring `source=visual` candidates (e.g. `hp_bar` events), so detected HP-drop moments are guaranteed in the reel with their before/after evidence instead of losing at LLM ranking. The Dark Souls demo sets it to 2.
- Make watch mode easier to use with OBS recording folders.

## Lemonade / Local AI

- Add recommended model profiles by available memory.
- Improve small-model prompts for `Qwen3-8B-GGUF` and smaller models.
- Add optional Lemonade vision-model setup when available:
  - ask the user what signals they care about
  - show one representative frame
  - propose highlighted visual regions
  - let the user approve before scanning the whole video
- Add TTS summary output through Lemonade when local TTS is available.

## Contributor-Friendly Ideas

- Add a named visual signal preset for your favorite game.
- Share an anonymized `moments.json` from your own run.
- Add a new ranking goal preset, such as "competitive review," "funny moments," "tutorial highlights," or "podcast recap."
- Improve the HTML report styling or filtering.
- Test on AMD Ryzen AI / Radeon / Strix Halo hardware and share model/runtime notes.
- Improve clip boundary detection without making clips too long.

## Out Of Scope For Now

- Real-time in-game assistance.
- Competitive automation.
- Cloud clipping service features.
- Full vertical-shorts editing templates.
- Training or fine-tuning models.
