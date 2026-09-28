"""포켓몬 타입 상성 (상성표를 규칙 안에 준다).

타입 6개(불·물·풀·전기·땅·비행)만 쓴다. 표는 규칙 문구에 모두 들어 있어 바깥 지식이 필요 없다.
규칙 문구는 CHART에서 만들고, 풀이기도 같은 표를 읽는다.
① 판정: 타입이 하나인 상대에게 보기 중 가장 큰(또는 가장 작은) 피해를 주는 기술 타입.
③ 한 수: 타입이 둘인 상대(배수를 곱한다)에게 가장 큰 피해를 주는 기술 타입. 가장 큰 배수가 하나뿐인 경우만.
② 변형: 같은 상황·보기에서 표의 한 칸만 바꾼 규칙. 바꾼 칸은 문항마다 답이 달라지는 칸을 고른다.
"""
from .common import make_item

GAME = 'pokemon_types'
NAME = '포켓몬 타입 상성'
FACET = '규칙 판정'

TYPES = ['불', '물', '풀', '전기', '땅', '비행']
# 공격 타입 → {방어 타입: 배수}. 여기 없는 조합은 1배.
CHART = {
    '불': {'풀': 2, '불': 0.5, '물': 0.5},
    '물': {'불': 2, '땅': 2, '물': 0.5, '풀': 0.5},
    '풀': {'물': 2, '땅': 2, '불': 0.5, '풀': 0.5, '비행': 0.5},
    '전기': {'물': 2, '비행': 2, '풀': 0.5, '전기': 0.5, '땅': 0},
    '땅': {'불': 2, '전기': 2, '풀': 0.5, '비행': 0},
    '비행': {'풀': 2, '전기': 0.5},
}
VALUES = [2, 0.5, 0]


def fmt(v):
    return {2: '2배', 0.5: '0.5배', 0: '0배(피해 없음)', 1: '1배'}[v]


def obj(w):
    return w + ('을' if (ord(w[-1]) - 0xAC00) % 28 else '를')


def rules_text(chart):
    lines = []
    for atk in TYPES:
        parts = []
        for v in VALUES:
            ds = [d for d in TYPES if chart[atk].get(d, 1) == v]
            if ds:
                parts.append(f'{"·".join(ds)}에 {fmt(v)}')
        lines.append(f'- {atk} 기술: ' + (', '.join(parts) if parts else '모든 타입에 1배'))
    return ('기술은 타입이 하나이고, 포켓몬은 타입이 하나 또는 둘이다. 기술이 주는 피해의 배수는 아래 표를 따른다. '
            '표에 없는 조합은 1배다. 포켓몬의 타입이 둘이면 두 타입에 대한 배수를 곱한다. 배수가 클수록 피해가 크다.\n'
            + '\n'.join(lines))


def mult(chart, atk, defender):
    m = 1
    for d in defender:
        m *= chart[atk].get(d, 1)
    return m


def extreme(chart, defender, options, goal):
    """goal 'max'/'min'. 배수가 가장 큰(작은) 보기가 하나뿐이면 그 보기, 아니면 None."""
    ms = {a: mult(chart, a, defender) for a in options}
    top = (max if goal == 'max' else min)(ms.values())
    hs = [a for a in options if ms[a] == top]
    return hs[0] if len(hs) == 1 else None


def modified(chart, atk, d, v):
    c = {a: dict(row) for a, row in chart.items()}
    if v == 1:
        c[atk].pop(d, None)
    else:
        c[atk][d] = v
    return c


def find_twin(rng, defender, options, goal, ans):
    """표 한 칸을 바꿔 답이 하나로 정해지면서 달라지는 경우를 찾는다."""
    cands = [(a, d, v) for a in options for d in dict.fromkeys(defender) for v in (2, 1, 0.5, 0)
             if CHART[a].get(d, 1) != v]
    rng.shuffle(cands)
    for a, d, v in cands:
        c = modified(CHART, a, d, v)
        t = extreme(c, defender, options, goal)
        if t is not None and t != ans:
            return c, t
    return None, None


QUESTIONS = {'max': '보기 중 상대에게 가장 큰 피해를 주는 기술의 타입은?',
             'min': '보기 중 상대에게 가장 작은 피해를 주는 기술의 타입은?'}


def generate(rng, per_stage):
    items = []
    std = rules_text(CHART)
    k = 0
    stages = [('1-판정', [(d,) for d in TYPES], ('max', 'min')),
              ('3-한수', [(a, b) for i, a in enumerate(TYPES) for b in TYPES[i + 1:]], ('max',))]
    for stage, defenders, goals in stages:
        made = 0
        tries = 0
        while made < per_stage:
            tries += 1
            assert tries < 10000
            defender = rng.choice(defenders)
            goal = rng.choice(goals)
            options = rng.sample(TYPES, rng.choice([3, 4, 5]))
            ans = extreme(CHART, defender, options, goal)
            if ans is None:
                continue
            sit = f'상대 포켓몬은 {"·".join(defender)} 두 타입이다.' if len(defender) == 2 else \
                f'상대 포켓몬은 {defender[0]} 타입 하나뿐이다.'
            base = make_item(rng, GAME, stage, made, {'규칙': std, '상황': sit}, QUESTIONS[goal], options, ans)
            items.append(base)
            if made % 4 != 3:  # 넷에 하나는 짝 없이 둔다
                chart, twin = find_twin(rng, defender, options, goal, ans)
                if twin is not None:
                    items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rules_text(chart), '상황': sit},
                                           QUESTIONS[goal], options, twin, original=ans, twin_of=base['id'],
                                           order=base['options']))
                    k += 1
            made += 1
    return items
