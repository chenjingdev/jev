"""오목 퍼즐 (9×9 판, 자유룰: 다섯 이상 이으면 승).

판 표기는 틱택토와 같다: 행 A~I(A가 맨 위), 열 1~9, 빈칸 '.', 좌표 'E5'.

① 판정: 지금 판에서 이긴 사람(또는 진 사람)은? (X / O / 아직 없음)
③ 한 수: "X의 수 두 번(이번 수 포함) 안에 O가 어떻게 두든 반드시 이기는 자리"가 판 전체에서 하나뿐인 국면 중,
   그 자리가 바로 이기는 자리이거나 O가 바로 이길 자리를 막는 자리인 것.
④ 앞보기: 같은 질문에서 그 자리가 바로 이기지도, 막지도 않는 자리(열린 넷이나 쌍사를 만드는 자리)인 것.
   반드시 이기는지는 정확히 판정한다: X가 바로 이기거나, 둔 뒤 O가 바로 이길 자리가 없고 X가 바로 이길 빈칸이
   둘 이상이면 이긴다(O는 한 곳만 막을 수 있다). 그 밖에는 O가 막거나 먼저 이긴다. 판 전체 빈칸을 다 검사해
   유일성을 확인하고, 보기는 그 자리와 전술적으로 관련된 자리(바로 이기는 자리, 막는 자리, 넷을 만드는 자리)와
   가까운 빈칸으로 12개 이하를 뽑는다.
② 변형: "정확히 다섯 개를 이어야 이긴다. 여섯 개 이상은 이긴 것으로 치지 않는다". ①은 여섯 이상으로만 이긴 판,
   ③·④는 변형 규칙에서도 반드시 이기는 자리가 하나이고 달라지는 국면만 짝으로 쓴다.
"""
from .common import make_item

GAME = 'gomoku'
NAME = '오목 퍼즐'
FACET = '수 읽기'

N = 9
ROWS = 'ABCDEFGHI'
CELLS = [r + str(c + 1) for r in ROWS for c in range(N)]
DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]
_COMMON = '9×9 판의 빈칸에 X와 O가 번갈아 돌을 하나씩 놓는다. X가 먼저 둔다. '
RULE_TEXT = {
    'free': _COMMON + '가로·세로·대각선 중 한 줄로 자기 돌을 다섯 개 이상 빈틈없이 이으면 그 즉시 이긴다.',
    'exact': _COMMON + '가로·세로·대각선 중 한 줄로 자기 돌을 정확히 다섯 개 빈틈없이 이으면 그 즉시 이긴다. '
                       '여섯 개 이상 이어진 것은 이긴 것으로 치지 않는다.',
}
NOTATION = '판은 행 A~I(A가 맨 위), 열 1~9로 적고 빈칸은 "."이다. 좌표는 "E5"처럼 행과 열을 붙여 쓴다.'


def render(board):
    return '  ' + ' '.join(str(c + 1) for c in range(N)) + '\n' + '\n'.join(
        r + ' ' + ' '.join(board[i * N:(i + 1) * N]) for i, r in enumerate(ROWS))


def parse(rows):
    assert len(rows) == N and all(len(r) == N for r in rows)
    return ''.join(rows)


def _step(i, d, k):
    r, c = i // N + d[0] * k, i % N + d[1] * k
    return r * N + c if 0 <= r < N and 0 <= c < N else None


def run_len(board, i, d, mark):
    """i 칸을 mark로 보고 방향 d로 이어진 mark 돌 수 (양쪽 합)."""
    n = 1
    for sgn in (1, -1):
        k = 1
        while True:
            j = _step(i, d, sgn * k)
            if j is None or board[j] != mark:
                break
            n += 1
            k += 1
    return n


def _wins(length, rule):
    return length >= 5 if rule == 'free' else length == 5


def wins_at(board, i, mark, rule):
    """빈칸 i에 mark를 놓으면 이기는가."""
    return board[i] == '.' and any(_wins(run_len(board, i, d, mark), rule) for d in DIRS)


def win_points(board, mark, rule):
    return {i for i in range(N * N) if wins_at(board, i, mark, rule)}


def winner(board, rule):
    """판 위에 이미 이긴 줄이 있는 쪽 (한 방향의 최대 연속 길이로 판단)."""
    for i, m in enumerate(board):
        if m == '.':
            continue
        for d in DIRS:
            prev = _step(i, d, -1)
            if prev is not None and board[prev] == m:
                continue   # 연속 구간의 시작 칸에서만 센다
            if _wins(run_len(board, i, d, m), rule):
                return m
    return None


def longest(board, mark):
    return max((run_len(board, i, d, mark) for i, m in enumerate(board) if m == mark for d in DIRS), default=0)


def place(board, i, mark):
    return board[:i] + mark + board[i + 1:]


def _near_lines(i):
    out = set()
    for d in DIRS:
        for k in range(-5, 6):
            j = _step(i, d, k)
            if j is not None:
                out.add(j)
    return out


def x_after(board, p, rule, base_x):
    """X가 p에 둔 뒤 X가 바로 이길 수 있는 빈칸 집합 (p를 지나는 줄 근처만 다시 계산)."""
    b = place(board, p, 'X')
    near = _near_lines(p)
    keep = {q for q in base_x if q != p and q not in near}
    return b, keep | {q for q in near if wins_at(b, q, 'X', rule)}


def forced_wins(board, rule):
    """X 차례. X의 수 두 번(이번 수 포함) 안에 O가 어떻게 두든 반드시 이기는 자리 목록.
    바로 이기거나, 둔 뒤 O가 바로 이길 빈칸이 없고 X가 바로 이길 빈칸이 둘 이상이면 이긴다."""
    base_x, base_o = win_points(board, 'X', rule), win_points(board, 'O', rule)
    out = []
    for p in range(N * N):
        if board[p] != '.':
            continue
        if p in base_x:
            out.append(p)
            continue
        if base_o - {p}:
            continue
        _, xs = x_after(board, p, rule, base_x)
        if len(xs) >= 2:
            out.append(p)
    return out


def annotate(board, p, rule='free'):
    b = place(board, p, 'X')
    top = max(run_len(board, p, d, 'X') for d in DIRS)
    xs = len(win_points(b, 'X', rule))
    os_ = len(win_points(b, 'O', rule))
    return (f'{CELLS[p]} — 여기 두면 이 돌을 지나는 가장 긴 X 연속 {top}개, 그 뒤 X가 바로 이길 수 있는 빈칸 {xs}곳, '
            f'O가 바로 이길 수 있는 빈칸 {os_}곳')


def verdict(board, rule, ask):
    w = winner(board, rule)
    if w is None:
        return '아직 없음'
    return w if ask == 'win' else ('O' if w == 'X' else 'X')


# ---------- 국면 만들기 ----------
PATTERNS = ['XXXX', 'XXX', 'XX.X', 'XXX.XX', 'XX.XX', 'X.XXX', 'OOOO', 'OOO', 'OOO.OO', 'OO.OO']


def _plant(rng, board, pat):
    for _ in range(50):
        d = rng.choice(DIRS)
        s = rng.randrange(N * N)
        cells = [_step(s, d, k) for k in range(len(pat))]
        if None in cells or any(board[j] != '.' for j in cells):
            continue
        b = list(board)
        for j, ch in zip(cells, pat):
            b[j] = ch
        return ''.join(b)
    return board


def _scatter(rng, board, mark, k):
    empt = [i for i in range(N * N) if board[i] == '.' and 1 <= i // N <= 7 and 1 <= i % N <= 7]
    for i in rng.sample(empt, min(k, len(empt))):
        board = place(board, i, mark)
    return board


OPEN3 = ['O.XXX..', '..XXX.O', 'O.X.XX..', '..XX.X.O', 'OXXX..', '..XXXO']
RECIPES = {
    'mixed': lambda r: r.sample(PATTERNS, r.randint(2, 3)),
    'open3': lambda r: [r.choice(OPEN3)] + r.sample(['OOO', 'OO.O', 'O.OO', 'XX', 'X.X'], 2),
    'over': lambda r: [r.choice(['XXX.XX', 'XX.XXX']), r.choice(['OOO.OO', 'OO.OOO']), r.choice(OPEN3)],
}


def random_position(rng, recipe):
    """X 차례(X와 O 돌 수가 같음)이고 아직 아무도 이기지 않은 전술 국면. recipe는 심을 돌 모양 묶음."""
    while True:
        b = '.' * (N * N)
        for pat in RECIPES[recipe](rng):
            b = _plant(rng, b, pat)
        diff = b.count('X') - b.count('O')
        extra = rng.randint(1, 4)
        b = _scatter(rng, b, 'X', extra + max(0, -diff))
        b = _scatter(rng, b, 'O', extra + max(0, diff))
        if b.count('X') == b.count('O') and winner(b, 'free') is None:
            return b


def shortlist(rng, board, must, rule_list=('free', 'exact'), size=10):
    """보기 후보: 꼭 넣을 자리 + 양쪽의 바로 이기는 자리 + 넷을 만드는 자리 + 돌 가까운 빈칸."""
    rel = list(must)
    for rule in rule_list:
        for mark in ('X', 'O'):
            rel += sorted(win_points(board, mark, rule))
        base_x = win_points(board, 'X', rule)
        rel += [p for p in range(N * N) if board[p] == '.' and p not in base_x
                and x_after(board, p, rule, base_x)[1]]
    out = []
    for p in rel:
        if p not in out:
            out.append(p)
    out = out[:12]
    near = [p for p in range(N * N) if board[p] == '.' and p not in out and any(
        (j := _step(p, d, s)) is not None and board[j] != '.' for d in DIRS for s in (1, -1))]
    rng.shuffle(near)
    out += near[:max(0, size - len(out))]
    return out


def _finished(rng, kind):
    """kind: 'over' (여섯 이상으로만 이긴 판), 'five' (정확히 다섯으로 이긴 판), 'none'."""
    while True:
        b = '.' * (N * N)
        w = rng.choice('XO')
        if kind != 'none':
            b = _plant(rng, b, w * (rng.choice((6, 7)) if kind == 'over' else 5))
        for pat in rng.sample(PATTERNS[1:5] + PATTERNS[7:], 2):
            b = _plant(rng, b, pat)
        # 이긴 쪽이 마지막에 뒀다: X가 이겼으면 X가 하나 많고, O가 이겼으면 같다. 'none'은 X 차례로 둔다.
        want_diff = 1 if (kind != 'none' and w == 'X') else 0
        extra = rng.randint(4, 10)
        diff = b.count('X') - b.count('O')
        b = _scatter(rng, b, 'X', extra + max(0, want_diff - diff))
        b = _scatter(rng, b, 'O', extra + max(0, diff - want_diff))
        if b.count('X') - b.count('O') != want_diff:
            continue
        runs = {m: longest(b, m) for m in 'XO'}
        if kind == 'none' and max(runs.values()) < 5:
            return b
        lo = 'O' if w == 'X' else 'X'
        if kind == 'five' and runs[w] == 5 and runs[lo] < 5:
            return b
        if kind == 'over' and runs[w] >= 6 and runs[lo] < 5 and winner(b, 'exact') is None:
            return b


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 짝: 여섯 이상으로만 이긴 판(변형에서는 '아직 없음')과 그 밖의 판
    opts = ['X', 'O', '아직 없음']
    questions = {'win': '지금 판에서 이긴 사람은?', 'lose': '지금 판에서 진 사람은?'}
    k2 = 0
    for n in range(per_stage):
        kind = 'over' if n % 2 == 0 else ('five' if n % 4 == 1 else 'none')
        b = _finished(rng, kind)
        ask = 'lose' if n % 4 in (1, 2) else 'win'
        state = {'규칙': RULE_TEXT['free'], '표기': NOTATION, '판': render(b)}
        base = make_item(rng, GAME, '1-판정', n, state, questions[ask], opts, verdict(b, 'free', ask))
        items.append(base)
        if verdict(b, 'free', ask) != verdict(b, 'exact', ask):
            items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=RULE_TEXT['exact']), questions[ask], opts,
                                   verdict(b, 'exact', ask), original=verdict(b, 'free', ask), twin_of=base['id'],
                                   order=base['options']))
            k2 += 1
    # ③·④: 반드시 이기는 자리가 판 전체에서 하나뿐인 국면
    q = ('X 차례다. X가 이번 수와 다음 수, 두 번 안에(그 사이 O는 한 번 둔다) O가 어떻게 두든 반드시 이기려면 '
         '이번에 어디에 둬야 하는가?')
    want = {'3-한수': per_stage, '4-앞보기': per_stage}
    need_twin = {'3-한수': max(1, per_stage // 3), '4-앞보기': 0}
    pools = {s: {'twin': [], 'plain': []} for s in want}
    tries = 0
    while any(len(p['twin']) < need_twin[s] or len(p['twin']) + len(p['plain']) < want[s] for s, p in pools.items()):
        tries += 1
        assert tries < 100000
        b = random_position(rng, ('mixed', 'open3', 'over')[tries % 3])
        f = forced_wins(b, 'free')
        if len(f) != 1:
            continue
        p = f[0]
        tactical = p in win_points(b, 'X', 'free') or p in win_points(b, 'O', 'free')
        stage = '3-한수' if tactical else '4-앞보기'
        fe = forced_wins(b, 'exact')
        twin = fe[0] if len(fe) == 1 and fe[0] != p else None
        pool = pools[stage]
        if twin is not None and len(pool['twin']) < per_stage // 2:
            pool['twin'].append((b, p, twin))
        elif twin is None and len(pool['plain']) < want[stage] - need_twin[stage]:
            pool['plain'].append((b, p, None))
    for stage, pool in pools.items():
        chosen = (pool['twin'] + pool['plain'])[:want[stage]]
        for n, (b, p, twin) in enumerate(chosen):
            cands = shortlist(rng, b, [p] + ([twin] if twin is not None else []))
            # 보기 안에서도 판 전체에서도 반드시 이기는 자리는 하나뿐이다
            assert [c for c in cands if c in forced_wins(b, 'free')] == [p]
            names = [CELLS[c] for c in cands]
            state = {'규칙': RULE_TEXT['free'], '표기': NOTATION, '판': render(b)}
            base = make_item(rng, GAME, f'{stage}(판)', n, state, q, names, CELLS[p])
            items.append(base)
            ann = {CELLS[c]: annotate(b, c) for c in cands}
            items.append(make_item(rng, GAME, f'{stage}(주석)', n, state, q, list(ann.values()), ann[CELLS[p]],
                                   order=[ann[o] for o in base['options']]))
            if twin is not None:
                items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=RULE_TEXT['exact']), q, names,
                                       CELLS[twin], original=CELLS[p], twin_of=base['id'], order=base['options']))
                k2 += 1
    return items
