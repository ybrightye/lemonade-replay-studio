from __future__ import annotations


RANKING_PROFILE = "gameplay_replay"
RANKING_PROMPT_VERSION = "gameplay_replay_v2_goal_conditioned"
DEFAULT_GOAL = "Make a funny gameplay replay. Prioritize humor, surprise, emotional reactions, failure/death, clutch plays, clear setup/payoff, and moments friends would want to rewatch."

RANKING_SYSTEM_PROMPT = (
    "Return ONLY valid compact JSON. No markdown. No reasoning. "
    "You are a replay producer selecting moments from gameplay commentary. "
    "Score moments for humor, surprise, emotional reaction, failure/death, clutch play, "
    "clear setup/payoff, and whether a friend would want to replay it. "
    "Do not choose a moment only because it is loud. Prefer context that sounds funny, "
    "important, tense, or memorable. Each clip should be about 15 seconds and must stay "
    "inside the candidate start/end range. "
    "Use this schema exactly: {\"moments\":[{\"id\":1,\"start\":0,\"end\":15,"
    "\"score\":8,\"title\":\"short title\",\"reason\":\"short reason\",\"quote\":\"short quote\"}]}"
)
