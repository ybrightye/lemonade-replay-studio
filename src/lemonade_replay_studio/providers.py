from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests

from .interest import GENERAL_DICTIONARY, InterestDictionary, blend_scores
from .models import Candidate, Moment
from .prompts import DEFAULT_GOAL, RANKING_PROFILE, RANKING_PROMPT_VERSION, RANKING_SYSTEM_PROMPT


class ProviderError(RuntimeError):
    pass


class AIProvider(ABC):
    name: str

    @abstractmethod
    def transcribe(self, audio_path: Path) -> str:
        raise NotImplementedError

    def transcribe_detailed(self, audio_path: Path) -> tuple[str, list[dict[str, Any]]]:
        """Return transcript text plus per-segment timings when available.

        The default has no timing info; providers that expose word/segment
        timestamps override this so clip boundaries can land on real spoken
        edges instead of interpolated estimates.
        """
        return self.transcribe(audio_path), []

    @abstractmethod
    def rank_moments(self, candidates: list[Candidate], transcripts: list[str], *, top_k: int, goal: str | None = None) -> list[Moment]:
        raise NotImplementedError


class MockProvider(AIProvider):
    name = "mock"

    def transcribe(self, audio_path: Path) -> str:
        return "Mock transcript: a reaction-heavy moment happened here."

    def rank_moments(self, candidates: list[Candidate], transcripts: list[str], *, top_k: int, goal: str | None = None) -> list[Moment]:
        ordered = sorted(zip(candidates, transcripts), key=lambda pair: pair[0].score, reverse=True)
        moments: list[Moment] = []
        for index, (candidate, transcript) in enumerate(ordered[:top_k], start=1):
            clip_duration = min(15.0, candidate.duration)
            center = (candidate.start + candidate.end) / 2
            start = max(0.0, center - clip_duration / 2)
            end = start + clip_duration
            moments.append(
                Moment(
                    start=start,
                    end=end,
                    score=candidate.score,
                    title=f"Local replay moment {index}",
                    reason=f"Selected from {candidate.reason}; transcript says: {transcript}",
                    quote=transcript,
                    metadata={"provider": self.name, "goal": goal or DEFAULT_GOAL, "cand_id": candidate.metadata.get("cand_id")},
                )
            )
        return sorted(moments, key=lambda item: item.start)


class LemonadeProvider(AIProvider):
    name = "lemonade"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:13305",
        chat_model: str | None = None,
        stt_model: str | None = None,
        timeout: int = 120,
        interest_dict: InterestDictionary | None = None,
        llm_trust: float = 0.85,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.chat_model = chat_model
        self.stt_model = stt_model
        self.timeout = timeout
        self.ranking_profile = RANKING_PROFILE
        self.ranking_prompt_version = RANKING_PROMPT_VERSION
        # Optional opt-in keyword lexicon blended with LLM scores. When None the
        # LLM is the sole signal in the happy path; the fallback ranker still
        # uses the game-agnostic GENERAL dictionary since it has no LLM to lean on.
        self.interest_dict = interest_dict
        self.interest_dict_name = interest_dict.name if interest_dict else None
        self.llm_trust = min(1.0, max(0.0, llm_trust))
        # Remember which versioned endpoint path worked so we stop re-probing
        # (and 404ing) the others on every subsequent call.
        self._endpoint_cache: dict[tuple[str, ...], str] = {}

    def health(self) -> dict[str, Any]:
        response = self._get_first(["/api/v1/health", "/v1/health", "/health"], timeout=10)
        return response.json()

    def models(self) -> list[dict[str, Any]]:
        response = self._get_first(["/api/v1/models?show_all=true", "/v1/models?show_all=true", "/api/v1/models", "/v1/models"], timeout=10)
        data = response.json()
        return list(data.get("data", []))

    def transcribe(self, audio_path: Path) -> str:
        text, _ = self.transcribe_detailed(audio_path)
        return text

    def transcribe_detailed(self, audio_path: Path) -> tuple[str, list[dict[str, Any]]]:
        # Ask for verbose_json so the server returns per-segment start/end times.
        # Servers that ignore it simply omit "segments"; we fall back to
        # interpolation, so this degrades rather than breaks.
        data: dict[str, str] = {"response_format": "verbose_json"}
        if self.stt_model:
            data["model"] = self.stt_model
        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "audio/wav")}
            response = self._post_first(
                ["/api/v1/audio/transcriptions", "/v1/audio/transcriptions"],
                data=data,
                files=files,
                timeout=self.timeout,
            )
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text")
        if not isinstance(text, str):
            raise ProviderError(f"Lemonade STT returned unexpected payload: {payload}")
        return text.strip(), _parse_stt_segments(payload)

    SINGLE_CALL_LIMIT = 16

    def rank_moments(self, candidates: list[Candidate], transcripts: list[str], *, top_k: int, goal: str | None = None) -> list[Moment]:
        if len(candidates) <= self.SINGLE_CALL_LIMIT:
            return self._rank_single(candidates, transcripts, top_k=top_k, goal=goal)
        # Too many candidates to rank in one comparable pass. Use cheap per-batch
        # passes ONLY to shortlist survivors -- per-batch scores are not
        # comparable across batches, so they are never merged directly -- then run
        # a single final ranking call over the survivors so the returned scores
        # share one context and are genuinely comparable.
        model = self.chat_model or self._pick_chat_model()
        ranking_goal = goal or DEFAULT_GOAL
        batch_size = self.SINGLE_CALL_LIMIT // 2
        shortlist: list[int] = []
        seen: set[int] = set()
        for batch_start in range(0, len(candidates), batch_size):
            batch_candidates = candidates[batch_start : batch_start + batch_size]
            batch_transcripts = transcripts[batch_start : batch_start + batch_size]
            for moment in self._rank_single(
                batch_candidates,
                batch_transcripts,
                top_k=min(4, len(batch_candidates)),
                goal=goal,
                model=model,
            ):
                candidate_id = int(moment.metadata.get("candidate_id", 0) or 0)
                global_index = batch_start + candidate_id - 1
                if 0 < candidate_id <= len(batch_candidates) and global_index not in seen:
                    seen.add(global_index)
                    shortlist.append(global_index)
        if not shortlist:
            return _rank_transcript_moments(candidates, transcripts, top_k=top_k, provider=self.name, model=model, goal=ranking_goal, interest_dict=self.interest_dict)
        shortlist = shortlist[: self.SINGLE_CALL_LIMIT]
        sub_candidates = [candidates[index] for index in shortlist]
        sub_transcripts = [transcripts[index] for index in shortlist]
        return self._rank_single(sub_candidates, sub_transcripts, top_k=top_k, goal=goal, model=model)

    def _rank_single(
        self,
        candidates: list[Candidate],
        transcripts: list[str],
        *,
        top_k: int,
        goal: str | None = None,
        model: str | None = None,
    ) -> list[Moment]:
        model = model or self.chat_model or self._pick_chat_model()
        ranking_goal = goal or DEFAULT_GOAL
        candidate_lines = []
        for index, (candidate, transcript) in enumerate(zip(candidates, transcripts), start=1):
            if transcript.strip():
                source = candidate.metadata.get("source", "transcript")
                visual = ""
                if source == "visual":
                    visual = (
                        f", visual_signal={candidate.metadata.get('visual_signal')}, "
                        f"visual_event_time={candidate.metadata.get('visual_event_timestamp')}, "
                        f"visual_score={candidate.metadata.get('visual_score')}"
                    )
                candidate_lines.append(
                    f"{index}. time={candidate.start:.1f}-{candidate.end:.1f}, "
                    f"source={source}, score={candidate.score:.3f}{visual}, reason={candidate.reason}, "
                    f"transcript={_compact_text(transcript, 320)}"
                )
        response = self._post_first(
            ["/api/v1/chat/completions", "/v1/chat/completions"],
            json_body={
                "model": model,
                "messages": [
                    {"role": "system", "content": RANKING_SYSTEM_PROMPT},
                    {"role": "user", "content": f"/no_think User goal: {ranking_goal}\nPick the best {top_k} moments for that goal.\n" + "\n".join(candidate_lines)},
                ],
                "temperature": 0.2,
                "max_tokens": 1200,
                "max_completion_tokens": 1200,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning_content") or ""
        try:
            parsed = _parse_json_object(content)
        except ProviderError:
            return _rank_transcript_moments(candidates, transcripts, top_k=top_k, provider=self.name, model=model, goal=ranking_goal, interest_dict=self.interest_dict)
        raw_moments = parsed if isinstance(parsed, list) else parsed.get("moments", [])
        moments = []
        candidate_by_id = {index: candidate for index, candidate in enumerate(candidates, start=1)}
        for item in raw_moments[:top_k]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "Replay moment"))
            reason = str(item.get("reason", ""))
            quote = str(item.get("quote", ""))
            if _looks_like_schema_placeholder(title, reason, quote):
                continue
            try:
                item_id = int(item.get("id", 0))
            except (TypeError, ValueError):
                item_id = 0
            source = candidate_by_id.get(item_id)
            if source:
                transcript = transcripts[item_id - 1] if 0 < item_id <= len(transcripts) else ""
                repaired = _candidate_id_matching_quote(candidates, transcripts, quote, current_id=item_id)
                if repaired and repaired != item_id:
                    item_id = repaired
                    source = candidate_by_id[item_id]
                    transcript = transcripts[item_id - 1]
                requested_start = _coerce_time(item.get("start", source.start), default=source.start)
                requested_end = _coerce_time(item.get("end", requested_start + 15.0), default=requested_start + 15.0, prefer_end=True)
                phrase_bounds = _phrase_bounds_from_quote(
                    source,
                    transcript,
                    quote,
                )
                if phrase_bounds:
                    start, end = phrase_bounds
                    selection_boundary_method = "stt_segment" if source.metadata.get("segments") else "phrase_estimate"
                elif source.start <= requested_start < requested_end <= source.end:
                    start = requested_start
                    end = requested_end
                    selection_boundary_method = "model"
                else:
                    clip_duration = min(15.0, source.duration)
                    center = (source.start + source.end) / 2
                    start = max(source.start, center - clip_duration / 2)
                    end = min(source.end, start + clip_duration)
                    selection_boundary_method = "centered_fallback"
            else:
                transcript = ""
                start = _coerce_time(item.get("start", 0.0), default=0.0)
                end = _coerce_time(item.get("end", start + 15.0), default=start + 15.0, prefer_end=True)
                selection_boundary_method = "model"
            llm_score = float(item.get("score", source.score if source else 0.0))
            if self.interest_dict is not None:
                keyword_score, keyword_reason = self.interest_dict.score(transcript or quote)
                final_score = blend_scores(llm_score, keyword_score, llm_trust=self.llm_trust)
            else:
                keyword_score = None
                keyword_reason = ""
                final_score = llm_score
            if _is_generic_text(title):
                title = _title_from_quote(quote or transcript)
            if _is_generic_text(reason):
                reason = keyword_reason or _neutral_reason(quote or transcript)
            moments.append(
                Moment(
                    start=start,
                    end=end,
                    score=final_score,
                    title=title,
                    reason=reason,
                    quote=quote,
                    metadata={
                        "provider": self.name,
                        "model": model,
                        "ranking_profile": self.ranking_profile,
                        "ranking_prompt_version": self.ranking_prompt_version,
                        "goal": ranking_goal,
                        "selection_boundary_method": selection_boundary_method,
                        "candidate_id": item_id,
                        "cand_id": source.metadata.get("cand_id") if source else None,
                        "llm_score": llm_score,
                        "keyword_score": keyword_score,
                        "interest_dict": self.interest_dict_name,
                        "llm_trust": self.llm_trust,
                    },
                )
            )
        if not moments:
            return _rank_transcript_moments(candidates, transcripts, top_k=top_k, provider=self.name, model=model, goal=ranking_goal, interest_dict=self.interest_dict)
        return sorted(moments, key=lambda item: item.start)

    def _pick_chat_model(self) -> str:
        models = self.models()
        for model in models:
            if _is_chat_model(model) and model.get("downloaded"):
                return str(model["id"])
        for model in models:
            if _is_chat_model(model):
                return str(model["id"])
        if models:
            return str(models[0]["id"])
        raise ProviderError("No Lemonade chat models found. Pull or load a local model first.")

    def _ordered_paths(self, paths: list[str]) -> list[str]:
        cached = self._endpoint_cache.get(tuple(paths))
        if cached and cached in paths:
            return [cached] + [path for path in paths if path != cached]
        return paths

    def _get_first(self, paths: list[str], *, timeout: int) -> requests.Response:
        last_error: Exception | None = None
        for path in self._ordered_paths(paths):
            try:
                response = requests.get(f"{self.base_url}{path}", timeout=timeout)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
            except requests.RequestException as exc:
                last_error = exc
                continue
            self._endpoint_cache[tuple(paths)] = path
            return response
        if last_error:
            raise last_error
        raise ProviderError(f"No Lemonade endpoint found for {paths}")

    def _post_first(
        self,
        paths: list[str],
        *,
        timeout: int,
        json_body: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> requests.Response:
        last_error: Exception | None = None
        for path in self._ordered_paths(paths):
            try:
                if files:
                    for value in files.values():
                        file_obj = value[1] if isinstance(value, tuple) and len(value) > 1 else None
                        if hasattr(file_obj, "seek"):
                            file_obj.seek(0)
                response = requests.post(
                    f"{self.base_url}{path}",
                    json=json_body,
                    data=data,
                    files=files,
                    timeout=timeout,
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
            except requests.RequestException as exc:
                last_error = exc
                continue
            self._endpoint_cache[tuple(paths)] = path
            return response
        if last_error:
            raise last_error
        raise ProviderError(f"No Lemonade endpoint found for {paths}")


def get_provider(
    name: str,
    *,
    base_url: str,
    chat_model: str | None,
    stt_model: str | None,
    interest_dict: InterestDictionary | None = None,
    llm_trust: float = 0.85,
) -> AIProvider:
    if name == "mock":
        return MockProvider()
    if name == "lemonade":
        return LemonadeProvider(
            base_url=base_url,
            chat_model=chat_model,
            stt_model=stt_model,
            interest_dict=interest_dict,
            llm_trust=llm_trust,
        )
    raise ProviderError(f"Unknown provider: {name}")


def _normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    for suffix in ("/api/v1", "/v1"):
        if base_url.endswith(suffix):
            return base_url[: -len(suffix)]
    return base_url


def _is_chat_model(model: dict[str, Any]) -> bool:
    labels = {str(label).lower() for label in model.get("labels", [])}
    model_type = str(model.get("type", "")).lower()
    recipe = str(model.get("recipe", "")).lower()
    model_id = str(model.get("id") or model.get("name") or "").lower()
    if {"llm", "chat", "reasoning", "tool-calling"} & labels:
        return True
    if "chat" in model_type or "llm" in model_type:
        return True
    if recipe == "llamacpp":
        return not any(token in model_id for token in ("embedding", "embed", "reranker"))
    return False


def _looks_like_schema_placeholder(title: str, reason: str, quote: str) -> bool:
    combined = " ".join([title, reason, quote]).lower()
    return any(placeholder == value.strip().lower() for placeholder, value in (("short title", title), ("short reason", reason), ("short quote", quote))) or (
        "short title" in combined and "short reason" in combined
    )


def _is_generic_text(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return normalized in {"", "transcript context window", "short reason", "short title", "replay moment"}


def _title_from_quote(text: str) -> str:
    phrases = _split_phrases(text)
    if not phrases:
        return "Replay moment"
    title = phrases[0].strip(" -")
    if len(title) > 72:
        title = title[:69].rstrip() + "..."
    return title or "Replay moment"


def _neutral_reason(text: str) -> str:
    quote = _compact_text(text, 80)
    if quote:
        return f"Selected as a notable spoken moment: {quote}"
    return "Selected as a notable spoken moment."


def _rank_transcript_moments(
    candidates: list[Candidate],
    transcripts: list[str],
    *,
    top_k: int,
    provider: str,
    model: str,
    goal: str | None = None,
    interest_dict: InterestDictionary | None = None,
) -> list[Moment]:
    # This path runs only when the LLM produced nothing usable, so it needs its
    # own scorer. Use the caller's opt-in dictionary if any, otherwise the
    # game-agnostic baseline (never a franchise-specific one by default).
    dictionary = interest_dict or GENERAL_DICTIONARY
    moments: list[Moment] = []
    for candidate, transcript in zip(candidates, transcripts):
        score, reason = dictionary.score(transcript)
        phrases = _split_phrases(transcript)
        quote = _best_phrase(phrases, dictionary) if phrases else _compact_text(transcript, 180)
        phrase_bounds = _phrase_bounds_from_quote(candidate, transcript, quote)
        if phrase_bounds:
            start, end = phrase_bounds
            method = "stt_segment" if candidate.metadata.get("segments") else "phrase_estimate"
        else:
            clip_duration = min(15.0, candidate.duration)
            center = (candidate.start + candidate.end) / 2
            start = max(candidate.start, center - clip_duration / 2)
            end = min(candidate.end, start + clip_duration)
            method = "centered_fallback"
        moments.append(
            Moment(
                start=start,
                end=end,
                score=score,
                title=_title_from_quote(quote),
                reason=reason,
                quote=quote,
                metadata={
                    "provider": provider,
                    "model": model,
                    "goal": goal or DEFAULT_GOAL,
                    "selection_boundary_method": method,
                    "cand_id": candidate.metadata.get("cand_id"),
                    "rank_fallback": "transcript_interest",
                },
            )
        )
    moments.sort(key=lambda item: item.score, reverse=True)
    return sorted(moments[:top_k], key=lambda item: item.start)


def _best_phrase(phrases: list[str], dictionary: InterestDictionary) -> str:
    scored = []
    for phrase in phrases:
        score, _ = dictionary.score(phrase)
        scored.append((score, len(_tokens(phrase)), phrase))
    if not scored:
        return ""
    return max(scored, key=lambda item: (item[0], item[1]))[2]


def _coerce_time(value: Any, *, default: float, prefer_end: bool = False) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    numbers = re.findall(r"\d+(?:\.\d+)?", str(value))
    if not numbers:
        return default
    return float(numbers[-1 if prefer_end else 0])


def _parse_json_object(text: str) -> dict[str, Any] | list[Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        for start in sorted(starts):
            try:
                parsed, _ = decoder.raw_decode(text[start:])
                return parsed
            except json.JSONDecodeError:
                continue
        raise ProviderError(f"Could not parse JSON from model response: {text[:500]}")


def _compact_text(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _parse_stt_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return []
    segments: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        segments.append({"start": start, "end": end, "text": str(item.get("text", "")).strip()})
    return segments


def _phrase_infos_for(candidate: Candidate, transcript: str) -> list[dict[str, float | str]]:
    # Prefer real STT segment timings (absolute source seconds, attached to the
    # candidate during transcription); otherwise interpolate by token count.
    segments = candidate.metadata.get("segments")
    if segments:
        infos = [
            {"text": str(seg.get("text", "")), "start": float(seg["start"]), "end": float(seg["end"])}
            for seg in segments
            if seg.get("text")
        ]
        if infos:
            return infos
    phrases = _split_phrases(transcript)
    if not phrases:
        return []
    return _estimate_phrase_times(candidate, phrases)


def _phrase_bounds_from_quote(candidate: Candidate, transcript: str, quote: str) -> tuple[float, float] | None:
    phrase_infos = _phrase_infos_for(candidate, transcript)
    if not phrase_infos:
        return None
    quote_tokens = set(_tokens(quote))
    if not quote_tokens:
        return None
    scored: list[tuple[float, int]] = []
    for index, info in enumerate(phrase_infos):
        phrase_tokens = set(_tokens(info["text"]))
        if not phrase_tokens:
            continue
        overlap = len(quote_tokens & phrase_tokens)
        score = overlap / max(1, len(quote_tokens))
        scored.append((score, index))
    if not scored:
        return None
    score, index = max(scored, key=lambda item: item[0])
    if score <= 0:
        return None

    start_index = index
    end_index = index
    # Include a little spoken setup/payoff, but keep clips tight.
    if index > 0:
        start_index = index - 1
    if index + 1 < len(phrase_infos):
        end_index = index + 1
    start = float(phrase_infos[start_index]["start"])
    end = float(phrase_infos[end_index]["end"])
    if end - start < 10 and end_index + 1 < len(phrase_infos):
        end_index += 1
        end = float(phrase_infos[end_index]["end"])
    if end - start > 24:
        center = (float(phrase_infos[index]["start"]) + float(phrase_infos[index]["end"])) / 2
        start = max(candidate.start, center - 12)
        end = min(candidate.end, center + 12)
    return start, end


def _candidate_id_matching_quote(
    candidates: list[Candidate],
    transcripts: list[str],
    quote: str,
    *,
    current_id: int,
) -> int | None:
    quote_tokens = set(_tokens(quote))
    if len(quote_tokens) < 3:
        return None
    current_transcript = transcripts[current_id - 1] if 0 < current_id <= len(transcripts) else ""
    current_score = _token_overlap_score(quote_tokens, current_transcript)
    best_id = current_id
    best_score = current_score
    for index, transcript in enumerate(transcripts[: len(candidates)], start=1):
        score = _token_overlap_score(quote_tokens, transcript)
        if score > best_score:
            best_id = index
            best_score = score
    if best_id != current_id and best_score >= 0.35 and best_score >= current_score + 0.25:
        return best_id
    return None


def _token_overlap_score(quote_tokens: set[str], transcript: str) -> float:
    if not quote_tokens:
        return 0.0
    transcript_tokens = set(_tokens(transcript))
    if not transcript_tokens:
        return 0.0
    return len(quote_tokens & transcript_tokens) / len(quote_tokens)


def _split_phrases(transcript: str) -> list[str]:
    lines: list[str] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^>+\s*", "", line)
        parts = re.split(r"(?<=[.!?])\s+", line)
        lines.extend(part.strip() for part in parts if part.strip())
    return lines


def _estimate_phrase_times(candidate: Candidate, phrases: list[str]) -> list[dict[str, float | str]]:
    weights = [max(1, len(_tokens(phrase))) for phrase in phrases]
    total_weight = sum(weights) or 1
    cursor = candidate.start
    infos: list[dict[str, float | str]] = []
    for phrase, weight in zip(phrases, weights):
        phrase_duration = candidate.duration * (weight / total_weight)
        start = cursor
        end = min(candidate.end, cursor + phrase_duration)
        infos.append({"text": phrase, "start": start, "end": end})
        cursor = end
    if infos:
        infos[-1]["end"] = candidate.end
    return infos


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())
