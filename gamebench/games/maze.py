"""미로 탈출.

판: '#' 벽, '.' 빈칸, 'S' 출발, 'E' 출구, 'K' 열쇠, 'D' 문. 행 A~, 열 1~ (틱택토 표기).
① 판정: S에서 주어진 방향으로 한 칸 움직일 수 있는가.
③ 한 수(판/주석): 최단 경로가 정확히 하나인 미로에서 그 경로의 첫 이동 방향.
   (주석)은 방향마다 도착 칸의 내용과 그 칸에서 E까지의 맨해튼 거리(벽 무시)를 붙인다.
② 변형: D가 잠겨 있지 않은 규칙. ①은 D 쪽으로 움직이는 문항, ③은 최단 경로의 첫 방향이 바뀌는 미로만.
"""
from collections import deque

from .common import make_item

GAME = 'maze'
NAME = '미로 탈출'
FACET = '경로·위험 회피'

DIRS = {'위': (-1, 0), '아래': (1, 0), '왼쪽': (0, -1), '오른쪽': (0, 1)}
DIR_NAMES = list(DIRS)
RULE_TEXT = {
    'locked': 'S에서 출발해 한 번에 위·아래·왼쪽·오른쪽 중 한 방향으로 한 칸씩 움직인다. 판 밖과 벽(#)으로는 움직일 수 없다. '
              'D는 잠긴 문이다. K 칸에 한 번이라도 들어가면 열쇠를 얻고, 열쇠를 얻은 뒤에만 D 칸에 들어갈 수 있다. '
              'E 칸에 들어가면 탈출한다.',
    'open': 'S에서 출발해 한 번에 위·아래·왼쪽·오른쪽 중 한 방향으로 한 칸씩 움직인다. 판 밖과 벽(#)으로는 움직일 수 없다. '
            'D는 열려 있는 문이라 빈칸처럼 언제든 들어갈 수 있다. K 칸도 빈칸처럼 지나가며 아무 일도 일어나지 않는다. '
            'E 칸에 들어가면 탈출한다.',
}
NOTATION = ('판은 행 A~, 열 1~로 적는다. "#"은 벽, "."은 빈칸, S는 출발 칸, E는 출구, K는 열쇠 칸, D는 문 칸이다. '
            '좌표는 "B2"처럼 행과 열을 붙여 쓴다. 위는 A 쪽, 왼쪽은 1 쪽이다.')
CONTENT = {'.': '빈칸', '#': '벽', 'S': '출발 칸', 'E': '출구', 'K': '열쇠 칸', 'D': '문 칸'}


def coord(r, c):
    return 'ABCDEFGHIJ'[r] + str(c + 1)


def render(grid):
    w = len(grid[0])
    return '  ' + ' '.join(str(c + 1) for c in range(w)) + '\n' + '\n'.join(
        'ABCDEFGHIJ'[r] + ' ' + ' '.join(row) for r, row in enumerate(grid))


def find(grid, ch):
    return next((r, c) for r, row in enumerate(grid) for c, x in enumerate(row) if x == ch)


def can_enter(grid, r, c, key, rule):
    if not (0 <= r < len(grid) and 0 <= c < len(grid[0])):
        return False
    x = grid[r][c]
    if x == '#':
        return False
    if x == 'D' and rule == 'locked' and not key:
        return False
    return True


def step(grid, state, d, rule):
    r, c, key = state
    dr, dc = DIRS[d]
    nr, nc = r + dr, c + dc
    if not can_enter(grid, nr, nc, key, rule):
        return None
    return nr, nc, key or (rule == 'locked' and grid[nr][nc] == 'K')


def shortest(grid, rule):
    """(최단 길이, 최단 경로 수, 최단 경로들의 첫 방향 집합). 출구에 못 가면 None."""
    sr, sc = find(grid, 'S')
    start = (sr, sc, False)
    dist, count, first = {start: 0}, {start: 1}, {start: set()}
    q = deque([start])
    best = None
    while q:
        s = q.popleft()
        if best is not None and dist[s] >= best:
            continue
        if grid[s[0]][s[1]] == 'E':
            continue
        for d in DIR_NAMES:
            t = step(grid, s, d, rule)
            if t is None:
                continue
            f = {d} if s == start else first[s]
            if t not in dist:
                dist[t], count[t], first[t] = dist[s] + 1, count[s], set(f)
                q.append(t)
                if grid[t[0]][t[1]] == 'E' and best is None:
                    best = dist[t]
            elif dist[t] == dist[s] + 1:
                count[t] += count[s]
                first[t] |= f
    if best is None:
        return None
    ends = [s for s in dist if grid[s[0]][s[1]] == 'E' and dist[s] == best]
    return best, sum(count[s] for s in ends), set().union(*(first[s] for s in ends))


def unique_first(grid, rule):
    res = shortest(grid, rule)
    if res is None or res[1] != 1:
        return None
    return next(iter(res[2]))


def annotate(grid, d):
    sr, sc = find(grid, 'S')
    er, ec = find(grid, 'E')
    dr, dc = DIRS[d]
    r, c = sr + dr, sc + dc
    if not (0 <= r < len(grid) and 0 <= c < len(grid[0])):
        return f'{d} — 판 밖'
    return f'{d} — {coord(r, c)}: {CONTENT[grid[r][c]]}, 이 칸에서 E까지 맨해튼 거리(벽 무시) {abs(er - r) + abs(ec - c)}'


def random_grid(rng):
    h, w = rng.randint(5, 7), rng.randint(5, 7)
    grid = [['#' if rng.random() < 0.33 else '.' for _ in range(w)] for _ in range(h)]
    cells = [(r, c) for r in range(h) for c in range(w)]
    picks = rng.sample(cells, 4)
    for ch, (r, c) in zip('SEKD', picks):
        grid[r][c] = ch
    return [''.join(row) for row in grid]


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 변형 짝: S에서 한 방향으로 움직일 수 있는가
    q_opts = ['움직일 수 있다', '막혀 있다']
    kinds = ['D', '#', '.', 'out', 'D', 'K', 'D', '.', '#', 'D']
    k2 = 0
    for i in range(per_stage):
        want = kinds[i % len(kinds)]
        for _ in range(5000):
            g = random_grid(rng)
            sr, sc = find(g, 'S')
            ds = []
            for d, (dr, dc) in DIRS.items():
                r, c = sr + dr, sc + dc
                inside = 0 <= r < len(g) and 0 <= c < len(g[0])
                if (want == 'out' and not inside) or (inside and g[r][c] == want):
                    ds.append(d)
            if ds:
                d = rng.choice(ds)
                break
        else:
            raise AssertionError('no maze for ①')
        state = {'규칙': RULE_TEXT['locked'], '표기': NOTATION, '판': render(g)}
        q = f'S에서 출발하자마자 {d}으로 한 칸 움직일 수 있는가?' if d in ('왼쪽', '오른쪽') else \
            f'S에서 출발하자마자 {d}로 한 칸 움직일 수 있는가?'
        ans = lambda rule: q_opts[0] if step(g, (sr, sc, False), d, rule) else q_opts[1]
        base = make_item(rng, GAME, '1-판정', i, state, q, q_opts, ans('locked'))
        items.append(base)
        if ans('open') != ans('locked'):
            items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=RULE_TEXT['open']), q, q_opts,
                                   ans('open'), original=ans('locked'), twin_of=base['id'], order=base['options']))
            k2 += 1
    # ③ 한 수: 최단 경로가 하나뿐인 미로. 절반은 문이 열린 규칙에서 첫 방향이 달라지는 미로.
    q3 = 'S에서 가장 적은 이동으로 E에 닿으려 한다. 첫 이동은 어느 방향인가?'
    want_twins = per_stage // 2
    twinned, plain = [], []
    for _ in range(200000):
        if len(twinned) >= want_twins and len(plain) >= per_stage - want_twins:
            break
        g = random_grid(rng)
        b = unique_first(g, 'locked')
        if b is None or shortest(g, 'locked')[0] < 4:
            continue
        if sum(u[1] == b for u in twinned + plain) >= (per_stage + 3) // 4 + 1:
            continue
        t = unique_first(g, 'open')
        if t is not None and t != b and len(twinned) < want_twins:
            twinned.append((g, b, t))
        elif (t is None or t == b) and len(plain) < per_stage - want_twins:
            plain.append((g, b, None))
    assert len(twinned) + len(plain) == per_stage, (len(twinned), len(plain))
    for i, (g, b, t) in enumerate(twinned + plain):
        state = {'규칙': RULE_TEXT['locked'], '표기': NOTATION, '판': render(g)}
        base = make_item(rng, GAME, '3-한수(판)', i, state, q3, DIR_NAMES, b)
        items.append(base)
        ann = {d: annotate(g, d) for d in DIR_NAMES}
        items.append(make_item(rng, GAME, '3-한수(주석)', i, state, q3, list(ann.values()), ann[b],
                               order=[ann[d] for d in base['options']]))
        if t:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=RULE_TEXT['open']), q3, DIR_NAMES,
                                   t, original=b, twin_of=base['id'], order=base['options']))
    return items
