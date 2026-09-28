"""야추 (요트 다이스).

① 판정: 이 굴림을 주어진 칸에 적으면 몇 점인가.
③ 한 수: 비어 있는 칸 가운데 이번 굴림으로 점수가 가장 높게 나오는 칸 (최댓값이 하나인 경우만).
② 변형: 한 칸의 점수 규칙만 다르다 (풀하우스 고정 25점, 포카드는 같은 눈 4개의 합,
   스몰 스트레이트 30점, 라지 스트레이트 40점). 답이 달라지는 경우만 짝으로 쓴다.
"""
from collections import Counter

from .common import make_item

GAME = 'yacht'
NAME = '야추'
FACET = '확률·기댓값'

NUMBERS = ['에이스(1)', '듀스(2)', '트레이(3)', '포(4)', '파이브(5)', '식스(6)']
CATS = NUMBERS + ['초이스', '포카드', '풀하우스', '스몰 스트레이트', '라지 스트레이트', '야추']

BASE = {'fh': 'sum', 'fk': 'all', 'ss': 15, 'ls': 30, 'dbl': None}
TWINS = {  # 규칙 이름: (바뀌는 설정, 영향을 받는 칸)
    'fh25': ({'fh': 25}, '풀하우스'),
    'fk4': ({'fk': 'four'}, '포카드'),
    'ss30': ({'ss': 30}, '스몰 스트레이트'),
    'ls40': ({'ls': 40}, '라지 스트레이트'),
    **{f'dbl{n}': ({'dbl': n}, NUMBERS[n - 1]) for n in range(1, 7)},  # 숫자 칸 하나만 두 배
}


def rules_text(cfg):
    fh = '다섯 개 눈의 합' if cfg['fh'] == 'sum' else f"{cfg['fh']}점"
    fk = '다섯 개 눈의 합' if cfg['fk'] == 'all' else '같은 눈 4개의 합(나머지 1개는 빼고)'
    if cfg['dbl'] is None:
        nums = '에이스(1)·듀스(2)·트레이(3)·포(4)·파이브(5)·식스(6): 그 눈이 나온 주사위들의 눈 합. '
    else:
        rest = [c for j, c in enumerate(NUMBERS) if j != cfg['dbl'] - 1]
        nums = ('·'.join(rest) + ': 그 눈이 나온 주사위들의 눈 합. '
                + NUMBERS[cfg['dbl'] - 1] + ': 그 눈이 나온 주사위들의 눈 합의 두 배. ')
    return ('주사위 5개를 굴려 나온 눈으로 아래 칸 중 하나에 점수를 적는다. ' + nums +
            '초이스: 다섯 개 눈의 합. '
            f'포카드: 같은 눈이 4개 이상이면 {fk}, 아니면 0점. '
            f'풀하우스: 같은 눈 3개와 다른 같은 눈 2개로 이루어지면 {fh}, 아니면 0점'
            '(다섯 개가 모두 같으면 풀하우스가 아니다). '
            f"스몰 스트레이트: 1-2-3-4, 2-3-4-5, 3-4-5-6 중 하나의 네 눈이 모두 들어 있으면 {cfg['ss']}점, 아니면 0점. "
            f"라지 스트레이트: 다섯 눈이 1-2-3-4-5 또는 2-3-4-5-6이면 {cfg['ls']}점, 아니면 0점. "
            '야추: 다섯 개가 모두 같으면 50점, 아니면 0점.')


def score(dice, cat, cfg=BASE):
    c = Counter(dice)
    s = sum(dice)
    if cat in NUMBERS:
        v = NUMBERS.index(cat) + 1
        return v * c[v] * (2 if cfg['dbl'] == v else 1)
    if cat == '초이스':
        return s
    if cat == '포카드':
        four = [v for v, n in c.items() if n >= 4]
        if not four:
            return 0
        return s if cfg['fk'] == 'all' else 4 * four[0]
    if cat == '풀하우스':
        if sorted(c.values()) != [2, 3]:
            return 0
        return s if cfg['fh'] == 'sum' else cfg['fh']
    if cat == '스몰 스트레이트':
        return cfg['ss'] if any(set(r) <= set(dice) for r in ((1, 2, 3, 4), (2, 3, 4, 5), (3, 4, 5, 6))) else 0
    if cat == '라지 스트레이트':
        return cfg['ls'] if sorted(dice) in ([1, 2, 3, 4, 5], [2, 3, 4, 5, 6]) else 0
    if cat == '야추':
        return 50 if len(c) == 1 else 0
    raise ValueError(cat)


def best_cat(dice, open_cats, cfg=BASE):
    """최댓값이 하나면 그 칸, 아니면 None."""
    scores = {k: score(dice, k, cfg) for k in open_cats}
    top = max(scores.values())
    best = [k for k, v in scores.items() if v == top]
    return best[0] if len(best) == 1 else None


def cfg_of(name):
    return BASE if name == 'base' else dict(BASE, **TWINS[name][0])


def roll_for(rng, kind):
    """칸과 관련 있는 굴림을 자주 만든다."""
    d = lambda: rng.randint(1, 6)
    if kind == '풀하우스':
        a, b = rng.sample(range(1, 7), 2)
        dice = [a, a, a, b, b]
    elif kind == '포카드':
        a = d()
        dice = [a] * 4 + [d()]
    elif kind == '스몰 스트레이트':
        lo = rng.randint(1, 3)
        dice = list(range(lo, lo + 4)) + [d()]
    elif kind == '라지 스트레이트':
        lo = rng.randint(1, 2)
        dice = list(range(lo, lo + 5))
    elif kind == '야추':
        dice = [d()] * 5
    else:
        dice = [d() for _ in range(5)]
    rng.shuffle(dice)
    return dice


def fmt_roll(dice):
    return '이번에 굴린 주사위 5개: ' + ', '.join(map(str, dice))


def pts(v):
    return f'{v}점'


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 변형 짝
    q_kinds = ['풀하우스', '포카드', '스몰 스트레이트', '라지 스트레이트', '초이스', '야추', 'num']
    twin_for = {TWINS[t][1]: t for t in TWINS}
    k2 = 0
    for i in range(per_stage):
        kind = q_kinds[i % len(q_kinds)]
        for _ in range(200):
            if kind == 'num':
                dice = roll_for(rng, 'any')
                cat = rng.choice(NUMBERS)
                if score(dice, cat) == 0:
                    continue
            else:
                cat = kind
                dice = roll_for(rng, kind if rng.random() < 0.8 else 'any')
            base_v = score(dice, cat)
            twin = twin_for.get(cat)
            tw_v = score(dice, cat, cfg_of(twin)) if twin else None
            if twin and tw_v == base_v and rng.random() < 0.7:
                continue
            break
        cands = sorted(({score(dice, k) for k in CATS} | {sum(dice), 0}) - {base_v, tw_v})
        rng.shuffle(cands)
        opts = [base_v] + ([tw_v] if tw_v is not None and tw_v != base_v else [])
        opts += cands[:6 - len(opts)]
        opts = [pts(v) for v in opts]
        state = {'규칙': rules_text(BASE), '상황': fmt_roll(dice)}
        q = f"이 굴림을 '{cat}' 칸에 적으면 몇 점인가?"
        base = make_item(rng, GAME, '1-판정', i, state, q, opts, pts(base_v))
        items.append(base)
        if tw_v is not None and tw_v != base_v:
            items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=rules_text(cfg_of(twin))), q, opts,
                                   pts(tw_v), original=pts(base_v), twin_of=base['id'], order=base['options']))
            k2 += 1
    # ③ 한 수 + ② 변형 짝: 비어 있는 칸 중 점수가 가장 높은 칸
    q3 = '이번 굴림을 비어 있는 칸 하나에 적어야 한다. 점수가 가장 높게 나오는 칸은?'
    want_twins = per_stage // 2
    twinned, plain = [], []
    kinds = ['풀하우스', '포카드', '스몰 스트레이트', '라지 스트레이트', '야추', 'any', 'any']
    for _ in range(5000):
        if len(twinned) >= want_twins and len(plain) >= per_stage - want_twins:
            break
        dice = roll_for(rng, rng.choice(kinds))
        open_cats = sorted(rng.sample(CATS, rng.randint(4, 9)), key=CATS.index)
        b = best_cat(dice, open_cats)
        if b is None or score(dice, b) == 0 or sum(u[2] == b for u in twinned + plain) >= 3:
            continue
        tws = [(name, best_cat(dice, open_cats, cfg_of(name))) for name in sorted(TWINS)]
        tws = [(name, t) for name, t in tws if t is not None and t != b]
        tw = rng.choice(tws) if tws else None
        if tw and len(twinned) < want_twins:
            twinned.append((dice, open_cats, b, tw))
        elif not tw and len(plain) < per_stage - want_twins:
            plain.append((dice, open_cats, b, None))
    assert len(twinned) + len(plain) == per_stage, (len(twinned), len(plain))
    for i, (dice, open_cats, b, tw) in enumerate(twinned + plain):
        state = {'규칙': rules_text(BASE), '상황': fmt_roll(dice) + '. 아직 비어 있는 칸: ' + ', '.join(open_cats)}
        base = make_item(rng, GAME, '3-한수', i, state, q3, open_cats, b)
        items.append(base)
        if tw:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=rules_text(cfg_of(tw[0]))), q3,
                                   open_cats, tw[1], original=b, twin_of=base['id'], order=base['options']))
    return items
