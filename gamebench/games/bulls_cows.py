"""숫자야구 (세 자리, 1~9 중 서로 다른 숫자).

① 판정: 비밀 숫자와 추측이 주어졌을 때 결과(S·B).
③ 한 수: 추측 기록이 주어졌을 때, 보기 중 모든 결과와 맞는 비밀 숫자(보기 중 하나만 맞는다).
② 변형: 볼을 "자리와 상관없이 비밀 숫자에 들어 있는 숫자의 개수"로 세는 규칙(스트라이크도 볼에 함께 센다).
   ①은 스트라이크가 있는 경우, ③은 두 규칙에서 맞는 보기가 서로 다른 기록만.
"""
from itertools import permutations

from .common import make_item

GAME = 'bulls_cows'
NAME = '숫자야구'
FACET = '논리·정보 추론'

ALL = [''.join(p) for p in permutations('123456789', 3)]
COMMON = ('비밀 숫자는 1~9 중 서로 다른 숫자 3개로 된 세 자리 수다. 세 자리 수를 추측하면 결과를 "1S 1B"처럼 '
          '스트라이크(S) 개수와 볼(B) 개수로 알려 준다. 스트라이크는 숫자와 자리가 모두 비밀 숫자와 같은 개수다. ')
RULE_TEXT = {
    'base': COMMON + '볼은 비밀 숫자에 들어 있지만 자리가 다른 숫자의 개수다.',
    'total': COMMON + '볼은 자리와 상관없이 비밀 숫자에 들어 있는 숫자의 개수다. 스트라이크인 숫자도 볼에 함께 센다.',
}


def score(secret, guess, rule):
    s = sum(a == b for a, b in zip(secret, guess))
    common = len(set(secret) & set(guess))
    return (s, common - s) if rule == 'base' else (s, common)


def fmt(r):
    return f'{r[0]}S {r[1]}B'


RESULTS = sorted({fmt(score(a, g, rule)) for rule in RULE_TEXT for a in ('123',) for g in ALL})


def consistent(cand, history, rule):
    return all(fmt(score(cand, g, rule)) == r for g, r in history)


def misses(cand, history, rule):
    return sum(fmt(score(cand, g, rule)) != r for g, r in history)


def generate(rng, per_stage):
    items = []
    # ① 판정: 결과 종류를 돌아가며 고른다. 스트라이크가 있으면 짝을 만든다
    q1 = '이 추측의 결과는?'
    by_result = {}
    for g in ALL:
        by_result.setdefault(score('123', g, 'base'), []).append(g)
    kinds = sorted(r for r in by_result if r != (3, 0))  # 추측이 비밀 숫자 그대로인 문항은 뺀다
    rng.shuffle(kinds)
    for i in range(per_stage):
        r = kinds[i % len(kinds)]
        # '123' 기준으로 뽑은 추측을 무작위 숫자 치환으로 옮겨 비밀 숫자도 다양하게 한다
        g0 = rng.choice(by_result[r])
        perm = dict(zip('123456789', rng.sample('123456789', 9)))
        secret, guess = ''.join(perm[c] for c in '123'), ''.join(perm[c] for c in g0)
        assert score(secret, guess, 'base') == r
        state = {'규칙': RULE_TEXT['base'], '상황': f'비밀 숫자는 {secret}이다. 추측한 수는 {guess}이다.'}
        base = make_item(rng, GAME, '1-판정', i, state, q1, RESULTS, fmt(score(secret, guess, 'base')))
        items.append(base)
        if r[0] > 0:
            items.append(make_item(rng, GAME, '2-변형', i, dict(state, 규칙=RULE_TEXT['total']), q1, RESULTS,
                                   fmt(score(secret, guess, 'total')), original=base_ans(base), twin_of=base['id'],
                                   order=base['options']))
    # ③ 기록과 맞는 비밀 숫자: 보기 6개, 짝은 절반
    q3 = '지금까지의 추측 기록을 보면, 보기 중 비밀 숫자가 될 수 있는 것은?'
    i = 0
    while i < per_stage:
        want_twin = i % 2 == 0
        secret = rng.choice(ALL)
        guesses = rng.sample([g for g in ALL if g != secret], rng.randint(2, 3))
        history = [(g, fmt(score(secret, g, 'base'))) for g in guesses]
        base_ok = [c for c in ALL if consistent(c, history, 'base')]
        twin_ok = [c for c in ALL if consistent(c, history, 'total')]
        twin_only = [c for c in twin_ok if c not in base_ok]
        if want_twin and not twin_only:
            continue
        others = [c for c in ALL if c not in base_ok and c not in twin_ok]
        near = [c for c in others if misses(c, history, 'base') == 1]
        if len(near) < 4:
            continue
        opts = [secret] + ([rng.choice(twin_only)] if want_twin else []) + rng.sample(near, 6 - 1 - want_twin)
        sit = '추측 기록:\n' + '\n'.join(f'{g} → {r}' for g, r in history)
        state = {'규칙': RULE_TEXT['base'], '상황': sit}
        base = make_item(rng, GAME, '3-한수', i, state, q3, opts, secret)
        assert [o for o in opts if consistent(o, history, 'base')] == [secret]
        items.append(base)
        if want_twin:
            tw = [o for o in opts if consistent(o, history, 'total')]
            assert len(tw) == 1 and tw[0] != secret
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=RULE_TEXT['total']), q3, opts,
                                   tw[0], original=secret, twin_of=base['id'], order=base['options']))
        i += 1
    return items


def base_ans(item):
    return item['options'][item['answer'] - 1]
