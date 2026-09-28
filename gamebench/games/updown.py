"""업다운 (1~100 수 맞히기).

① 판정: 기록이 주어졌을 때 비밀 수가 될 수 있는 범위.
③ 한 수: 운이 가장 나쁜 경우에도 맞힐 때까지 부르는 횟수가 가장 적은 다음 수.
   남은 범위의 크기가 2^k-1인 국면만 써서 가운데 수 하나만 최선이 되게 한다(풀이기로 확인).
② 변형: "비밀 수가 부른 수보다 작으면 '업', 크면 '다운'". 두 규칙 모두에서 범위가 비지 않으려면
   기록이 한 방향(모두 업 또는 모두 다운)이어야 하므로, 짝은 그런 기록만 쓴다.
"""
from .common import make_item

GAME = 'updown'
NAME = '업다운'
FACET = '논리·정보 추론'

LO, HI = 1, 100
RULE_TEXT = {
    'base': f'비밀 수는 {LO}부터 {HI}까지의 정수 중 하나다. 수를 하나 부르면, 비밀 수가 부른 수보다 크면 "업", '
            '작으면 "다운", 같으면 "맞음"이라고 알려 준다.',
    'rev': f'비밀 수는 {LO}부터 {HI}까지의 정수 중 하나다. 수를 하나 부르면, 비밀 수가 부른 수보다 작으면 "업", '
           '크면 "다운", 같으면 "맞음"이라고 알려 준다.',
}


def interval(history, rule):
    """기록과 맞는 범위 (lo, hi). 비면 None."""
    lo, hi = LO, HI
    for g, r in history:
        bigger = (r == '업') == (rule == 'base')  # 비밀 수가 g보다 큰가
        if bigger:
            lo = max(lo, g + 1)
        else:
            hi = min(hi, g - 1)
    return (lo, hi) if lo <= hi else None


def need(n):
    """크기 n인 범위에서 운이 가장 나빠도 맞히는 데 필요한 최소 횟수."""
    c = 0
    while n > 0:
        n //= 2
        c += 1
    return c


def worst(rng_, g):
    lo, hi = rng_
    if not lo <= g <= hi:
        return 1 + need(hi - lo + 1)
    return 1 + max(need(g - lo), need(hi - g))


def fmt_range(r):
    return f'{r[0]}부터 {r[1]}까지'


def fmt_history(history):
    return '기록: ' + ', '.join(f'{g} → {r}' for g, r in history)


def narrow(rng, target):
    """1~100에서 시작해 매번 현재 범위 안의 수를 불러 target 범위로 좁혀 가는 기록."""
    L, U = target
    lo, hi, hist = LO, HI, []
    while (lo, hi) != (L, U):
        if len(hist) < 3:
            g = rng.choice([g for g in range(lo, hi + 1) if g < L or g > U])
        else:  # 기록이 길어지지 않게 네 번째부터는 범위 끝 바로 바깥을 부른다
            g = L - 1 if lo < L else U + 1
        if g < L:
            hist.append((g, '업')); lo = g + 1
        else:
            hist.append((g, '다운')); hi = g - 1
    return hist


def monotone(rng, first, last, up, extra):
    """한 방향 기록: first에서 시작해 last로 끝난다. 업이면 커지고, 다운이면 작아진다."""
    a, b = sorted((first, last))
    mids = sorted(rng.sample(range(a + 1, b), min(extra, b - a - 1)))
    gs = [a] + mids + [b]
    if not up:
        gs = gs[::-1]
    return [(g, '업' if up else '다운') for g in gs]


def range_options(ranges):
    opts = []
    for lo, hi in ranges:
        for r in ((lo, hi), (lo - 1, hi + 1), (lo - 1, hi), (lo, hi + 1)):
            if LO <= r[0] <= r[1] <= HI and fmt_range(r) not in opts:
                opts.append(fmt_range(r))
    return opts


def guess_options(ranges):
    opts = []
    for lo, hi in ranges:
        m = (lo + hi) // 2
        for g in (m, m - 1, m + 1, lo, hi, (lo + m) // 2):
            if LO <= g <= HI and str(g) not in opts:
                opts.append(str(g))
    return opts


def best_among(r, opts):
    scores = {o: worst(r, int(o)) for o in opts}
    top = min(scores.values())
    best = [o for o, v in scores.items() if v == top]
    assert len(best) == 1, (r, scores)
    return best[0]


def generate(rng, per_stage):
    items = []
    # ① 판정: 짝수 번째는 섞인 기록(짝 없음), 홀수 번째는 한 방향 기록(짝 있음)
    q1 = '지금까지의 기록으로 볼 때, 비밀 수가 될 수 있는 범위는?'
    for i in range(per_stage):
        if i % 2 == 0:
            L = rng.randint(10, 80)
            hist = narrow(rng, (L, L + rng.randint(3, 15)))
        else:
            up = i % 4 == 1
            a, b = sorted(rng.sample(range(10, 91), 2))
            hist = monotone(rng, a, b, up, rng.randint(0, 2))
        state = {'규칙': RULE_TEXT['base'], '상황': fmt_history(hist)}
        rb, rt = interval(hist, 'base'), interval(hist, 'rev')
        opts = range_options([rb] + ([rt] if rt else []))
        base = make_item(rng, GAME, '1-판정', i, state, q1, opts, fmt_range(rb))
        items.append(base)
        if rt:
            items.append(make_item(rng, GAME, '2-변형', i, dict(state, 규칙=RULE_TEXT['rev']), q1, opts,
                                   fmt_range(rt), original=fmt_range(rb), twin_of=base['id'], order=base['options']))
    # ③ 한 수: 짝수 번째는 섞인 기록, 홀수 번째는 두 규칙 모두 범위 크기가 2^k-1인 한 방향 기록(짝 있음)
    q3 = '보기 중 다음에 부를 수로, 운이 가장 나빠도 맞힐 때까지 부르는 횟수가 가장 적은 것은?'
    lows, highs = (8, 16, 32), (69, 85, 93)  # 1~(x-1), (y+1)~100 이 7, 15, 31칸
    for i in range(per_stage):
        if i % 2 == 0:
            size = rng.choice((7, 15, 31))
            L = rng.randint(LO + 1, HI - size)
            hist = narrow(rng, (L, L + size - 1))
            ranges = [interval(hist, 'base')]
        else:
            up = i % 4 == 1
            hist = monotone(rng, rng.choice(lows), rng.choice(highs), up, rng.randint(0, 2))
            ranges = [interval(hist, 'base'), interval(hist, 'rev')]
        opts = guess_options(ranges)
        state = {'규칙': RULE_TEXT['base'], '상황': fmt_history(hist)}
        ans = best_among(ranges[0], opts)
        base = make_item(rng, GAME, '3-한수', i, state, q3, opts, ans)
        items.append(base)
        if len(ranges) == 2:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=RULE_TEXT['rev']), q3, opts,
                                   best_among(ranges[1], opts), original=ans, twin_of=base['id'],
                                   order=base['options']))
    return items
