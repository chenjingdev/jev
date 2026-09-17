"""Jev judgement as plain control flow: check / true / switch / score / ask."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from typesafe_sdk import (
    Answer,
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeClient,
    TypeSafeError,
    TypeSafeUnprocessableEntityError,
)
from typesafe_sdk.constants import DEFAULT_MODEL

from .cache import Cache, make_key, state_hash
from .log import CallLog

__all__ = [
    "Decision",
    "ask",
    "check",
    "configure",
    "decide",
    "options",
    "reset",
    "scale",
    "score",
    "switch",
    "true",
]

logger = logging.getLogger("sif")

#: State accepted by the API: text, a mapping or a sequence.
State = Any

#: Question name used for the single-question helpers; part of the cache key.
_KEY = "answer"

DEFAULT_SWITCH_INSTRUCTIONS = "Which option best describes the input?"

_UNSET: Any = object()

#: Errors a `default` must never paper over: the request is wrong, not unlucky.
#: Retrying or falling back would only hide a broken key or a malformed question.
_FATAL_ERRORS = (
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeUnprocessableEntityError,
)


def _is_fatal(error: TypeSafeError) -> bool:
    """True for configuration errors, false for transient API failures.

    The SDK raises a bare `TypeSafeError` only for client-side mistakes - a missing
    API key, an unencodable body, a malformed question. Everything that can be
    blamed on the network or the service is a subclass.
    """
    return isinstance(error, _FATAL_ERRORS) or type(error) is TypeSafeError


# --------------------------------------------------------------------------- config


@dataclass
class _Config:
    model: str | None = None
    timeout: float | None = None
    cache: bool | str | Path | None = None
    log: bool | str | Path | None = None


_config = _Config()
_lock = threading.Lock()
_client: TypeSafeClient | None = None
_cache: Cache | None = None
_call_log: CallLog | None = None


def configure(
    *,
    model: str | Any = _UNSET,
    timeout: float | Any = _UNSET,
    cache: bool | str | Path | Any = _UNSET,
    log: bool | str | Path | Any = _UNSET,
) -> None:
    """Set the module-wide client options; drops the cached singletons."""
    global _client, _cache, _call_log
    with _lock:
        if model is not _UNSET:
            _config.model = model
        if timeout is not _UNSET:
            _config.timeout = timeout
        if cache is not _UNSET:
            _config.cache = cache
            _cache = None
        if log is not _UNSET:
            _config.log = log
            _call_log = None
        if model is not _UNSET or timeout is not _UNSET:
            if _client is not None:
                _client.close()
            _client = None


def reset() -> None:
    """Forget the client, cache handle and log handle (mostly for tests)."""
    global _client, _cache, _call_log
    with _lock:
        if _client is not None:
            _client.close()
        _client = None
        _cache = None
        _call_log = None


def _get_client() -> TypeSafeClient:
    """Lazily build the shared client so connections are kept alive."""
    global _client
    with _lock:
        if _client is None:
            kwargs: dict[str, Any] = {}
            if _config.model is not None:
                kwargs["model"] = _config.model
            if _config.timeout is not None:
                kwargs["timeout"] = _config.timeout
            _client = TypeSafeClient(**kwargs)
        return _client


def _model_name() -> str:
    """The model this process asks for, used as part of the cache key."""
    return _config.model or os.environ.get("TYPESAFE_DEFAULT_MODEL") or DEFAULT_MODEL


def _truthy(value: str) -> bool:
    return value.strip().lower() not in ("0", "false", "no", "off", "")


def _get_cache() -> Cache | None:
    """The cache handle, or None when caching is off."""
    global _cache
    setting = _config.cache
    if setting is False:
        return None
    if setting is None and not _truthy(os.environ.get("SIF_CACHE", "1")):
        return None
    with _lock:
        if _cache is None:
            path = setting if isinstance(setting, (str, Path)) else None
            _cache = Cache(path) if path else Cache()
        return _cache


def _get_log() -> CallLog | None:
    """The log handle, or None when logging is off."""
    global _call_log
    setting = _config.log
    if setting is False:
        return None
    if setting is None and not _truthy(os.environ.get("SIF_LOG", "1")):
        return None
    with _lock:
        if _call_log is None:
            path = setting if isinstance(setting, (str, Path)) else None
            _call_log = CallLog(path) if path else CallLog()
        return _call_log


# --------------------------------------------------------------- question helpers


def options(choices: Sequence[str] | Mapping[str, str | None], instructions: str | None = None) -> Choice:
    """Build a Choice question from a list of names or a name -> description map."""
    return Choice(instructions=instructions or DEFAULT_SWITCH_INSTRUCTIONS, criteria=_criteria(choices))


def scale(levels: Sequence[str], instructions: str) -> Score:
    """Build a Score question from ordered levels, lowest first."""
    levels = list(levels)
    if len(levels) < 2:
        raise ValueError("score needs at least two levels")
    return Score(instructions=instructions, criteria=levels)


def _criteria(choices: Sequence[str] | Mapping[str, str | None]) -> dict[str, Any]:
    """Normalize switch options to the criteria mapping the API wants."""
    if isinstance(choices, Mapping):
        criteria = dict(choices)
    else:
        criteria = {str(choice): None for choice in choices}
    if len(criteria) < 2:
        raise ValueError("switch needs at least two options")
    return criteria


def _as_question(value: Any) -> Noul | Choice | Score:
    """Accept SDK question objects, or a bare string as a Noul."""
    if isinstance(value, (Noul, Choice, Score)):
        return value
    if isinstance(value, str):
        return Noul(instructions=value)
    raise TypeError(
        f"question must be a str, Noul, Choice or Score; got {type(value).__name__}. "
        "Use sif.options(...) for a choice and sif.scale(...) for a score."
    )


def _question_payload(question: Noul | Choice | Score) -> dict[str, Any]:
    """Stable, JSON-safe view of a question for the cache key and the log."""
    if isinstance(question, Noul):
        return {"type": "noul", "instructions": question.instructions, "criteria": question.criteria}
    if isinstance(question, Choice):
        return {"type": "choice", "instructions": question.instructions, "criteria": dict(question.criteria)}
    return {"type": "score", "instructions": question.instructions, "criteria": list(question.criteria)}


# ------------------------------------------------------------------ raw <-> answer


def _int_keys(mapping: Mapping[Any, Any]) -> dict[Any, Any]:
    """JSON turns the int keys of a score answer into strings; turn them back."""
    out: dict[Any, Any] = {}
    for key, value in mapping.items():
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            out[key] = value
    return out


def _answer_to_raw(answer: Answer) -> dict[str, Any]:
    """Serialize an answer object the way the wire format spells it."""
    if isinstance(answer, NoulAnswer):
        return {"type": "noul", "noul": answer.noul}
    if isinstance(answer, ChoiceAnswer):
        return {
            "type": "choice",
            "choice": answer.choice,
            "confidence": answer.confidence,
            "probabilities": dict(answer.probabilities),
        }
    if isinstance(answer, ScoreAnswer):
        return {
            "type": "score",
            "score": answer.score,
            "confidence": answer.confidence,
            "legend": {str(k): v for k, v in answer.legend.items()},
            "probabilities": {str(k): v for k, v in answer.probabilities.items()},
        }
    raise TypeError(f"unknown answer type {type(answer).__name__}")


def _answer_from_raw(raw: Mapping[str, Any]) -> Answer:
    """Rebuild an answer object from a cached raw payload."""
    kind = raw.get("type")
    if kind == "noul":
        return NoulAnswer(noul=raw["noul"])
    if kind == "choice":
        return ChoiceAnswer(
            choice=raw["choice"],
            confidence=raw["confidence"],
            probabilities=dict(raw.get("probabilities") or {}),
        )
    if kind == "score":
        return ScoreAnswer(
            score=raw["score"],
            confidence=raw["confidence"],
            legend=_int_keys(raw.get("legend") or {}),
            probabilities=_int_keys(raw.get("probabilities") or {}),
        )
    raise ValueError(f"unknown answer type {kind!r} in cached payload")


def _raw_answers(response: Any, answers: Mapping[str, Answer]) -> dict[str, Any]:
    """Prefer the untouched HTTP payload; fall back to re-serializing."""
    try:
        body = response.raw_http_response.json()
        raw = body.get("answers")
        if isinstance(raw, dict) and raw:
            return raw
    except Exception:  # noqa: BLE001 - the raw body is a nicety, never required
        pass
    return {name: _answer_to_raw(answer) for name, answer in answers.items()}


# -------------------------------------------------------------------------- engine


def _run(state: State, questions: Mapping[str, Noul | Choice | Score]) -> dict[str, Answer]:
    """One request: cache lookup, then the API. Raises TypeSafeError on failure."""
    payload = {name: _question_payload(question) for name, question in questions.items()}
    model = _model_name()
    cache = _get_cache()
    call_log = _get_log()
    key = make_key(model, state, payload) if cache is not None else None

    started = time.perf_counter()
    if cache is not None and key is not None:
        hit = cache.get(key)
        if hit is not None:
            raw_hit, answered_by = hit
            answers = {name: _answer_from_raw(raw) for name, raw in raw_hit.items()}
            if call_log is not None:
                call_log.write(
                    model=model,
                    model_resolved=answered_by,
                    state_hash=state_hash(state),
                    questions=payload,
                    answers=raw_hit,
                    usage=None,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    cached=True,
                )
            return answers

    client = _get_client()
    started = time.perf_counter()
    try:
        response = client.system_one(state=state, questions=dict(questions))
    except TypeSafeError as error:
        if call_log is not None:
            call_log.write(
                model=model,
                state_hash=state_hash(state),
                questions=payload,
                answers={},
                usage=None,
                latency_ms=(time.perf_counter() - started) * 1000,
                cached=False,
                error=f"{type(error).__name__}: {error}",
            )
        raise
    latency_ms = (time.perf_counter() - started) * 1000

    answers = dict(response.answers)
    raw = _raw_answers(response, answers)
    usage = getattr(response, "usage", None)
    usage_dict = (
        {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
        if usage is not None
        else None
    )
    resolved = getattr(response, "model", None) or model
    if cache is not None and key is not None:
        cache.set(key, resolved, raw, time.time())
    if call_log is not None:
        call_log.write(
            model=model,
            model_resolved=resolved,
            state_hash=state_hash(state),
            questions=payload,
            answers=raw,
            usage=usage_dict,
            latency_ms=latency_ms,
            cached=False,
        )
    return answers


def _one(state: State, question: Noul | Choice | Score, extract: Any, default: Any) -> Any:
    """Run a single question, falling back to `default` when the API fails.

    Configuration errors (see `_is_fatal`) are raised even when a default is set.
    """
    try:
        answers = _run(state, {_KEY: question})
    except TypeSafeError as error:
        if default is None or _is_fatal(error):
            raise
        logger.warning("sif: %s: %s - falling back to %r", type(error).__name__, error, default)
        return default
    return extract(answers[_KEY])


# ---------------------------------------------------------------------- public API


def check(
    state: State,
    question: str,
    *,
    criteria: dict[str, Any] | None = None,
    default: float | None = None,
) -> float:
    """Probability from 0 to 1 that `question` holds of `state`."""
    return _one(state, Noul(instructions=question, criteria=criteria), lambda a: a.noul, default)


def true(
    state: State,
    question: str,
    *,
    threshold: float = 0.5,
    criteria: dict[str, Any] | None = None,
    default: bool | None = None,
) -> bool:
    """True when `check(...)` clears `threshold`."""
    fallback = None if default is None else float(default)
    probability = check(state, question, criteria=criteria, default=fallback)
    return probability >= threshold


def decide(
    state: State,
    choices: Sequence[str] | Mapping[str, str | None],
    instructions: str | None = None,
    *,
    default: str | None = None,
) -> Decision:
    """Pick one option and keep the probabilities and confidence."""
    question = options(choices, instructions)

    def extract(answer: ChoiceAnswer) -> Decision:
        return Decision(
            choice=answer.choice,
            probabilities=dict(answer.probabilities),
            confidence=answer.confidence,
        )

    fallback = None if default is None else Decision(choice=default, probabilities={}, confidence=0.0)
    return _one(state, question, extract, fallback)


def switch(
    state: State,
    choices: Sequence[str] | Mapping[str, str | None],
    instructions: str | None = None,
    *,
    default: str | None = None,
) -> str:
    """The option that best fits `state`."""
    return decide(state, choices, instructions, default=default).choice


def score(
    state: State,
    levels: Sequence[str],
    instructions: str,
    *,
    default: float | None = None,
) -> float:
    """Position of `state` on the ordered `levels`, as a float index."""
    return _one(state, scale(levels, instructions), lambda a: a.score, default)


def ask(state: State, **questions: Any) -> dict[str, Answer]:
    """Ask several questions in one request; returns the raw answer objects.

    Values may be SDK ``Noul``/``Choice``/``Score`` objects, a bare string
    (read as a Noul), or ``sif.options(...)`` / ``sif.scale(...)``.
    """
    if not questions:
        raise ValueError("ask needs at least one question")
    return _run(state, {name: _as_question(value) for name, value in questions.items()})


@dataclass(frozen=True)
class Decision:
    """A `switch` result with the numbers behind it."""

    choice: str
    probabilities: dict[str, float]
    confidence: float

    def __str__(self) -> str:
        return self.choice
