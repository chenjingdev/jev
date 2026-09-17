"""sif - semantic if.

Jev judgement used like ordinary control flow::

    import sif
    if sif.true(message, "The customer is angry"):
        route = sif.switch(message, ["refund", "shipping", "praise"])
"""

from typesafe_sdk import Answer, Choice, ChoiceAnswer, Noul, NoulAnswer, Score, ScoreAnswer, TypeSafeError

from .cache import Cache
from .core import (
    Decision,
    ask,
    check,
    configure,
    decide,
    options,
    reset,
    scale,
    score,
    switch,
    true,
)
from .log import CallLog

__version__ = "0.1.0"

__all__ = [
    "Answer",
    "Cache",
    "CallLog",
    "Choice",
    "ChoiceAnswer",
    "Decision",
    "Noul",
    "NoulAnswer",
    "Score",
    "ScoreAnswer",
    "TypeSafeError",
    "__version__",
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
