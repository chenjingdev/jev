"""Unit tests: the client is replaced by a fake, so no API key is needed."""

from __future__ import annotations

import json

import httpx2
import pytest
from typesafe_sdk import (
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    TypeSafeAPIConnectionError,
    TypeSafeAPITimeoutError,
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeError,
    TypeSafeInternalServerError,
    TypeSafeRateLimitError,
    TypeSafeUnprocessableEntityError,
)

import sif
from sif import core


def rate_limited() -> TypeSafeRateLimitError:
    """A real 429 the way the SDK raises it."""
    return TypeSafeRateLimitError(429, {"error": "rate limited"}, httpx2.Headers(), "slow down")


def timed_out() -> TypeSafeAPITimeoutError:
    """A real timeout the way the SDK raises it."""
    return TypeSafeAPITimeoutError(10.0)


def no_api_key() -> TypeSafeError:
    """What the SDK raises when TYPESAFE_API_KEY is unset: the bare base class."""
    return TypeSafeError(
        "No API key was provided. Pass api_key or set the TYPESAFE_API_KEY environment variable."
    )


class FakeUsage:
    def __init__(self, input_tokens: int = 123, output_tokens: int | None = None) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    """Stands in for SystemOneResponse; no raw HTTP body attached."""

    def __init__(self, answers: dict[str, object], model: str = "jev-latest") -> None:
        self.answers = answers
        self.model = model
        self.usage = FakeUsage()

    @property
    def raw_http_response(self):
        raise RuntimeError("no raw response in tests")


class FakeClient:
    """Records every call and replays a scripted answer or exception."""

    def __init__(self, script) -> None:
        self.script = script
        self.calls: list[tuple[object, dict]] = []

    def system_one(self, *, state, questions, **kwargs):
        self.calls.append((state, questions))
        result = self.script(state, questions) if callable(self.script) else self.script
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        pass


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    """Point the cache and log at tmp_path and forget the singletons."""
    monkeypatch.delenv("SIF_CACHE", raising=False)
    monkeypatch.delenv("SIF_LOG", raising=False)
    core.reset()
    core._config.model = None
    core._config.timeout = None
    core._config.cache = str(tmp_path / "cache.sqlite")
    core._config.log = str(tmp_path / "calls.jsonl")
    yield tmp_path
    core.reset()
    core._config.cache = None
    core._config.log = None


def install(monkeypatch, script) -> FakeClient:
    """Replace the module-wide client with a fake."""
    client = FakeClient(script)
    monkeypatch.setattr(core, "_get_client", lambda: client)
    return client


def log_lines(tmp_path) -> list[dict]:
    path = tmp_path / "calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ return values


def test_check_returns_noul_probability(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.87)}))
    assert sif.check("배송이 너무 늦어요", "The customer is upset") == 0.87
    assert len(client.calls) == 1
    state, questions = client.calls[0]
    assert state == "배송이 너무 늦어요"
    assert isinstance(questions["answer"], Noul)
    assert questions["answer"].instructions == "The customer is upset"


def test_check_passes_criteria(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.1)}))
    sif.check("x", "urgent?", criteria={"true": "needs action now", "false": "can wait"})
    _, questions = client.calls[0]
    assert questions["answer"].criteria == {"true": "needs action now", "false": "can wait"}


def test_true_applies_threshold(isolate, monkeypatch):
    install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.6)}))
    assert sif.true("x", "q") is True
    assert sif.true("x", "q", threshold=0.9) is False


def test_switch_returns_choice_and_normalizes_a_list(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse(
        {"answer": ChoiceAnswer(choice="refund", confidence=0.9, probabilities={"refund": 0.9, "praise": 0.1})}
    ))
    assert sif.switch("환불해주세요", ["refund", "praise"]) == "refund"
    _, questions = client.calls[0]
    assert isinstance(questions["answer"], Choice)
    assert questions["answer"].criteria == {"refund": None, "praise": None}
    assert questions["answer"].instructions == core.DEFAULT_SWITCH_INSTRUCTIONS


def test_switch_keeps_a_dict_of_descriptions(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse(
        {"answer": ChoiceAnswer(choice="billing", confidence=0.8, probabilities={"billing": 0.8, "tech": 0.2})}
    ))
    sif.switch("x", {"billing": "Payment issues", "tech": None}, "Which team")
    _, questions = client.calls[0]
    assert questions["answer"].criteria == {"billing": "Payment issues", "tech": None}
    assert questions["answer"].instructions == "Which team"


def test_decide_exposes_probabilities_and_confidence(isolate, monkeypatch):
    install(monkeypatch, FakeResponse(
        {"answer": ChoiceAnswer(choice="a", confidence=0.77, probabilities={"a": 0.7, "b": 0.3})}
    ))
    decision = sif.decide("x", ["a", "b"])
    assert decision.choice == "a"
    assert decision.confidence == 0.77
    assert decision.probabilities == {"a": 0.7, "b": 0.3}
    assert str(decision) == "a"


def test_score_returns_the_float(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse(
        {"answer": ScoreAnswer(score=1.035, confidence=0.6, legend={0: "Calm"}, probabilities={0: 0.3, 1: 0.7})}
    ))
    assert sif.score("x", ["Calm", "Annoyed", "Furious"], "How angry") == 1.035
    _, questions = client.calls[0]
    assert isinstance(questions["answer"], Score)
    assert list(questions["answer"].criteria) == ["Calm", "Annoyed", "Furious"]


def test_score_rejects_one_level(isolate, monkeypatch):
    install(monkeypatch, FakeResponse({}))
    with pytest.raises(ValueError):
        sif.score("x", ["only"], "How angry")


def test_switch_rejects_one_option(isolate, monkeypatch):
    install(monkeypatch, FakeResponse({}))
    with pytest.raises(ValueError):
        sif.switch("x", ["only"])


def test_ask_bundles_questions_into_one_request(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({
        "urgent": NoulAnswer(noul=0.95),
        "topic": ChoiceAnswer(choice="refund", confidence=0.8, probabilities={"refund": 0.8, "praise": 0.2}),
        "anger": ScoreAnswer(score=1.5, confidence=0.5, legend={0: "Calm"}, probabilities={0: 0.2, 1: 0.8}),
    }))
    answers = sif.ask(
        "지금 당장 환불해주세요",
        urgent="The message is urgent",
        topic=sif.options(["refund", "praise"]),
        anger=sif.scale(["Calm", "Annoyed", "Furious"], "How angry"),
    )
    assert len(client.calls) == 1, "all questions go out in a single request"
    _, questions = client.calls[0]
    assert set(questions) == {"urgent", "topic", "anger"}
    assert isinstance(questions["urgent"], Noul)
    assert answers["urgent"].noul == 0.95
    assert answers["topic"].choice == "refund"
    assert answers["anger"].score == 1.5


def test_ask_rejects_an_unusable_question(isolate, monkeypatch):
    install(monkeypatch, FakeResponse({}))
    with pytest.raises(TypeError):
        sif.ask("x", bad=123)


def test_ask_needs_a_question(isolate, monkeypatch):
    install(monkeypatch, FakeResponse({}))
    with pytest.raises(ValueError):
        sif.ask("x")


# ------------------------------------------------------------------------- cache


def test_cache_hit_does_not_call_the_client(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.42)}))
    assert sif.check("같은 문장", "q") == 0.42
    assert len(client.calls) == 1
    assert sif.check("같은 문장", "q") == 0.42
    assert len(client.calls) == 1, "second call must be served from the cache"
    records = log_lines(isolate)
    assert [r["cached"] for r in records] == [False, True]
    assert records[0]["usage"] == {"input_tokens": 123, "output_tokens": None}
    assert records[1]["usage"] is None


def test_cache_rebuilds_every_answer_type_faithfully(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({
        "urgent": NoulAnswer(noul=0.95),
        "topic": ChoiceAnswer(choice="refund", confidence=0.8, probabilities={"refund": 0.8, "praise": 0.2}),
        "anger": ScoreAnswer(score=1.5, confidence=0.5, legend={0: "Calm", 1: "Mad"}, probabilities={0: 0.2, 1: 0.8}),
    }))
    kwargs = dict(
        urgent="The message is urgent",
        topic=sif.options(["refund", "praise"]),
        anger=sif.scale(["Calm", "Mad"], "How angry"),
    )
    fresh = sif.ask("문의", **kwargs)
    cached = sif.ask("문의", **kwargs)
    assert len(client.calls) == 1
    assert cached["urgent"].noul == fresh["urgent"].noul
    assert cached["topic"].probabilities == fresh["topic"].probabilities
    assert cached["anger"].score == fresh["anger"].score
    assert cached["anger"].probabilities == {0: 0.2, 1: 0.8}, "int keys survive the JSON round trip"
    assert cached["anger"].legend == {0: "Calm", 1: "Mad"}


def test_a_different_state_misses_the_cache(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check("첫 번째", "q")
    sif.check("두 번째", "q")
    assert len(client.calls) == 2


def test_a_different_question_misses_the_cache(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check("같은 문장", "첫 질문")
    sif.check("같은 문장", "둘째 질문")
    assert len(client.calls) == 2


def test_cache_off_by_env(isolate, monkeypatch):
    core.reset()
    core._config.cache = None
    monkeypatch.setenv("SIF_CACHE", "0")
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check("x", "q")
    sif.check("x", "q")
    assert len(client.calls) == 2


def test_cache_off_by_configure(isolate, monkeypatch):
    sif.configure(cache=False)
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check("x", "q")
    sif.check("x", "q")
    assert len(client.calls) == 2


def test_dict_and_list_state_are_accepted(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check({"subject": "환불", "body": "늦어요"}, "q")
    sif.check(["첫 줄", "둘째 줄"], "q")
    assert client.calls[0][0] == {"subject": "환불", "body": "늦어요"}
    assert client.calls[1][0] == ["첫 줄", "둘째 줄"]


# ---------------------------------------------------------------------- fallback


def test_default_is_returned_when_the_api_fails(isolate, monkeypatch):
    install(monkeypatch, timed_out())
    assert sif.check("x", "q", default=0.0) == 0.0
    assert sif.true("x", "q", default=False) is False
    assert sif.true("x", "q", default=True) is True
    assert sif.switch("x", ["a", "b"], default="a") == "a"
    assert sif.score("x", ["lo", "hi"], "how", default=1.0) == 1.0


def test_default_decision_keeps_the_shape(isolate, monkeypatch):
    install(monkeypatch, rate_limited())
    decision = sif.decide("x", ["a", "b"], default="b")
    assert decision.choice == "b"
    assert decision.probabilities == {}
    assert decision.confidence == 0.0


def test_without_a_default_the_error_propagates(isolate, monkeypatch):
    install(monkeypatch, rate_limited())
    with pytest.raises(TypeSafeRateLimitError):
        sif.check("x", "q")
    with pytest.raises(TypeSafeRateLimitError):
        sif.switch("x", ["a", "b"])
    with pytest.raises(TypeSafeRateLimitError):
        sif.score("x", ["lo", "hi"], "how")


def test_a_missing_api_key_raises_even_with_a_default(isolate, monkeypatch):
    """A broken key is a configuration error; a default would only hide it."""
    install(monkeypatch, no_api_key())
    with pytest.raises(TypeSafeError, match="No API key"):
        sif.check("x", "q", default=0.0)
    with pytest.raises(TypeSafeError, match="No API key"):
        sif.true("x", "q", default=False)
    with pytest.raises(TypeSafeError, match="No API key"):
        sif.switch("x", ["a", "b"], default="a")
    with pytest.raises(TypeSafeError, match="No API key"):
        sif.score("x", ["lo", "hi"], "how", default=1.0)
    with pytest.raises(TypeSafeError, match="No API key"):
        sif.decide("x", ["a", "b"], default="a")


def test_a_missing_key_raises_from_client_construction_too(isolate, monkeypatch):
    """The real failure path: the client itself refuses to be built."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    core.reset()
    with pytest.raises(TypeSafeError, match="No API key"):
        sif.check("키 없는 상태", "q", default=0.0)


@pytest.mark.parametrize(
    "error",
    [
        TypeSafeAuthenticationError(401, {"error": "bad key"}, httpx2.Headers()),
        TypeSafeBadRequestError(400, {"error": "bad request"}, httpx2.Headers()),
        TypeSafeUnprocessableEntityError(422, {"error": "unprocessable"}, httpx2.Headers()),
    ],
    ids=["401", "400", "422"],
)
def test_configuration_errors_ignore_the_default(isolate, monkeypatch, error):
    install(monkeypatch, error)
    with pytest.raises(type(error)):
        sif.check("x", "q", default=0.0)


@pytest.mark.parametrize(
    "error",
    [
        TypeSafeAPITimeoutError(10.0),
        TypeSafeRateLimitError(429, {"error": "slow down"}, httpx2.Headers()),
        TypeSafeInternalServerError(529, {"error": "overloaded"}, httpx2.Headers()),
        TypeSafeAPIConnectionError("connection reset"),
    ],
    ids=["timeout", "429", "529", "connection"],
)
def test_transient_errors_use_the_default(isolate, monkeypatch, error):
    install(monkeypatch, error)
    assert sif.check("x", "q", default=0.25) == 0.25


def test_ask_always_propagates(isolate, monkeypatch):
    install(monkeypatch, timed_out())
    with pytest.raises(TypeSafeAPITimeoutError):
        sif.ask("x", urgent="is it urgent")


def test_a_failure_does_not_poison_the_cache(isolate, monkeypatch):
    install(monkeypatch, timed_out())
    assert sif.check("x", "q", default=0.25) == 0.25
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.9)}))
    assert sif.check("x", "q", default=0.25) == 0.9
    assert len(client.calls) == 1


def test_failures_are_logged_with_the_error(isolate, monkeypatch):
    install(monkeypatch, timed_out())
    sif.check("x", "q", default=0.0)
    records = log_lines(isolate)
    assert len(records) == 1
    assert records[0]["cached"] is False
    assert "TypeSafeAPITimeoutError" in records[0]["error"]


# --------------------------------------------------------------------------- log


def test_log_keeps_raw_probabilities_and_latency(isolate, monkeypatch):
    install(monkeypatch, FakeResponse(
        {"answer": ChoiceAnswer(choice="a", confidence=0.7, probabilities={"a": 0.7, "b": 0.3})}
    ))
    sif.switch("x", ["a", "b"])
    record = log_lines(isolate)[0]
    assert record["answers"]["answer"]["probabilities"] == {"a": 0.7, "b": 0.3}
    assert record["answers"]["answer"]["confidence"] == 0.7
    assert record["questions"]["answer"]["type"] == "choice"
    assert isinstance(record["latency_ms"], (int, float))
    assert len(record["state_hash"]) == 64
    assert record["model"] == "jev-latest"


def test_log_off_by_configure(isolate, monkeypatch):
    sif.configure(log=False)
    install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check("x", "q")
    assert log_lines(isolate) == []


def test_configure_model_changes_the_cache_key(isolate, monkeypatch):
    client = install(monkeypatch, FakeResponse({"answer": NoulAnswer(noul=0.5)}))
    sif.check("x", "q")
    sif.configure(model="jev")
    install(monkeypatch, client)
    monkeypatch.setattr(core, "_get_client", lambda: client)
    sif.check("x", "q")
    assert len(client.calls) == 2
    assert log_lines(isolate)[-1]["model"] == "jev-latest"
