"""오셀로 (6×6 판).

판 표기는 틱택토와 같다: 행 A~F(A가 맨 위), 열 1~6, 빈칸 '.', 좌표 'B2'. X와 O가 돌 색 대신 쓰인다.

① 판정: 한 자리에 두면 뒤집히는 돌 수 / 보기 중 둘 수 있는(없는) 자리.
③ 한 수: X 차례에서 돌을 가장 많이 뒤집는 자리(최댓값이 하나인 국면). 보기는 X가 둘 수 있는 자리 전부.
④ 앞보기: X가 둔 뒤 O가 X의 돌을 가장 많이 줄이도록 응수할 때, 그 뒤 X의 돌이 가장 많이 남는 자리.
   가장 많이 뒤집는 자리와 다른 국면만 쓴다(한 수 앞을 봐야 풀린다). 탐색은 2수 전수 조사.
② 변형: "가로·세로로만 뒤집는다(대각선 방향으로는 뒤집지 않는다)". ①의 뒤집히는 돌 수와 ③의 최다 뒤집기 자리가
   달라지는 국면만 짝으로 쓴다.
"""
from .common import make_item

GAME = 'othello'
NAME = '오셀로'
FACET = '수 읽기'

N = 6
ROWS = 'ABCDEF'
CELLS = [r + str(c + 1) for r in ROWS for c in range(N)]
STRAIGHT = [(0, 1), (0, -1), (1, 0), (-1, 0)]
DIAG = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
DIRS = {'standard': STRAIGHT + DIAG, 'nodiag': STRAIGHT}

_TAIL = ('상대 돌을 하나 이상 뒤집을 수 있는 자리에만 둘 수 있다. 둘 수 있는 자리가 없으면 차례를 넘긴다. '
         '더 둘 곳이 없으면 돌이 많은 쪽이 이긴다.')
RULE_TEXT = {
    'standard': '6×6 판에 X와 O가 번갈아 돌을 하나씩 놓는다. 돌을 놓은 자리에서 가로·세로·대각선 여덟 방향을 각각 보아, '
                '상대 돌이 한 개 이상 빈틈없이 이어지고 그 바로 다음에 자기 돌이 있으면 그 사이의 상대 돌을 모두 뒤집어 '
                '자기 돌로 만든다. ' + _TAIL,
    'nodiag': '6×6 판에 X와 O가 번갈아 돌을 하나씩 놓는다. 돌을 놓은 자리에서 가로·세로 네 방향만 각각 보아, '
              '상대 돌이 한 개 이상 빈틈없이 이어지고 그 바로 다음에 자기 돌이 있으면 그 사이의 상대 돌을 모두 뒤집어 '
              '자기 돌로 만든다. 대각선 방향으로는 뒤집지 않는다. ' + _TAIL,
}
NOTATION = '판은 행 A~F(A가 맨 위), 열 1~6으로 적고 빈칸은 "."이다. 좌표는 "B2"처럼 행과 열을 붙여 쓴다.'
START = '.' * 14 + 'OX' + '....' + 'XO' + '.' * 14   # C3=O, C4=X, D3=X, D4=O


def render(board):
    return '  ' + ' '.join(str(c + 1) for c in range(N)) + '\n' + '\n'.join(
        r + ' ' + ' '.join(board[i * N:(i + 1) * N]) for i, r in enumerate(ROWS))


def other(p):
    return 'O' if p == 'X' else 'X'


def flips_by_dir(board, i, p, rule):
    """p가 i에 두면 방향별로 뒤집히는 칸 목록 {방향: [칸...]}. 빈칸이 아니면 {}."""
    if board[i] != '.':
        return {}
    r0, c0 = divmod(i, N)
    out = {}
    for dr, dc in DIRS[rule]:
        run, r, c = [], r0 + dr, c0 + dc
        while 0 <= r < N and 0 <= c < N and board[r * N + c] == other(p):
            run.append(r * N + c)
            r, c = r + dr, c + dc
        if run and 0 <= r < N and 0 <= c < N and board[r * N + c] == p:
            out[(dr, dc)] = run
    return out


def flips(board, i, p, rule):
    return [j for run in flips_by_dir(board, i, p, rule).values() for j in run]


def legal(board, p, rule):
    return [i for i in range(N * N) if flips(board, i, p, rule)]


def play(board, i, p, rule):
    b = list(board)
    b[i] = p
    for j in flips(board, i, p, rule):
        b[j] = p
    return ''.join(b)


def count_text(k):
    return '둘 수 없다' if k == 0 else f'{k}개'


COUNT_OPTS = [count_text(k) for k in range(8)]


def most_flips(board, rule, options):
    """보기(칸 번호) 중 X가 뒤집는 돌 수가 가장 많은 칸. 하나가 아니면 None."""
    sc = {i: len(flips(board, i, 'X', rule)) for i in options}
    top = max(sc.values())
    best = [i for i, v in sc.items() if v == top]
    return best[0] if len(best) == 1 and top > 0 else None


def after_reply(board, i, rule):
    """X가 i에 둔 뒤 O가 X의 돌을 가장 많이 줄이도록 응수했을 때 X 돌 수 (O가 둘 곳이 없으면 그대로)."""
    b = play(board, i, 'X', rule)
    replies = legal(b, 'O', rule)
    if not replies:
        return b.count('X')
    return min(play(b, j, 'O', rule).count('X') for j in replies)


def lookahead_best(board, rule):
    sc = {i: after_reply(board, i, rule) for i in legal(board, 'X', rule)}
    top = max(sc.values())
    best = [i for i, v in sc.items() if v == top]
    return (best[0] if len(best) == 1 else None), sc


DIR_KO = {'가로': STRAIGHT[:2], '세로': STRAIGHT[2:], '대각선': DIAG}


def annotate3(board, i):
    fd = flips_by_dir(board, i, 'X', 'standard')
    parts = ', '.join(f'{k} {sum(len(fd.get(d, [])) for d in ds)}개' for k, ds in DIR_KO.items())
    return f'{CELLS[i]} — 여기 두면 뒤집히는 O 돌: {parts}'


def annotate4(board, i):
    b = play(board, i, 'X', 'standard')
    replies = legal(b, 'O', 'standard')
    most = max((len(flips(b, j, 'O', 'standard')) for j in replies), default=0)
    return (f'{CELLS[i]} — 여기 두면 O 돌 {len(flips(board, i, "X", "standard"))}개가 뒤집혀 X 돌이 {b.count("X")}개가 된다. '
            f'그 뒤 O가 둘 수 있는 자리 {len(replies)}곳, 그중 가장 많이 뒤집는 수는 X 돌 {most}개를 뒤집는다')


def playout(rng, moves):
    """시작 판에서 무작위로 moves수 둔다 (넘김 포함). (판, 다음 차례) 또는 게임이 끝나면 None."""
    b, p = START, 'X'
    for _ in range(moves):
        opts = legal(b, p, 'standard')
        if not opts:
            p = other(p)
            opts = legal(b, p, 'standard')
            if not opts:
                return None
        b = play(b, rng.choice(opts), p, 'standard')
        p = other(p)
    if not legal(b, p, 'standard'):
        return None
    return b, p


def x_positions(rng, lo, hi):
    """X 차례인 무작위 국면을 끝없이 낸다 (같은 판은 한 번만)."""
    seen = set()
    while True:
        r = playout(rng, rng.randint(lo, hi))
        if r is None or r[1] != 'X' or r[0] in seen:
            continue
        seen.add(r[0])
        yield r[0]


def generate(rng, per_stage):
    items = []
    state_of = lambda b, rule='standard': {'규칙': RULE_TEXT[rule], '표기': NOTATION, '판': render(b)}
    # ① 판정: 짝수 번호는 뒤집히는 돌 수(대각선 뒤집기가 있어 ② 짝이 된다), 홀수 번호는 둘 수 있는/없는 자리 고르기
    gen = x_positions(rng, 4, 16)
    k2 = 0
    for n in range(per_stage):
        while True:
            b = next(gen)
            if n % 2 == 0:
                cands = [i for i in legal(b, 'X', 'standard')
                         if len(flips(b, i, 'X', 'standard')) <= 7
                         and len(flips(b, i, 'X', 'nodiag')) != len(flips(b, i, 'X', 'standard'))]
                if not cands:
                    continue
                i = rng.choice(cands)
                q = f'X 차례다. X가 {CELLS[i]}에 두면 뒤집히는 O 돌은 몇 개인가?'
                std, nod = (count_text(len(flips(b, i, 'X', r))) for r in ('standard', 'nodiag'))
                base = make_item(rng, GAME, '1-판정', n, state_of(b), q, COUNT_OPTS, std)
                items.append(base)
                items.append(make_item(rng, GAME, '2-변형', k2, state_of(b, 'nodiag'), q, COUNT_OPTS, nod,
                                       original=std, twin_of=base['id'], order=base['options']))
                k2 += 1
                break
            ok = set(legal(b, 'X', 'standard'))
            near = [i for i in range(N * N) if b[i] == '.' and i not in ok and any(
                0 <= i // N + dr < N and 0 <= i % N + dc < N and b[(i // N + dr) * N + i % N + dc] != '.'
                for dr, dc in STRAIGHT + DIAG)]
            want_legal = n % 4 == 1
            if want_legal and len(near) >= 3:
                opts = [rng.choice(sorted(ok))] + rng.sample(near, 3)
                correct = opts[0]
                q = 'X 차례다. 다음 중 X가 둘 수 있는 자리는?'
            elif not want_legal and len(ok) >= 3 and near:
                opts = [rng.choice(near)] + rng.sample(sorted(ok), 3)
                correct = opts[0]
                q = 'X 차례다. 다음 중 X가 둘 수 없는 자리는?'
            else:
                continue
            items.append(make_item(rng, GAME, '1-판정', n, state_of(b), q, [CELLS[i] for i in opts], CELLS[correct]))
            break
    # ③ 한 수: 가장 많이 뒤집는 자리 (보기 = X가 둘 수 있는 자리 전부). 짝이 되는 국면을 절반 넣는다.
    q3 = 'X 차례다. 이번 수로 O 돌을 가장 많이 뒤집는 자리는?'
    twins, plain = [], []
    while len(twins) < per_stage // 2 or len(plain) < per_stage - per_stage // 2:
        b = next(gen)
        moves = legal(b, 'X', 'standard')
        if not 3 <= len(moves) <= 16:
            continue
        best = most_flips(b, 'standard', moves)
        if best is None:
            continue
        vbest = most_flips(b, 'nodiag', moves)
        if vbest is not None and vbest != best:
            if len(twins) < per_stage // 2:
                twins.append((b, moves, best, vbest))
        elif len(plain) < per_stage - per_stage // 2:
            plain.append((b, moves, best, None))
    for n, (b, moves, best, vbest) in enumerate(twins + plain):
        base = make_item(rng, GAME, '3-한수(판)', n, state_of(b), q3, [CELLS[i] for i in moves], CELLS[best])
        items.append(base)
        ann = {CELLS[i]: annotate3(b, i) for i in moves}
        items.append(make_item(rng, GAME, '3-한수(주석)', n, state_of(b), q3, list(ann.values()), ann[CELLS[best]],
                               order=[ann[o] for o in base['options']]))
        if vbest is not None:
            items.append(make_item(rng, GAME, '2-변형', k2, state_of(b, 'nodiag'), q3, [CELLS[i] for i in moves],
                                   CELLS[vbest], original=CELLS[best], twin_of=base['id'], order=base['options']))
            k2 += 1
    # ④ 앞보기: O의 가장 나쁜 응수 뒤 X 돌이 가장 많이 남는 자리 (가장 많이 뒤집는 자리와 다른 국면만)
    q4 = ('X 차례다. X가 둔 뒤 O는 X의 돌을 가장 많이 줄이는 자리에 둔다고 하자. '
          '그 뒤 X의 돌이 가장 많이 남게 하려면 X는 어디에 둬야 하는가?')
    gen4 = x_positions(rng, 8, 20)
    n = 0
    while n < per_stage:
        b = next(gen4)
        moves = legal(b, 'X', 'standard')
        if not 3 <= len(moves) <= 16:
            continue
        best, _ = lookahead_best(b, 'standard')
        if best is None or best == most_flips(b, 'standard', moves):
            continue
        base = make_item(rng, GAME, '4-앞보기(판)', n, state_of(b), q4, [CELLS[i] for i in moves], CELLS[best])
        items.append(base)
        ann = {CELLS[i]: annotate4(b, i) for i in moves}
        items.append(make_item(rng, GAME, '4-앞보기(주석)', n, state_of(b), q4, list(ann.values()), ann[CELLS[best]],
                               order=[ann[o] for o in base['options']]))
        n += 1
    return items
