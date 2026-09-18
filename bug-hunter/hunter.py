"""Bug hunter on top of Jev: feed it functions, get back the ones worth a close look.

Jev is a System One model. It cannot run or trace code, so the questions are not
"does this crash" but "is this pattern visible in the source" - propositions a
reviewer could tick off by reading. Every proposition is worded so a clean
function reads as false.

Per function, one `sif.ask()` request carrying:

- one Noul per smell (multi-label: a function can swallow an exception and be
  off by one at the same time), scored independently
- one Score on 무해 → 사소 → 심각 → 치명 for how bad the worst problem is
- one Choice for the single most likely bug kind, used only for the label

The `ask()` questions are answered in parallel and never see each other, so the
Choice can name a kind whose Noul stayed low. The ranking uses the Nouls.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import sif

#: Smell id -> (Korean name, Noul instruction). Each is a pattern visible in the
#: source without running it.
SMELLS: dict[str, tuple[str, str]] = {
    "none_unchecked": (
        "None 미검사",
        "이 함수는 None일 수 있는 값(Optional 인자, dict.get, re.match, find 결과 등)을 검사 없이 속성 접근·인덱싱·연산에 쓴다",
    ),
    "boundary": (
        "경계 미처리",
        "이 함수는 빈 입력, 길이 0, 마지막 인덱스, 음수 같은 경계 입력에서 잘못된 결과를 내거나 예외를 낸다",
    ),
    "off_by_one": (
        "오프바이원",
        "이 함수의 range·슬라이스·비교 연산자(<, <=)에 하나 어긋난 경계가 있어 원소 하나를 빠뜨리거나 하나 더 본다",
    ),
    "swallowed_exception": (
        "예외 삼킴",
        "이 함수는 except 절에서 예외를 잡은 뒤 로그·재발생·의미 있는 처리 없이 무시하거나 잘못된 기본값을 돌려준다",
    ),
    "resource_leak": (
        "자원 누수",
        "이 함수는 파일·소켓·커서·락 같은 자원을 열고 나서 예외나 조기 반환 경로에서 닫지 않는다",
    ),
    "mutable_default": (
        "가변 기본값",
        "이 함수는 list·dict·set 같은 가변 객체를 기본 인자로 쓰거나, 호출 사이에 공유되는 상태를 변경한다",
    ),
    "wrong_return": (
        "반환 불일치",
        "이 함수는 어떤 분기에서 반환을 빠뜨리거나(None 반환), 다른 분기와 타입·의미가 다른 값을 돌려준다",
    ),
    "logic": (
        "논리 오류",
        "이 함수의 조건식·연산자·변수 이름이 의도와 어긋난다 (and/or 혼동, 잘못된 변수 참조, 반전된 비교, 덮어써진 결과)",
    ),
    "type_mismatch": (
        "타입 혼동",
        "이 함수는 str과 bytes, int와 str, float 동등 비교, 리스트와 단일 값처럼 타입이 맞지 않는 값을 섞어 쓴다",
    ),
    "unsafe_input": (
        "입력 신뢰",
        "이 함수는 외부 입력(경로, SQL, 쉘 명령, HTML, eval 대상)을 검증이나 이스케이프 없이 그대로 쓴다",
    ),
}

#: Ordered severity levels, lowest first. The Score index is the level.
SEVERITY: tuple[str, ...] = ("무해", "사소", "심각", "치명")

SEVERITY_INSTRUCTIONS = (
    "이 함수에서 가장 나쁜 문제가 실제 실행에서 미치는 영향. "
    "무해: 버그 없음. 사소: 드문 입력에서만 틀리거나 스타일 문제. "
    "심각: 흔한 입력에서 잘못된 결과나 예외. 치명: 데이터 손상, 보안 구멍, 무한 루프."
)

#: Choice options for the single most likely bug kind.
KINDS: dict[str, str] = {
    "none": "버그가 보이지 않음",
    **{smell: name for smell, (name, _) in SMELLS.items()},
}
KIND_INSTRUCTIONS = "이 함수에서 가장 가능성이 높은 버그 종류 하나"

#: A smell counts as detected at or above this probability.
DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class Function:
    """One function's source, with where it came from."""

    file: str
    name: str
    lineno: int
    source: str
    language: str = "python"

    @property
    def location(self) -> str:
        return f"{self.file}:{self.lineno}"

    def as_state(self) -> dict:
        """The state Jev sees. A mapping, so the model knows which part is code."""
        return {
            "language": self.language,
            "file": self.file,
            "function": self.name,
            "source": self.source,
        }


@dataclass(frozen=True)
class Verdict:
    """One function's screening result."""

    function: Function
    probabilities: dict[str, float]  # smell id -> P(smell present)
    severity: float  # position on SEVERITY, 0.0 ~ 3.0
    severity_confidence: float
    kind: str  # most likely bug kind (KINDS key)
    kind_confidence: float
    threshold: float

    @property
    def risk(self) -> float:
        """The ranking key: the strongest smell. Severity breaks ties."""
        return max(self.probabilities.values())

    @property
    def smells(self) -> list[str]:
        """Smell ids at or above the threshold, most probable first."""
        hits = [(p, s) for s, p in self.probabilities.items() if p >= self.threshold]
        return [s for _, s in sorted(hits, reverse=True)]

    @property
    def labels(self) -> list[str]:
        return [SMELLS[s][0] for s in self.smells]

    @property
    def level(self) -> int:
        """Severity rounded to the nearest level index."""
        return max(0, min(len(SEVERITY) - 1, round(self.severity)))

    @property
    def severity_label(self) -> str:
        return SEVERITY[self.level]

    @property
    def sort_key(self) -> tuple[float, float]:
        return (self.risk, self.severity)

    def as_dict(self) -> dict:
        return {
            "file": self.function.file,
            "function": self.function.name,
            "lineno": self.function.lineno,
            "risk": self.risk,
            "smells": self.smells,
            "labels": self.labels,
            "severity": self.severity_label,
            "severity_score": self.severity,
            "severity_confidence": self.severity_confidence,
            "kind": self.kind,
            "kind_label": KINDS[self.kind],
            "kind_confidence": self.kind_confidence,
            "probabilities": self.probabilities,
        }


# ------------------------------------------------------------------ extraction


def extract_functions(source: str, file: str, *, language: str = "python") -> list[Function]:
    """Every def/async def in a Python source, methods included, outermost first.

    Nested functions are returned as their own entries as well as inside their
    parent; Jev sees the parent whole, so the inner copy is what gets its own row.
    """
    tree = ast.parse(source, filename=file)
    out: list[Function] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment:
            continue
        out.append(Function(file=file, name=node.name, lineno=node.lineno, source=segment, language=language))
    out.sort(key=lambda f: f.lineno)
    return out


def load_functions(paths: Iterable[str | Path]) -> list[Function]:
    """Functions from Python files, or every .py under a directory."""
    out: list[Function] = []
    for raw in paths:
        path = Path(raw)
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in files:
            if any(part in {".venv", "__pycache__", "node_modules", ".git"} for part in file.parts):
                continue
            text = file.read_text(encoding="utf-8")
            out.extend(extract_functions(text, str(file)))
    return out


# ------------------------------------------------------------------- judgement


def _questions() -> dict:
    questions = {smell: sif.Noul(instructions=text) for smell, (_, text) in SMELLS.items()}
    questions["severity"] = sif.scale(SEVERITY, SEVERITY_INSTRUCTIONS)
    questions["kind"] = sif.options(KINDS, KIND_INSTRUCTIONS)
    return questions


def judge(function: Function, *, threshold: float = DEFAULT_THRESHOLD) -> Verdict:
    """Screen one function: smell probabilities + severity + kind, one request."""
    answers: Mapping = sif.ask(function.as_state(), **_questions())
    severity = answers["severity"]
    kind = answers["kind"]
    return Verdict(
        function=function,
        probabilities={smell: answers[smell].noul for smell in SMELLS},
        severity=severity.score,
        severity_confidence=severity.confidence,
        kind=kind.choice,
        kind_confidence=kind.confidence,
        threshold=threshold,
    )


def hunt(functions: Iterable[Function], *, threshold: float = DEFAULT_THRESHOLD) -> list[Verdict]:
    """Judge every function and return them riskiest first."""
    verdicts = [judge(f, threshold=threshold) for f in functions]
    verdicts.sort(key=lambda v: v.sort_key, reverse=True)
    return verdicts
