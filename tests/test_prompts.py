from lemonade_replay_studio.prompts import DEFAULT_GOAL, RANKING_PROFILE, RANKING_PROMPT_VERSION, RANKING_SYSTEM_PROMPT


def test_ranking_prompt_contract_is_named_and_clip_focused():
    assert RANKING_PROFILE == "gameplay_replay"
    assert RANKING_PROMPT_VERSION == "gameplay_replay_v2_goal_conditioned"
    assert "funny gameplay replay" in DEFAULT_GOAL
    assert "humor, surprise, emotional reaction" in RANKING_SYSTEM_PROMPT
    assert "failure/death" in RANKING_SYSTEM_PROMPT
    assert "valid compact JSON" in RANKING_SYSTEM_PROMPT
