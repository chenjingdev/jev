"""Korean toxicity guardrail on top of Jev, in the shape of TUNiB's Safety Check.

TUNiB's public description of TUNiBridge Safety Check is "12 categories of
toxicity, 4 levels of severity, with probabilities". Their category list is not
public, so the twelve below are our own. The shape is what we copy:

- one probability per category (multi-label: a sentence can be 욕설 and 성희롱)
- one severity level on an ordered 4-step scale
- everything in a single `sif.ask()` request, so 13 questions go out together
  and are answered in parallel without seeing each other

Categories are Nouls rather than a single Choice on purpose. A Choice makes the
categories compete and forces one winner; a toxicity detector needs each
category judged on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import sif

#: Category id -> (Korean name, Noul instruction). The instruction is the
#: proposition Jev scores; it is written so a harmless sentence reads as false.
CATEGORIES: dict[str, tuple[str, str]] = {
    "profanity": ("욕설", "이 문장은 욕설이나 비속어를 담고 있다 (초성·변형·우회 표기 포함)"),
    "insult": ("모욕", "이 문장은 특정 사람을 깎아내리거나 조롱·비하한다"),
    "hate": ("혐오·차별", "이 문장은 성별·인종·지역·장애·성적 지향·나이·종교 등 집단 속성을 이유로 혐오하거나 차별한다"),
    "sexual": ("성희롱·성적", "이 문장은 성희롱이거나 노골적인 성적 표현을 담고 있다"),
    "violence": ("폭력·위협", "이 문장은 신체적 폭력을 묘사·찬양하거나 누군가를 위협한다"),
    "self_harm": ("자해·자살", "이 문장은 자해나 자살을 언급·조장하거나 그 방법을 다룬다"),
    "crime": ("범죄 조장", "이 문장은 범죄(사기·해킹·절도·불법 거래 등)를 부추기거나 그 방법을 알려준다"),
    "drugs": ("약물", "이 문장은 마약·불법 약물의 사용이나 구입을 언급하거나 조장한다"),
    "privacy": ("개인정보", "이 문장은 전화번호·주소·주민번호·계좌 등 특정 개인의 개인정보를 노출한다"),
    "politics": ("정치 편향", "이 문장은 특정 정당·정치인·정치 진영을 노골적으로 지지하거나 공격한다"),
    "religion": ("종교 편향", "이 문장은 특정 종교를 비하하거나 강요·선동한다"),
    "spam": ("스팸·광고", "이 문장은 광고·홍보·도박 사이트 유도 같은 스팸이다"),
}

#: Ordered severity levels, lowest first. The Score index is the level.
SEVERITY: tuple[str, ...] = ("안전", "주의", "유해", "심각")

SEVERITY_INSTRUCTIONS = (
    "이 문장을 챗봇 대화에서 그대로 노출했을 때 유해한 정도. "
    "안전: 문제 없음. 주의: 거칠지만 허용 범위. 유해: 노출하면 안 됨. 심각: 실제 피해나 범죄로 이어질 수 있음."
)

#: A category counts as detected at or above this probability.
DEFAULT_THRESHOLD = 0.5


@dataclass(frozen=True)
class Verdict:
    """One sentence's screening result."""

    text: str
    probabilities: dict[str, float]  # category id -> P(category applies)
    severity: float  # position on SEVERITY, 0.0 ~ 3.0
    severity_confidence: float
    threshold: float

    @property
    def categories(self) -> list[str]:
        """Category ids at or above the threshold, most probable first."""
        hits = [(p, c) for c, p in self.probabilities.items() if p >= self.threshold]
        return [c for _, c in sorted(hits, reverse=True)]

    @property
    def labels(self) -> list[str]:
        """Korean names of the detected categories."""
        return [CATEGORIES[c][0] for c in self.categories]

    @property
    def level(self) -> int:
        """Severity rounded to the nearest level index."""
        return max(0, min(len(SEVERITY) - 1, round(self.severity)))

    @property
    def severity_label(self) -> str:
        return SEVERITY[self.level]

    @property
    def safe(self) -> bool:
        """No category detected and severity rounds to 안전.

        Severity alone can make a sentence unsafe: a verdict with no category and
        level 주의 is possible, and it is reported as such rather than hidden.
        """
        return not self.categories and self.level == 0

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "safe": self.safe,
            "categories": self.labels,
            "severity": self.severity_label,
            "severity_score": self.severity,
            "severity_confidence": self.severity_confidence,
            "probabilities": {CATEGORIES[c][0]: p for c, p in self.probabilities.items()},
        }


def _questions() -> dict:
    questions = {cid: sif.Noul(instructions=text) for cid, (_, text) in CATEGORIES.items()}
    questions["severity"] = sif.scale(SEVERITY, SEVERITY_INSTRUCTIONS)
    return questions


def screen(text: str, *, threshold: float = DEFAULT_THRESHOLD) -> Verdict:
    """Screen one sentence: 12 category probabilities + severity, one request."""
    answers: Mapping = sif.ask(text, **_questions())
    severity = answers["severity"]
    return Verdict(
        text=text,
        probabilities={cid: answers[cid].noul for cid in CATEGORIES},
        severity=severity.score,
        severity_confidence=severity.confidence,
        threshold=threshold,
    )
