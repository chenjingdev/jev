"""Jev를 자기회귀 디코더로 쓴다: 한 글자씩 골라 봇의 답장을 조립한다 (v2).

매 스텝 지금까지의 답장을 state로 넣고, 다음 조각을 Choice로 고르고, 고른 것을
답장 끝에 붙여 다시 state로 넣는다. v2는 디코딩 방식과 단위를 인자로 분리한다.

디코딩 (pick):
- argmax: API가 고른 최댓값 라벨.
- sample: 반복 페널티(직전 ×0.3, 직전 3개 안 ×0.6) → temperature 0.8 → top-p 0.9 샘플링.

모드 5개:
- jamo-seq-argmax / jamo-seq-sample: 초성 → 중성 → 종성을 순서대로 세 번 호출
- jamo-par-argmax:                   초성·중성·종성을 한 요청에 세 질문으로 (서로의 답을 못 봄)
- syl-argmax / syl-sample:           빈도 상위 253음절 + space + end 중 하나를 한 번에

실행:
    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python experiments/hangul/run.py
"""

from __future__ import annotations

import collections
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from typesafe_sdk import Choice, TypeSafeClient

HERE = Path(__file__).parent
OUT = HERE / "results.json"
SYL_TABLE = HERE / "syllables_top253.json"

CORPUS_ROOT = Path("/Users/chenjing/dev")
CORPUS_DEPTH = 3
CORPUS_SKIP = {"node_modules", ".venv", ".git"}
TOP_SYLLABLES = 253

SEED = 7
TEMPERATURE = 0.8
TOP_P = 0.9
PENALTY_LAST = 0.3
PENALTY_RECENT = 0.6

# --------------------------------------------------------------------------- 자모표

CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

CHO_NAME = dict(zip(CHO, "기역 쌍기역 니은 디귿 쌍디귿 리을 미음 비읍 쌍비읍 시옷 쌍시옷 이응 지읒 쌍지읒 치읓 키읔 티읕 피읖 히읗".split()))
JUNG_NAME = dict(zip(JUNG, "아 애 야 얘 어 에 여 예 오 와 왜 외 요 우 워 웨 위 유 으 의 이".split()))

SPACE = "space"
END = "end"

SYLLABLES: list[str] = []


def compose(cho: str, jung: str, jong: str = "") -> str:
    return chr(0xAC00 + CHO.index(cho) * 588 + JUNG.index(jung) * 28 + JONG.index(jong))


# --------------------------------------------------------------------------- 음절 빈도표


def build_syllable_table() -> dict:
    """/Users/chenjing/dev 아래 *.md(깊이 3까지)의 완성형 음절을 세어 상위 표를 만든다."""
    counts: collections.Counter[str] = collections.Counter()
    files = 0
    for dirpath, dirnames, filenames in os.walk(CORPUS_ROOT):
        rel = Path(dirpath).relative_to(CORPUS_ROOT)
        depth = 0 if rel == Path(".") else len(rel.parts)
        dirnames[:] = [] if depth >= CORPUS_DEPTH - 1 else [d for d in dirnames if d not in CORPUS_SKIP]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            try:
                text = Path(dirpath, name).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            files += 1
            counts.update(ch for ch in text if "가" <= ch <= "힣")
    top = counts.most_common(TOP_SYLLABLES)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(CORPUS_ROOT),
        "max_depth": CORPUS_DEPTH,
        "files": files,
        "distinct_syllables": len(counts),
        "total_syllables": sum(counts.values()),
        "top": [[s, n] for s, n in top],
    }


def load_syllables() -> list[str]:
    if SYL_TABLE.exists():
        table = json.loads(SYL_TABLE.read_text(encoding="utf-8"))
        print(f"음절표 재사용: {SYL_TABLE.name} ({len(table['top'])}개)", flush=True)
    else:
        table = build_syllable_table()
        SYL_TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"음절표 생성: {SYL_TABLE.name} — md {table['files']}개, 음절 {table['total_syllables']}자, "
              f"고유 {table['distinct_syllables']}종 → 상위 {len(table['top'])}", flush=True)
    print("  상위 30: " + " ".join(f"{s}({n})" for s, n in table["top"][:30]), flush=True)
    return [s for s, _ in table["top"]]


# --------------------------------------------------------------------------- 질문 만들기


def allow(text: str, crit: dict[str, str]) -> dict[str, str]:
    """문장 처음·공백 뒤의 space와 4글자 미만의 end를 뺀다."""
    if not text or text.endswith(" "):
        del crit[SPACE]
    if len(text.replace(" ", "")) < 4:
        del crit[END]
    return crit


def cho_criteria(text: str) -> dict[str, str]:
    crit = {c: f"초성 {c}({CHO_NAME[c]})으로 시작하는 글자를 이어 쓴다" for c in CHO}
    crit[SPACE] = "띄어쓰기. 단어가 끝났으니 공백을 넣는다"
    crit[END] = "마침표를 찍고 문장을 끝낸다"
    return allow(text, crit)


def jung_criteria(cho: str) -> dict[str, str]:
    return {j: f"중성 {j}({JUNG_NAME[j]}) → 글자 '{compose(cho, j)}'" for j in JUNG}


def jong_criteria(cho: str, jung: str) -> dict[str, str]:
    crit = {"none": f"받침 없음 → 글자 '{compose(cho, jung)}'"}
    for j in JONG[1:]:
        crit[j] = f"받침 {j} → 글자 '{compose(cho, jung, j)}'"
    return crit


def syl_criteria(text: str) -> dict[str, str]:
    crit = {s: f"글자 '{s}'를 이어 쓴다" for s in SYLLABLES}
    crit[SPACE] = "띄어쓰기. 단어가 끝났으니 공백을 넣는다"
    crit[END] = "마침표를 찍고 문장을 끝낸다"
    return allow(text, crit)


def make_state(prompt: str, text: str, partial: str | None) -> str:
    head = (
        "아래는 사용자와 봇의 짧은 한국어 대화다. 봇의 답장을 한 글자씩 완성하고 있다.\n"
        "규칙: 자연스럽고 문법에 맞는 한국어. 답장은 마침표로 끝난다.\n"
        "\n"
        f"사용자: {prompt}\n"
        f"봇: 「{text}」"
    )
    if partial is None:
        return head
    return head + f"\n지금 조립 중인 글자: {partial or '(아직 없음)'}"


# --------------------------------------------------------------------------- 디코딩


def pick(answer: dict, decode: str, history: list[str]) -> str:
    """분포에서 라벨 하나를 고른다. argmax는 최댓값, sample은 페널티→temperature→top-p."""
    if decode == "argmax":
        return answer["choice"]
    weights = dict(answer["probabilities"])
    if history:
        last, recent = history[-1], set(history[-3:])
        for label in weights:
            if label == last:
                weights[label] *= PENALTY_LAST
            elif label in recent:
                weights[label] *= PENALTY_RECENT
    total = sum(weights.values())
    if total <= 0:
        return answer["choice"]
    weights = {k: (v / total) ** (1 / TEMPERATURE) for k, v in weights.items()}
    total = sum(weights.values())
    ordered = sorted(((k, v / total) for k, v in weights.items()), key=lambda kv: -kv[1])
    kept: list[tuple[str, float]] = []
    acc = 0.0
    for label, p in ordered:
        kept.append((label, p))
        acc += p
        if acc >= TOP_P:
            break
    return random.choices([k for k, _ in kept], weights=[p for _, p in kept])[0]


def top5(answer: dict) -> list[list]:
    return [[k, v] for k, v in list(answer["probabilities"].items())[:5]]


# --------------------------------------------------------------------------- 호출


class Runner:
    def __init__(self, client: TypeSafeClient, log: list[dict]):
        self.client = client
        self.log = log
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def ask(self, state: str, questions: dict[str, Choice], meta: dict,
            decode: str, history: dict[str, list[str]]) -> tuple[dict, dict]:
        t0 = time.perf_counter()
        resp = self.client.system_one(state=state, questions=questions)
        ms = (time.perf_counter() - t0) * 1000
        self.calls += 1
        self.input_tokens += resp.usage.input_tokens or 0
        self.output_tokens += resp.usage.output_tokens or 0
        answers = {}
        for name, a in resp.answers.items():
            probs = dict(sorted(a.probabilities.items(), key=lambda kv: -kv[1]))
            answers[name] = {"choice": a.choice, "confidence": a.confidence, "probabilities": probs}
        picked = {}
        for name, a in answers.items():
            hist = history.setdefault(name, [])
            label = pick(a, decode, hist)
            picked[name] = label
            hist.append(label)
        self.log.append({
            **meta,
            "decode": decode,
            "state": state,
            "latency_ms": round(ms, 1),
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": resp.model,
            "answers": answers,
            "picked": picked,
        })
        return answers, picked


def repeated(text: str) -> bool:
    """같은 글자 4연속이거나, 12자 이상에서 마지막 4글자 덩어리가 3번 이상이면 루프."""
    s = text.replace(" ", "")
    if len(s) >= 4 and s[-1] * 4 == s[-4:]:
        return True
    return len(s) >= 12 and s.count(s[-4:]) >= 3


# --------------------------------------------------------------------------- 모드


def run_jamo_sequential(runner: Runner, prompt: str, max_syllables: int, decode: str) -> dict:
    text = ""
    syllables = []
    history: dict[str, list[str]] = {}
    stop = "max"
    for i in range(max_syllables):
        meta = {"prompt": prompt, "mode": f"jamo-seq-{decode}", "syllable": i}
        ans, got = runner.ask(make_state(prompt, text, ""), {"cho": Choice(
            instructions="다음에 올 것은 무엇인가? 새 글자의 초성, 띄어쓰기, 또는 문장 끝.",
            criteria=cho_criteria(text))}, {**meta, "step": "cho"}, decode, history)
        a = ans["cho"]
        if got["cho"] == END:
            text += "."
            syllables.append({"i": i, "unit": ".", "conf": [a["confidence"]], "top": {"cho": top5(a)}})
            stop = "end"
            break
        if got["cho"] == SPACE:
            text += " "
            syllables.append({"i": i, "unit": " ", "conf": [a["confidence"]], "top": {"cho": top5(a)}})
            continue
        cho = got["cho"]
        ans, got = runner.ask(make_state(prompt, text, f"초성 {cho}"), {"jung": Choice(
            instructions="이 글자의 중성(모음)은 무엇인가?",
            criteria=jung_criteria(cho))}, {**meta, "step": "jung"}, decode, history)
        b, jung = ans["jung"], got["jung"]
        ans, got = runner.ask(make_state(prompt, text, f"초성 {cho} + 중성 {jung} = '{compose(cho, jung)}'"), {"jong": Choice(
            instructions="이 글자의 받침(종성)은 무엇인가?",
            criteria=jong_criteria(cho, jung))}, {**meta, "step": "jong"}, decode, history)
        c = ans["jong"]
        jong = "" if got["jong"] == "none" else got["jong"]
        unit = compose(cho, jung, jong)
        text += unit
        syllables.append({"i": i, "unit": unit,
                          "conf": [a["confidence"], b["confidence"], c["confidence"]],
                          "top": {"cho": top5(a), "jung": top5(b), "jong": top5(c)}})
        print(f"  [{i:02d}] {text}", flush=True)
        if repeated(text):
            print("  루프 감지, 중단", flush=True)
            stop = "loop"
            break
    return {"text": text, "syllables": syllables, "stop": stop}


def run_jamo_parallel(runner: Runner, prompt: str, max_syllables: int, decode: str) -> dict:
    """초성·중성·종성을 한 요청에 묻는다. 중성·종성은 초성을 모른 채 고른다."""
    text = ""
    syllables = []
    history: dict[str, list[str]] = {}
    stop = "max"
    for i in range(max_syllables):
        meta = {"prompt": prompt, "mode": f"jamo-par-{decode}", "syllable": i, "step": "all"}
        qs = {
            "cho": Choice(instructions="다음에 올 것은 무엇인가? 새 글자의 초성, 띄어쓰기, 또는 문장 끝.",
                          criteria=cho_criteria(text)),
            "jung": Choice(instructions="다음 글자의 중성(모음)은 무엇인가?",
                           criteria={j: f"중성 {j}({JUNG_NAME[j]})" for j in JUNG}),
            "jong": Choice(instructions="다음 글자의 받침(종성)은 무엇인가?",
                           criteria={"none": "받침 없음", **{j: f"받침 {j}" for j in JONG[1:]}}),
        }
        ans, got = runner.ask(make_state(prompt, text, ""), qs, meta, decode, history)
        a, b, c = ans["cho"], ans["jung"], ans["jong"]
        tops = {"cho": top5(a), "jung": top5(b), "jong": top5(c)}
        if got["cho"] == END:
            text += "."
            syllables.append({"i": i, "unit": ".", "conf": [a["confidence"]], "top": tops})
            stop = "end"
            break
        if got["cho"] == SPACE:
            text += " "
            syllables.append({"i": i, "unit": " ", "conf": [a["confidence"]], "top": tops})
            continue
        jong = "" if got["jong"] == "none" else got["jong"]
        unit = compose(got["cho"], got["jung"], jong)
        text += unit
        syllables.append({"i": i, "unit": unit,
                          "conf": [a["confidence"], b["confidence"], c["confidence"]], "top": tops})
        print(f"  [{i:02d}] {text}", flush=True)
        if repeated(text):
            print("  루프 감지, 중단", flush=True)
            stop = "loop"
            break
    return {"text": text, "syllables": syllables, "stop": stop}


def run_syllable(runner: Runner, prompt: str, max_syllables: int, decode: str) -> dict:
    """한 호출에 음절 하나. 선택지는 빈도 상위 음절 + 띄어쓰기 + 문장 끝."""
    text = ""
    syllables = []
    history: dict[str, list[str]] = {}
    stop = "max"
    for i in range(max_syllables):
        meta = {"prompt": prompt, "mode": f"syl-{decode}", "syllable": i, "step": "syl"}
        ans, got = runner.ask(make_state(prompt, text, None), {"syl": Choice(
            instructions="다음에 올 것은 무엇인가? 다음 글자, 띄어쓰기, 또는 문장 끝.",
            criteria=syl_criteria(text))}, meta, decode, history)
        a, label = ans["syl"], got["syl"]
        tops = {"syl": top5(a)}
        if label == END:
            text += "."
            syllables.append({"i": i, "unit": ".", "conf": [a["confidence"]], "top": tops})
            stop = "end"
            break
        unit = " " if label == SPACE else label
        text += unit
        syllables.append({"i": i, "unit": unit, "conf": [a["confidence"]], "top": tops})
        if label == SPACE:
            continue
        print(f"  [{i:02d}] {text}", flush=True)
        if repeated(text):
            print("  루프 감지, 중단", flush=True)
            stop = "loop"
            break
    return {"text": text, "syllables": syllables, "stop": stop}


MODES = [
    ("jamo-seq-argmax", "jamo", "argmax", run_jamo_sequential),
    ("jamo-seq-sample", "jamo", "sample", run_jamo_sequential),
    ("jamo-par-argmax", "jamo", "argmax", run_jamo_parallel),
    ("syl-argmax", "syllable", "argmax", run_syllable),
    ("syl-sample", "syllable", "sample", run_syllable),
]


def main() -> None:
    global SYLLABLES
    prompts = sys.argv[1:] or ["안녕하세요", "오늘 하루 어땠어?"]
    max_syllables = 40
    random.seed(SEED)
    SYLLABLES = load_syllables()
    client = TypeSafeClient()
    log: list[dict] = []
    runner = Runner(client, log)
    runs = []
    t_start = time.perf_counter()
    for prompt in prompts:
        for mode, unit, decode, fn in MODES:
            print(f"\n== {prompt} / {mode}", flush=True)
            calls0, t0 = runner.calls, time.perf_counter()
            result = fn(runner, prompt, max_syllables, decode)
            runs.append({
                "prompt": prompt, "mode": mode, "decode": decode, "unit": unit,
                "text": result["text"], "stop": result["stop"],
                "syllables": result["syllables"],
                "calls": runner.calls - calls0,
                "seconds": round(time.perf_counter() - t0, 1),
            })
            print(f"→ 「{result['text']}」  ({runner.calls - calls0}회 호출, {result['stop']})", flush=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": log[0]["model"] if log else None,
        "max_syllables": max_syllables,
        "decoding": {"seed": SEED, "temperature": TEMPERATURE, "top_p": TOP_P,
                     "penalty_last": PENALTY_LAST, "penalty_recent": PENALTY_RECENT},
        "syllable_table": {"path": SYL_TABLE.name, "size": len(SYLLABLES)},
        "totals": {
            "calls": runner.calls,
            "input_tokens": runner.input_tokens,
            "output_tokens": runner.output_tokens,
            "seconds": round(time.perf_counter() - t_start, 1),
        },
        "runs": runs,
        "calls": log,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {OUT}  (호출 {runner.calls}회, 입력 {runner.input_tokens} 토큰)")


if __name__ == "__main__":
    main()
