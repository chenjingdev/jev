"""Jev-like 공통 호출 인터페이스. PROTOCOL.md 1절.

모든 시스템은 choose(state, instructions, criteria) -> {키: 확률} 하나로만 호출된다.
어댑터는 정답 파일을 읽지 않는다.

로컬 Jev-like는 각자 전용 가상환경에서 `shim` 서버를 띄우고, 여기서는 HTTP로만 부른다.
shim 계약 (모든 로컬 시스템 공통):
  GET  /health  -> {"name": str, "returns_probabilities": bool, "max_input_tokens": int | null, "detail": {...}}
  POST /choose  {"state": {...}, "instructions": str, "criteria": {"A": str, ...}}
       200 -> {"probabilities": {"A": float, ...}}   # 키 집합이 criteria와 같아야 한다
       413 -> {"error": "unsupported", "reason": str, "input_tokens": int | null}  # 몰래 자르지 않는다
"""
import json
from typing import Mapping, Protocol
import urllib.error
import urllib.request


class Unsupported(Exception):
    """입력 길이 등으로 시스템이 처리할 수 없는 문항. 어댑터는 몰래 자르지 않고 이걸 던진다."""


class Adapter(Protocol):
    name: str
    returns_probabilities: bool  # False면 고른 답 1.0으로 기록되고 보고표에 표시된다

    def choose(self, state: Mapping, instructions: str, criteria: Mapping[str, str]) -> dict[str, float]:
        ...


def as_state(state):
    """state는 객체 그대로 보낸다. 제작자 벤치마크(claims/)처럼 원본 state가 문자열이나 목록이면 그대로 보낸다."""
    return state if isinstance(state, (str, list)) else dict(state)


def check(probs, criteria):
    if set(probs) != set(criteria):
        raise ValueError(f'Response options do not match request: {sorted(probs)}')
    return {k: float(v) for k, v in probs.items()}


class JevAdapter:
    name = 'jev-1.13.0'
    returns_probabilities = True

    def __init__(self, timeout: float = 45):
        self.timeout = timeout

    def choose(self, state, instructions, criteria):
        from typesafe_sdk import Choice, TypeSafeClient
        with TypeSafeClient(timeout=self.timeout) as client:
            r = client.system_one(model=self.name, state=as_state(state),
                                  questions={'answer': Choice(instructions=instructions, criteria=dict(criteria))})
        return check(dict(r.answers['answer'].probabilities), criteria)


class ShimAdapter:
    """로컬 shim 서버(위 계약)를 부르는 어댑터."""

    def __init__(self, name: str, port: int, timeout: float = 600):
        self.name, self.url, self.timeout = name, f'http://127.0.0.1:{port}', timeout
        self.returns_probabilities = True

    def health(self):
        with urllib.request.urlopen(self.url + '/health', timeout=10) as r:
            info = json.loads(r.read())
        self.returns_probabilities = info.get('returns_probabilities', True)
        return info

    def choose(self, state, instructions, criteria):
        body = json.dumps({'state': as_state(state), 'instructions': instructions, 'criteria': dict(criteria)},
                          ensure_ascii=False).encode()
        req = urllib.request.Request(self.url + '/choose', body, {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return check(json.loads(r.read())['probabilities'], criteria)
        except urllib.error.HTTPError as e:
            if e.code == 413:
                raise Unsupported(e.read().decode()[:300]) from None
            raise


# 로컬 시스템별 shim 포트. shim 코드는 csat/bench/shims/<name>/ 에 있다.
SHIMS = {
    'open-jev': 8801,
    'jevmlx': 8802,
    'semif': 8803,
    'kev': 8804,
    'laya': 8805,
    'clm': 8806,  # amd(Windows) 원격 실행. Mac에서는 ssh -L 8806:127.0.0.1:8806 amd 터널로 부른다
    'julia': 8807,
    'laya-typed': 8808,  # claims/ 전용: Laya가 typed-decisions로 추가 학습한 체크포인트
    'jeff-0.8b': 8809,
    'jeff-2b': 8810,
    'jeff-gemma4-e2b': 8811,
}


def get(name: str):
    if name == JevAdapter.name:
        return JevAdapter()
    return ShimAdapter(name, SHIMS[name])
