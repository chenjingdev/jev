"""스네이크.

판 표기는 틱택토 기준(행 A~, 열 1~). H 머리, o 몸, T 꼬리, * 먹이, # 벽, . 빈칸.
몸의 순서는 상황에 머리부터 꼬리까지 좌표로 적는다.
① 판정: 이번 턴에 바로 죽는(또는 바로 죽지 않는) 방향이 정확히 하나인 국면.
③ 한 수(판/주석): 앞으로 HORIZON턴 동안 살아남을 수 있는 첫 방향이 정확히 하나. 나머지 방향은 바로 죽거나,
   전수 탐색(먹이를 먹어 길어지는 것까지 포함)으로 HORIZON턴 안에 반드시 죽는다. 적어도 한 방향은 바로 죽지는 않는다.
④ 앞보기(판/주석): 먹이를 가장 적은 턴에 먹는 첫 방향이 정확히 하나(몸이 따라 움직이는 것을 포함한 상태 탐색).
② 변형: 판 가장자리를 넘으면 반대편으로 나오는 규칙. ④ 국면 중 첫 방향이 바뀌는 것만 짝으로 쓴다.
   (가장자리 규칙은 움직일 수 있는 길을 늘리기만 하므로 ①·③처럼 '살아남는 방향이 하나'인 문항은 답이 바뀌지 않는다.)
"""
from collections import deque
from functools import lru_cache

from .common import make_item

GAME = 'snake'
NAME = '스네이크'
FACET = '경로·위험 회피'

ROWS = 'ABCDEF'
DIRS = {'위': (-1, 0), '아래': (1, 0), '왼쪽': (0, -1), '오른쪽': (0, 1)}
DIR_NAMES = list(DIRS)
HORIZON = 8

_MOVE = ('뱀은 매 턴 머리를 위·아래·왼쪽·오른쪽 중 한 방향으로 한 칸 움직이고, 몸의 나머지 칸은 각각 바로 앞 칸이 있던 자리로 따라간다. ')
_EAT = ('머리가 먹이(*) 칸에 들어가면 먹이를 먹고, 그 턴에는 꼬리가 따라오지 않고 제자리에 남아 길이가 1 늘어난다. '
        '먹이는 하나뿐이고 먹은 뒤 새로 생기지 않는다.')
RULE_TEXT = {
    'wall': _MOVE + '머리가 판 밖으로 나가거나, 벽(#) 칸에 들어가거나, 움직이기 직전에 몸(꼬리 포함)이 있던 칸에 들어가면 죽는다. ' + _EAT,
    'wrap': _MOVE + '판 가장자리에서 판 밖 쪽으로 움직이면 죽지 않고 같은 행(또는 같은 열)의 반대쪽 끝 칸으로 나온다. '
                    '머리가 벽(#) 칸에 들어가거나, 움직이기 직전에 몸(꼬리 포함)이 있던 칸에 들어가면 죽는다. ' + _EAT,
}
NOTATION = ('판은 행 A~, 열 1~로 적는다. H는 뱀 머리, o는 뱀 몸, T는 뱀 꼬리, *는 먹이, #은 벽, "."은 빈칸이다. '
            '좌표는 "B2"처럼 행과 열을 붙여 쓴다. 위는 A 쪽, 왼쪽은 1 쪽이다.')


def coord(p):
    return ROWS[p[0]] + str(p[1] + 1)


class Board:
    def __init__(self, h, w, walls):
        self.h, self.w, self.walls = h, w, frozenset(walls)

    def move(self, body, food, d, rule):
        """(새 몸, 새 먹이) 또는 죽으면 None."""
        dr, dc = DIRS[d]
        r, c = body[0][0] + dr, body[0][1] + dc
        if not (0 <= r < self.h and 0 <= c < self.w):
            if rule == 'wall':
                return None
            r, c = r % self.h, c % self.w
        nh = (r, c)
        if nh in self.walls or nh in body:
            return None
        if nh == food:
            return (nh,) + body, None
        return (nh,) + body[:-1], food


def survives(bd, body, food, rule, t):
    @lru_cache(maxsize=None)
    def rec(body, food, t):
        if t == 0:
            return True
        return any((nx := bd.move(body, food, d, rule)) and rec(nx[0], nx[1], t - 1) for d in DIR_NAMES)
    return rec(body, food, t)


def survivable_dirs(bd, body, food, rule, horizon=HORIZON):
    out = []
    for d in DIR_NAMES:
        nx = bd.move(body, food, d, rule)
        if nx and survives(bd, nx[0], nx[1], rule, horizon - 1):
            out.append(d)
    return out


def food_first(bd, body, food, rule, limit=16):
    """먹이를 먹는 최소 턴 수와 그 최소를 이루는 첫 방향 집합. 못 먹으면 (None, set())."""
    start = (body, food)
    frontier = {}
    for d in DIR_NAMES:
        nx = bd.move(body, food, d, rule)
        if nx:
            frontier.setdefault(nx, set()).add(d)
    seen = set(frontier) | {start}
    for depth in range(1, limit + 1):
        eaten = set().union(*[f for (b, fd), f in frontier.items() if fd is None]) if frontier else set()
        if eaten:
            return depth, eaten
        nxt = {}
        for (b, fd), firsts in frontier.items():
            for d in DIR_NAMES:
                nx = bd.move(b, fd, d, rule)
                if nx and nx not in seen:
                    nxt.setdefault(nx, set()).update(firsts)
        seen |= set(nxt)
        frontier = nxt
        if not frontier:
            break
    return None, set()


def render(bd, body, food):
    def ch(p):
        if p == body[0]:
            return 'H'
        if p == body[-1]:
            return 'T'
        if p in body:
            return 'o'
        if p == food:
            return '*'
        if p in bd.walls:
            return '#'
        return '.'
    return '  ' + ' '.join(str(c + 1) for c in range(bd.w)) + '\n' + '\n'.join(
        ROWS[r] + ' ' + ' '.join(ch((r, c)) for c in range(bd.w)) for r in range(bd.h))


def situation(body, food):
    return ('뱀 몸(머리부터 꼬리까지): ' + ', '.join(coord(p) for p in body) + f'. 길이 {len(body)}. '
            + (f'먹이 위치: {coord(food)}.' if food else '먹이 없음.'))


def flood(bd, body, start):
    seen, st = {start}, [start]
    while st:
        r, c = st.pop()
        for dr, dc in DIRS.values():
            p = (r + dr, c + dc)
            if 0 <= p[0] < bd.h and 0 <= p[1] < bd.w and p not in seen and p not in bd.walls and p not in body:
                seen.add(p)
                st.append(p)
    return len(seen)


def target(bd, body, d):
    dr, dc = DIRS[d]
    p = (body[0][0] + dr, body[0][1] + dc)
    inside = 0 <= p[0] < bd.h and 0 <= p[1] < bd.w
    return p if inside else None


def content(bd, body, food, p):
    if p is None:
        return '판 밖'
    if p in body:
        return '꼬리 칸' if p == body[-1] else '몸 칸'
    if p in bd.walls:
        return '벽'
    return '먹이 칸' if p == food else '빈칸'


def annotate_space(bd, body, food, d):
    p = target(bd, body, d)
    what = content(bd, body, food, p)
    if what in ('빈칸', '먹이 칸'):
        return f'{d} — {coord(p)}: {what}, 이 칸과 이어진 빈 칸 수(지금 몸과 벽 제외, 이 칸 포함) {flood(bd, body, p)}'
    return f'{d} — ' + (f'{coord(p)}: ' if p else '') + what


def annotate_food(bd, body, food, d):
    p = target(bd, body, d)
    what = content(bd, body, food, p)
    if what in ('빈칸', '먹이 칸'):
        return f'{d} — {coord(p)}: {what}, 이 칸에서 먹이까지 맨해튼 거리 {abs(p[0] - food[0]) + abs(p[1] - food[1])}'
    return f'{d} — ' + (f'{coord(p)}: ' if p else '') + what


def random_position(rng, length=None, walls=None):
    h, w = rng.choice([(5, 5), (5, 6), (6, 5), (6, 6)])
    L = length or rng.randint(3, 7)
    cells = [(r, c) for r in range(h) for c in range(w)]
    for _ in range(100):
        body = [rng.choice(cells)]
        while len(body) < L:
            r, c = body[-1]
            nxt = [(r + dr, c + dc) for dr, dc in DIRS.values()]
            nxt = [p for p in nxt if 0 <= p[0] < h and 0 <= p[1] < w and p not in body]
            if not nxt:
                break
            body.append(rng.choice(nxt))
        if len(body) == L:
            break
    else:
        return None
    free = [p for p in cells if p not in body]
    nw = rng.randint(0, 4) if walls is None else walls
    ws = rng.sample(free, nw)
    free = [p for p in free if p not in ws]
    food = rng.choice(free)
    return Board(h, w, ws), tuple(body), food


def generate(rng, per_stage):
    items = []
    # ① 판정: 바로 죽는 방향 / 바로 죽지 않는 방향이 정확히 하나
    for i in range(per_stage):
        goal = 'dead' if i % 2 == 0 else 'alive'
        for _ in range(20000):
            pos = random_position(rng)
            if pos is None:
                continue
            bd, body, food = pos
            dead = [d for d in DIR_NAMES if bd.move(body, food, d, 'wall') is None]
            alive = [d for d in DIR_NAMES if d not in dead]
            pick = dead if goal == 'dead' else alive
            if len(pick) == 1 and len(pick) != 4:
                break
        else:
            raise AssertionError('no position for ①')
        state = {'규칙': RULE_TEXT['wall'], '표기': NOTATION, '판': render(bd, body, food), '상황': situation(body, food)}
        q = '이번 턴에 움직이면 바로 죽는 방향은?' if goal == 'dead' else '이번 턴에 움직여도 바로 죽지 않는 방향은?'
        items.append(make_item(rng, GAME, '1-판정', i, state, q, DIR_NAMES, pick[0]))
    # ③ 한 수: HORIZON턴 동안 살아남는 첫 방향이 하나뿐 (바로 죽지 않는 다른 방향이 적어도 하나)
    q3 = f'이번 턴을 포함해 앞으로 {HORIZON}턴 동안 죽지 않고 계속 움직일 수 있으려면 이번 턴에 어느 방향으로 가야 하는가?'
    picked = []
    for _ in range(20000):
        if len(picked) >= per_stage:
            break
        pos = random_position(rng, length=rng.randint(4, 8), walls=rng.randint(1, 5))
        if pos is None:
            continue
        bd, body, food = pos
        alive = [d for d in DIR_NAMES if bd.move(body, food, d, 'wall')]
        if len(alive) < 2:
            continue
        good = survivable_dirs(bd, body, food, 'wall')
        if len(good) != 1 or sum(u[3] == good[0] for u in picked) >= (per_stage + 3) // 4 + 1:
            continue
        doomed = [d for d in alive if d != good[0]]
        if all(flood(bd, body, target(bd, body, d)) == 1 for d in doomed) and rng.random() < 0.6:
            continue  # 한 칸짜리 막다른 곳보다 넓은 함정을 더 많이
        picked.append((bd, body, food, good[0]))
    assert len(picked) == per_stage, len(picked)
    for i, (bd, body, food, good) in enumerate(picked):
        state = {'규칙': RULE_TEXT['wall'], '표기': NOTATION, '판': render(bd, body, food), '상황': situation(body, food)}
        base = make_item(rng, GAME, '3-한수(판)', i, state, q3, DIR_NAMES, good)
        items.append(base)
        ann = {d: annotate_space(bd, body, food, d) for d in DIR_NAMES}
        items.append(make_item(rng, GAME, '3-한수(주석)', i, state, q3, list(ann.values()), ann[good],
                               order=[ann[d] for d in base['options']]))
    # ④ 앞보기 + ② 변형 짝: 먹이를 가장 빨리 먹는 첫 방향
    q4 = '먹이를 가장 적은 턴 만에 먹으려면 이번 턴에 어느 방향으로 가야 하는가?'
    want_twins = per_stage // 2
    twinned, plain = [], []
    for _ in range(20000):
        if len(twinned) >= want_twins and len(plain) >= per_stage - want_twins:
            break
        pos = random_position(rng, walls=rng.randint(0, 3))
        if pos is None:
            continue
        bd, body, food = pos
        n, firsts = food_first(bd, body, food, 'wall')
        if n is None or n < 3 or len(firsts) != 1:
            continue
        b = next(iter(firsts))
        if sum(u[3] == b for u in twinned + plain) >= (per_stage + 3) // 4 + 1:
            continue
        head = body[0]
        if abs(head[0] - food[0]) + abs(head[1] - food[1]) == n and rng.random() < 0.7:
            continue  # 몸을 피해 돌아가야 하는 국면을 더 많이
        tn, tf = food_first(bd, body, food, 'wrap')
        t = next(iter(tf)) if tn is not None and len(tf) == 1 else None
        if t is not None and t != b and len(twinned) < want_twins:
            twinned.append((bd, body, food, b, t))
        elif (t is None or t == b) and len(plain) < per_stage - want_twins:
            plain.append((bd, body, food, b, None))
    assert len(twinned) + len(plain) == per_stage, (len(twinned), len(plain))
    for i, (bd, body, food, b, t) in enumerate(twinned + plain):
        state = {'규칙': RULE_TEXT['wall'], '표기': NOTATION, '판': render(bd, body, food), '상황': situation(body, food)}
        base = make_item(rng, GAME, '4-앞보기(판)', i, state, q4, DIR_NAMES, b)
        items.append(base)
        ann = {d: annotate_food(bd, body, food, d) for d in DIR_NAMES}
        items.append(make_item(rng, GAME, '4-앞보기(주석)', i, state, q4, list(ann.values()), ann[b],
                               order=[ann[d] for d in base['options']]))
        if t:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=RULE_TEXT['wrap']), q4, DIR_NAMES,
                                   t, original=b, twin_of=base['id'], order=base['options']))
    return items
