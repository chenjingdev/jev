"""지뢰찾기.

판 표기는 틱택토 기준(행 A~, 열 1~). 이웃은 규칙 문구가 정한다(8방향 또는 4방향).
① 판정: 지뢰 위치가 모두 보이는 판에서 한 칸에 적힐 숫자.
③ 한 수(판/주석): 열린 숫자만 보이는 판에서, 보기 칸 가운데 확실히 안전한 칸이 정확히 하나.
   '확실히 안전'은 열린 숫자를 모두 만족하는 지뢰 배치 전부에서 지뢰가 아닌 것이다(풀이기가 전수 확인).
   전체 지뢰 수는 알려 주지 않는다. (주석)은 보기 칸마다 맞닿은(8방향) 열린 칸의 숫자를 붙인다.
② 변형: 숫자가 위·아래·왼쪽·오른쪽 4칸만 센다는 규칙. 같은 판이 두 규칙 모두에서 가능하고,
   확실히 안전한 보기 칸이 두 규칙에서 각각 하나이며 서로 다른 판만 쓴다.
"""
from .common import make_item

GAME = 'minesweeper'
NAME = '지뢰찾기'
FACET = '논리·정보 추론'

ROWS = 'ABCDEF'
NB = {8: [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)],
      4: [(-1, 0), (1, 0), (0, -1), (0, 1)]}
RULE_TEXT = {
    8: '지뢰찾기 판이다. 열린 칸에는 지뢰가 없고, 열린 칸에 적힌 숫자는 그 칸을 둘러싼 8칸(위·아래·왼쪽·오른쪽과 대각선 네 칸) '
       '가운데 지뢰가 있는 칸의 수다. 판 밖은 세지 않는다.',
    4: '지뢰찾기 판이다. 열린 칸에는 지뢰가 없고, 열린 칸에 적힌 숫자는 그 칸의 위·아래·왼쪽·오른쪽 4칸 가운데 '
       '지뢰가 있는 칸의 수다. 대각선 칸은 세지 않는다. 판 밖은 세지 않는다.',
}
NOTATION1 = '판은 행 A~, 열 1~로 적는다. "*"는 지뢰, "."은 지뢰가 없는 칸이다. 좌표는 "B2"처럼 행과 열을 붙여 쓴다.'
NOTATION3 = ('판은 행 A~, 열 1~로 적는다. 숫자는 열린 칸, "?"는 아직 열지 않은 칸이다. 좌표는 "B2"처럼 행과 열을 붙여 쓴다. '
             '판 전체의 지뢰 수는 알려 주지 않는다.')


def coord(r, c):
    return ROWS[r] + str(c + 1)


def neighbors(h, w, r, c, k):
    return [(r + dr, c + dc) for dr, dc in NB[k] if 0 <= r + dr < h and 0 <= c + dc < w]


def count(mines, h, w, r, c, k):
    return sum((p in mines) for p in neighbors(h, w, r, c, k))


def render_full(h, w, mines):
    return '  ' + ' '.join(str(c + 1) for c in range(w)) + '\n' + '\n'.join(
        ROWS[r] + ' ' + ' '.join('*' if (r, c) in mines else '.' for c in range(w)) for r in range(h))


def render_open(h, w, nums):
    return '  ' + ' '.join(str(c + 1) for c in range(w)) + '\n' + '\n'.join(
        ROWS[r] + ' ' + ' '.join(str(nums[(r, c)]) if (r, c) in nums else '?' for c in range(w)) for r in range(h))


def analyze(h, w, nums, k):
    """열린 숫자 nums {(r,c): n}을 규칙 k로 읽는다.
    돌려주는 값: (가능한 배치가 있는가, 지뢰일 수 있는 칸 집합, 제약에 걸린 칸 집합)."""
    cons = []
    for (r, c), n in nums.items():
        cells = [p for p in neighbors(h, w, r, c, k) if p not in nums]
        if n > len(cells):
            return False, set(), set()
        cons.append((cells, n))
    frontier = sorted({p for cells, _ in cons for p in cells})
    by_var = {v: [j for j, (cells, _) in enumerate(cons) if v in cells] for v in frontier}

    def ok(assign, touched):
        for j in touched:
            cells, n = cons[j]
            m = sum(assign.get(p, 0) for p in cells)
            u = sum(1 for p in cells if p not in assign)
            if m > n or m + u < n:
                return False
        return True

    def find(forced):
        order = [v for v in frontier if v in forced] + [v for v in frontier if v not in forced]
        assign = {}

        def rec(i):
            if i == len(order):
                return dict(assign)
            v = order[i]
            for val in ((forced[v],) if v in forced else (0, 1)):
                assign[v] = val
                if ok(assign, by_var[v]):
                    res = rec(i + 1)
                    if res is not None:
                        return res
                del assign[v]
            return None
        return rec(0)

    sol = find({})
    if sol is None:
        return False, set(), set()
    can_mine = {v for v, x in sol.items() if x}
    for v in frontier:
        if v not in can_mine:
            s = find({v: 1})
            if s is not None:
                can_mine |= {u for u, x in s.items() if x}
    return True, can_mine, set(frontier)


def safe_cells(h, w, nums, k):
    """규칙 k에서 확실히 안전한 닫힌 칸 (가능한 배치가 없으면 None)."""
    feasible, can_mine, frontier = analyze(h, w, nums, k)
    if not feasible:
        return None
    return frontier - can_mine


def annotate(h, w, nums, cell):
    adj = [(p, nums[p]) for p in neighbors(h, w, *cell, 8) if p in nums]
    if not adj:
        return f'{coord(*cell)} — 맞닿은 열린 칸 없음'
    return f'{coord(*cell)} — 맞닿은 열린 칸의 숫자: ' + ', '.join(f'{coord(*p)}={n}' for p, n in adj)


def trivial(h, w, nums, cell, k):
    """0인 열린 칸과 맞닿아 바로 안전한 칸인가."""
    return any(nums.get(p) == 0 for p in neighbors(h, w, *cell, k))


def random_open_board(rng):
    h, w = rng.randint(4, 6), rng.randint(4, 6)
    cells = [(r, c) for r in range(h) for c in range(w)]
    mines = set(rng.sample(cells, max(2, round(len(cells) * rng.uniform(0.15, 0.3)))))
    safe = [p for p in cells if p not in mines]
    opened = rng.sample(safe, max(3, round(len(safe) * rng.uniform(0.3, 0.6))))
    nums = {p: count(mines, h, w, *p, 8) for p in sorted(opened)}
    return h, w, nums


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 변형 짝: 지뢰가 다 보이는 판에서 한 칸의 숫자
    q_opts = [str(n) for n in range(9)]
    k2 = 0
    for i in range(per_stage):
        for _ in range(1000):
            h, w = rng.randint(4, 6), rng.randint(4, 6)
            cells = [(r, c) for r in range(h) for c in range(w)]
            mines = set(rng.sample(cells, round(len(cells) * rng.uniform(0.2, 0.35))))
            target = rng.choice([p for p in cells if p not in mines])
            a8, a4 = count(mines, h, w, *target, 8), count(mines, h, w, *target, 4)
            if a8 == 0 or (i % 4 != 3 and a8 == a4):
                continue
            break
        state = {'규칙': RULE_TEXT[8], '표기': NOTATION1, '판': render_full(h, w, mines)}
        q = f'지뢰가 없는 {coord(*target)} 칸에 적힐 숫자는?'
        base = make_item(rng, GAME, '1-판정', i, state, q, q_opts, str(a8))
        items.append(base)
        if a4 != a8:
            items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=RULE_TEXT[4]), q, q_opts, str(a4),
                                   original=str(a8), twin_of=base['id'], order=base['options']))
            k2 += 1
    # ③ 한 수: 보기 칸 중 확실히 안전한 칸이 정확히 하나
    q3 = '아직 열지 않은 칸 가운데 지뢰가 없다고 확실히 말할 수 있는 칸은?'
    want_twins = per_stage // 2
    twinned, plain = [], []
    for _ in range(20000):
        if len(twinned) >= want_twins and len(plain) >= per_stage - want_twins:
            break
        h, w, nums = random_open_board(rng)
        s8 = safe_cells(h, w, nums, 8)
        if not s8:
            continue
        s8 = sorted(p for p in s8 if not trivial(h, w, nums, p, 8))
        _, _, front8 = analyze(h, w, nums, 8)
        s4 = safe_cells(h, w, nums, 4) if len(twinned) < want_twins else None
        hidden = sorted(p for p in ((r, c) for r in range(h) for c in range(w)) if p not in nums)
        if s4:
            all4 = s4
            s4 = sorted(p for p in s4 if not trivial(h, w, nums, p, 4) and p not in safe_cells(h, w, nums, 8))
            s8x = [p for p in s8 if p not in all4]
            if s4 and s8x:
                a, b = rng.choice(s8x), rng.choice(s4)
                allsafe = safe_cells(h, w, nums, 8) | all4
                dis = [p for p in sorted(front8) if p not in allsafe]
                if len(dis) >= 2:
                    rng.shuffle(dis)
                    twinned.append((h, w, nums, a, b, dis[:rng.randint(2, 4)]))
                    continue
        if s8 and len(plain) < per_stage - want_twins:
            a = rng.choice(s8)
            dis = [p for p in sorted(front8) if p not in safe_cells(h, w, nums, 8)]
            if len(dis) >= 2:
                rng.shuffle(dis)
                plain.append((h, w, nums, a, None, dis[:rng.randint(2, 4)]))
    assert len(twinned) + len(plain) == per_stage, (len(twinned), len(plain))
    for i, (h, w, nums, a, b, dis) in enumerate(twinned + plain):
        cells = sorted([a] + ([b] if b else []) + dis)
        opts = [coord(*p) for p in cells]
        state = {'규칙': RULE_TEXT[8], '표기': NOTATION3, '판': render_open(h, w, nums)}
        base = make_item(rng, GAME, '3-한수(판)', i, state, q3, opts, coord(*a))
        items.append(base)
        ann = {coord(*p): annotate(h, w, nums, p) for p in cells}
        items.append(make_item(rng, GAME, '3-한수(주석)', i, state, q3, list(ann.values()), ann[coord(*a)],
                               order=[ann[o] for o in base['options']]))
        if b:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=RULE_TEXT[4]), q3, opts,
                                   coord(*b), original=coord(*a), twin_of=base['id'], order=base['options']))
    return items
