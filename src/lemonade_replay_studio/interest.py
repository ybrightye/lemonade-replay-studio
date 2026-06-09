"""Keyword interest dictionaries used to nudge or fall back from LLM moment ranking.

The interest scorer is a cheap, transparent heuristic: it looks for reaction and
gameplay words in a transcript and returns a 0-10 score plus a human-readable
reason. It is deliberately *separate* from the LLM so the two signals can be
combined with an explicit trust weight (see :func:`blend_scores`) instead of the
older ``max(llm, keyword)`` rule, which could only ever raise a score and let a
keyword false-positive silently override the model.

Dictionaries are opt-in and game-specific. ``general`` is a game-agnostic
baseline (no franchise vocabulary, so words like "souls" do not mis-fire on
games where they mean something mundane). Named builtins such as ``dark-souls``
and per-game JSON files supplied by the user *replace* the baseline rather than
extend it, which keeps cross-game false positives out.
"""

from __future__ import annotations

from dataclasses import dataclass
import functools
import json
import re
from pathlib import Path


DICTIONARIES_DIR = Path(__file__).parent / "dictionaries"


@dataclass(frozen=True)
class InterestGroup:
    """One weighted bag of words with a label used in the reason string."""

    words: tuple[str, ...]
    weight: float
    label: str


@dataclass(frozen=True)
class InterestDictionary:
    name: str
    groups: tuple[InterestGroup, ...]
    length_bonus: bool = True

    def score(self, text: str) -> tuple[float, str]:
        """Return a 0-10 interest score and a "Selected for ..." reason."""
        lowered = text.lower()
        signals: list[str] = []
        score = 0.0
        for group in self.groups:
            hits = sum(1 for word in group.words if _word_present(word, lowered))
            if hits:
                # Cap per-group hits so one keyword-stuffed line cannot dominate.
                score += group.weight * min(2, hits)
                signals.append(group.label)
        if self.length_bonus:
            score += min(1.0, len(_word_tokens(text)) / 120)
        if not signals:
            signals.append("clear spoken context")
        return min(10.0, score), "Selected for " + ", ".join(dict.fromkeys(signals))


# Game-agnostic baseline. Used for the LLM-failure fallback ranker even when the
# user opts out of a dictionary, because that degraded path needs *some* signal.
# Intentionally contains no franchise-specific vocabulary.
GENERAL_DICTIONARY = InterestDictionary(
    name="general",
    groups=(
        InterestGroup(("laugh", "laughs", "laughing", "hahaha", "lol"), 2.5, "laughter"),
        InterestGroup(("died", "die", "dead", "death", "killed", "dropped", "lost"), 2.0, "death or failure reaction"),
        InterestGroup(("oh no", "oh shit", "fuck", "shit", "wow", "my god", "goodness", "what the"), 1.8, "strong reaction"),
        InterestGroup(("nice", "let's go", "clutch", "watch this", "run", "attack"), 1.2, "active gameplay beat"),
        InterestGroup(("boss", "enemy", "almost", "barely", "close"), 0.7, "tense gameplay context"),
    ),
)


def blend_scores(llm_score: float, keyword_score: float, *, llm_trust: float) -> float:
    """Combine an LLM score and a keyword score on a shared 0-10 scale.

    ``llm_trust`` in [0, 1] weights the LLM: 1.0 ignores the keyword score, 0.0
    ignores the LLM. Unlike ``max(llm, keyword)`` this can move a score in either
    direction, so a low-trust setting can also *demote* a weak model's picks.
    """
    alpha = _clamp01(llm_trust)
    llm = _clamp01(llm_score / 10.0)
    keyword = _clamp01(keyword_score / 10.0)
    return (alpha * llm + (1.0 - alpha) * keyword) * 10.0


def load_interest_dictionary(spec: str | None) -> InterestDictionary | None:
    """Resolve a ``--interest-dict`` spec to a dictionary, or ``None`` if off.

    ``None``/``"none"``/``"off"`` -> no keyword influence in the LLM path.
    A builtin name (e.g. ``dark-souls``) -> ``dictionaries/<name>.json``.
    A path ending in ``.json`` (or an existing file) -> that file.
    """
    if spec is None:
        return None
    name = spec.strip()
    if name.lower() in ("", "none", "off"):
        return None
    path = Path(name)
    if path.suffix.lower() == ".json" or path.exists():
        if not path.exists():
            raise ValueError(f"Interest dictionary file not found: {path}")
        return _from_file(path)
    builtin = DICTIONARIES_DIR / f"{name}.json"
    if builtin.exists():
        return _from_file(builtin)
    available = ", ".join(sorted(p.stem for p in DICTIONARIES_DIR.glob("*.json"))) or "none"
    raise ValueError(
        f"Unknown interest dictionary: {spec!r}. "
        f"Use 'none', a builtin ({available}), or a path to a .json file."
    )


def _from_file(path: Path) -> InterestDictionary:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read interest dictionary {path}: {exc}") from exc
    return _from_mapping(data, default_name=path.stem)


def _from_mapping(data: dict, *, default_name: str) -> InterestDictionary:
    raw_groups = data.get("groups", [])
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ValueError(f"Interest dictionary '{default_name}' has no groups.")
    groups = tuple(
        InterestGroup(
            words=tuple(str(word).lower() for word in group.get("words", [])),
            weight=float(group.get("weight", 1.0)),
            label=str(group.get("label", "notable moment")),
        )
        for group in raw_groups
    )
    return InterestDictionary(
        name=str(data.get("name", default_name)),
        groups=groups,
        length_bonus=bool(data.get("length_bonus", True)),
    )


@functools.lru_cache(maxsize=4096)
def _compiled(word: str) -> re.Pattern[str]:
    # Lookarounds give word-boundary matching that still works for tokens with
    # trailing punctuation (e.g. "no!") and multi-word phrases (e.g. "oh no"),
    # so "die" no longer fires inside "studied" and "souls" no longer fires as a
    # substring of unrelated words.
    return re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE)


def _word_present(word: str, text: str) -> bool:
    return _compiled(word).search(text) is not None


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
