import pytest

from lemonade_replay_studio.interest import (
    GENERAL_DICTIONARY,
    blend_scores,
    load_interest_dictionary,
)


def test_word_boundary_avoids_substring_false_positives():
    # "die" must not fire inside "studied"; "lost" must not fire inside "glossy".
    score, reason = GENERAL_DICTIONARY.score("I studied the glossy menu carefully.")
    assert "death or failure reaction" not in reason
    assert score < 1.0  # only the small length bonus, no keyword groups


def test_general_dictionary_does_not_treat_souls_as_death():
    # League: "souls" is a mundane mechanic word and must not score as a death.
    score, reason = GENERAL_DICTIONARY.score("Thresh grabbed the souls off that minion.")
    assert "death or failure reaction" not in reason


def test_general_dictionary_detects_real_reactions():
    score, reason = GENERAL_DICTIONARY.score("Oh no, I died and everyone laughs.")
    assert "death or failure reaction" in reason
    assert "laughter" in reason
    assert score > 3.0


def test_dark_souls_builtin_fires_on_souls():
    dictionary = load_interest_dictionary("dark-souls")
    assert dictionary is not None
    score, reason = dictionary.score("I lost all my souls at the bonfire.")
    assert "lost-souls" in reason
    assert score > 2.0


def test_blend_respects_trust_weight():
    assert blend_scores(8.0, 2.0, llm_trust=1.0) == pytest.approx(8.0)
    assert blend_scores(8.0, 2.0, llm_trust=0.0) == pytest.approx(2.0)
    assert blend_scores(8.0, 2.0, llm_trust=0.5) == pytest.approx(5.0)


def test_blend_can_demote_not_only_promote():
    # Unlike max(), a low-trust blend pulls a confident-but-unsupported LLM
    # score down toward a weak keyword score.
    blended = blend_scores(9.0, 1.0, llm_trust=0.3)
    assert blended < 9.0


def test_load_interest_dictionary_off_returns_none():
    assert load_interest_dictionary(None) is None
    assert load_interest_dictionary("none") is None
    assert load_interest_dictionary("off") is None


def test_load_interest_dictionary_from_path(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        '{"name": "custom", "groups": [{"words": ["boom"], "weight": 3.0, "label": "boom"}]}',
        encoding="utf-8",
    )
    dictionary = load_interest_dictionary(str(path))
    assert dictionary is not None
    assert dictionary.name == "custom"
    score, reason = dictionary.score("and then boom it happened")
    assert "boom" in reason


def test_load_interest_dictionary_unknown_name_raises():
    with pytest.raises(ValueError):
        load_interest_dictionary("not-a-real-game")
