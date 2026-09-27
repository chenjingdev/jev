"""사목 (Connect Four, 가로 5칸 × 세로 4칸 작은 판).

판 표기는 틱택토와 같다: 행 A~D(A가 맨 위), 열 1~5, 빈칸 '.', 좌표 'D3'. 수는 열 번호로 고른다.

① 판정: 지금 판에서 이긴 사람(또는 진 사람)은? (X / O / 아직 없음)
③ 한 수: X 차례에서 게임 이론상 최선의 수가 정확히 하나이고, 그 수가 바로 이기거나 O의 바로 이기는 자리를 막는 수.
④ 앞보기: 최선의 수가 하나뿐이지만 바로 이기거나 바로 막는 수가 아닌 국면.
   최선은 판 끝까지 전부 읽는 완전 탐색(메모이즈한 negamax)으로 정한다. 5×4 판이라 중반 국면은 금방 끝난다.
② 변형: "대각선으로 이은 것은 치지 않는다". ①은 대각선으로만 이긴 판, ③·④는 변형 규칙에서도 최선이 하나이고
   그 수가 달라지는 국면만 짝으로 쓴다.
"""
from functools import lru_cache

from .common import make_item

GAME = 'connect4'
NAME = '사목'
FACET = '수 읽기'

W, H = 5, 4
ROWS = 'ABCD'
CELLS = [r + str(c + 1) for r in ROWS for c in range(W)]


def _lines(diag):
    dirs = [(0, 1), (1, 0)] + ([(1, 1), (1, -1)] if diag else [])
    out = []
    for r in range(H):
        for c in range(W):
            for dr, dc in dirs:
                cells = [(r + k * dr, c + k * dc) for k in range(4)]
                if all(0 <= a < H and 0 <= b < W for a, b in cells):
                    out.append(tuple(a * W + b for a, b in cells))
    return out


LINES = {'standard': _lines(True), 'nodiag': _lines(False)}
BY_CELL = {rule: [[ln for ln in ls if i in ln] for i in range(W * H)] for rule, ls in LINES.items()}

_COMMON = ('가로 5칸, 세로 4칸 판에 X와 O가 번갈아 말을 하나씩 넣는다. X가 먼저 둔다. 말은 고른 열의 가장 아래 빈칸으로 '
           '떨어진다. ')
RULE_TEXT = {
    'standard': _COMMON + '가로·세로·대각선 중 한 줄로 자기 말 4개를 먼저 이으면 이긴다. '
                          '판이 다 차도록 아무도 못 이기면 비긴다.',
    'nodiag': _COMMON + '가로·세로 중 한 줄로 자기 말 4개를 먼저 이으면 이긴다. 대각선으로 이은 것은 치지 않는다. '
                        '판이 다 차도록 아무도 못 이기면 비긴다.',
}
NOTATION = ('판은 행 A~D(A가 맨 위, D가 맨 아래), 열 1~5로 적고 빈칸은 "."이다. 좌표는 "D3"처럼 행과 열을 붙여 쓴다. '
            '수는 말을 넣을 열로 고르며 "3열"처럼 쓴다.')


def render(board):
    return '  ' + ' '.join(str(c + 1) for c in range(W)) + '\n' + '\n'.join(
        r + ' ' + ' '.join(board[i * W:(i + 1) * W]) for i, r in enumerate(ROWS))


def parse(rows):
    """['.....', ...] (A행부터) -> 판 문자열."""
    assert len(rows) == H and all(len(r) == W for r in rows)
    return ''.join(rows)


def drop(board, col):
    """col 열에 넣으면 말이 놓이는 칸 번호. 꽉 찼으면 None."""
    for r in range(H - 1, -1, -1):
        if board[r * W + col] == '.':
            return r * W + col
    return None


def legal_cols(board):
    return [c for c in range(W) if drop(board, c) is not None]


def completes(board, i, mark, rule):
    """i 칸에 mark를 놓으면 완성되는 줄 수."""
    b = board[:i] + mark + board[i + 1:]
    return sum(1 for ln in BY_CELL[rule][i] if all(b[j] == mark for j in ln))


def winner(board, rule):
    for ln in LINES[rule]:
        m = board[ln[0]]
        if m != '.' and all(board[j] == m for j in ln):
            return m
    return None


def turn_of(board):
    return 'X' if board.count('X') == board.count('O') else 'O'


@lru_cache(maxsize=None)
def _negamax(board, rule, turn):
    """turn 차례에서의 게임 값 (turn 기준: 1 승, 0 무, -1 패). board는 아직 끝나지 않은 판."""
    nxt = 'O' if turn == 'X' else 'X'
    cells = [drop(board, c) for c in range(W)]
    cells = [i for i in cells if i is not None]
    if not cells:
        return 0
    if any(completes(board, i, turn, rule) for i in cells):
        return 1
    best = -1
    for i in cells:
        v = -_negamax(board[:i] + turn + board[i + 1:], rule, nxt)
        if v > best:
            best = v
            if best == 1:
                break
    return best


def move_values(board, rule):
    """X 차례에서 열마다 게임 값 (X 기준)."""
    out = {}
    for c in legal_cols(board):
        i = drop(board, c)
        b = board[:i] + 'X' + board[i + 1:]
        out[c] = 1 if completes(board, i, 'X', rule) else -_negamax(b, rule, 'O')
    return out


def best_moves(board, rule):
    vals = move_values(board, rule)
    top = max(vals.values())
    return [c for c, v in vals.items() if v == top], vals


def col_name(c):
    return f'{c + 1}열'


def annotate(board, c, rule):
    i = drop(board, c)
    b = board[:i] + 'X' + board[i + 1:]
    x_lines = completes(board, i, 'X', rule)
    o_cols = 0 if x_lines else sum(1 for d in legal_cols(b) if completes(b, drop(b, d), 'O', rule))
    return (f'{col_name(c)} — 말이 {CELLS[i]}에 놓인다. 여기 두면 X가 완성하는 줄 {x_lines}개, '
            f'그 뒤 O가 바로 4개를 이을 수 있는 열 {o_cols}개')


def verdict(board, rule, ask):
    w = winner(board, rule)
    if w is None:
        return '아직 없음'
    return w if ask == 'win' else ('O' if w == 'X' else 'X')


def _playout(rng, stop_at):
    """표준 규칙으로 무작위로 두다가 누가 이기거나 stop_at 수에 이르면 멈춘다."""
    b = '.' * (W * H)
    for _ in range(stop_at):
        cols = legal_cols(b)
        if not cols or winner(b, 'standard'):
            break
        i = drop(b, rng.choice(cols))
        b = b[:i] + turn_of(b) + b[i + 1:]
    return b


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 짝: 대각선으로만 이긴 판(변형에서는 '아직 없음')과 그 밖의 판을 섞는다
    diag_only, others, seen = [], [], set()
    while len(diag_only) < per_stage or len(others) < per_stage:
        b = _playout(rng, rng.randint(9, W * H))
        if b in seen:
            continue
        seen.add(b)
        if winner(b, 'standard') and not winner(b, 'nodiag'):
            diag_only.append(b)
        elif verdict(b, 'standard', 'win') == verdict(b, 'nodiag', 'win') and b.count('.') < 12:
            others.append(b)
    opts = ['X', 'O', '아직 없음']
    questions = {'win': '지금 판에서 이긴 사람은?', 'lose': '지금 판에서 진 사람은?'}
    for i in range(per_stage):
        b = diag_only[i // 2] if i % 2 == 0 else others[i // 2]
        ask = 'lose' if i % 4 in (1, 2) else 'win'
        state = {'규칙': RULE_TEXT['standard'], '표기': NOTATION, '판': render(b)}
        base = make_item(rng, GAME, '1-판정', i, state, questions[ask], opts, verdict(b, 'standard', ask))
        items.append(base)
        if verdict(b, 'standard', ask) != verdict(b, 'nodiag', ask):
            items.append(make_item(rng, GAME, '2-변형', i, dict(state, 규칙=RULE_TEXT['nodiag']), questions[ask],
                                   opts, verdict(b, 'nodiag', ask), original=verdict(b, 'standard', ask),
                                   twin_of=base['id'], order=base['options']))
    # ③·④: 무작위 중반 국면(X 차례)에서 완전 탐색으로 최선의 수가 하나뿐인 것
    pools = {'3-한수': [], '4-앞보기': []}
    seen = set()
    tries = 0
    while (min(len(p) for p in pools.values()) < per_stage
           or min(sum(t is not None for _, _, t in p) for p in pools.values()) < per_stage // 2) and tries < 4000:
        tries += 1
        b = _playout(rng, 2 * rng.randint(5, 7))
        if b in seen or winner(b, 'standard') or turn_of(b) != 'X' or len(legal_cols(b)) < 3:
            continue
        seen.add(b)
        best, _ = best_moves(b, 'standard')
        if len(best) != 1:
            continue
        c = best[0]
        i = drop(b, c)
        tactical = completes(b, i, 'X', 'standard') or completes(b, i, 'O', 'standard')
        vbest, _ = best_moves(b, 'nodiag')
        twin = vbest[0] if len(vbest) == 1 and vbest[0] != c else None
        pools['3-한수' if tactical else '4-앞보기'].append((b, c, twin))
    q3 = 'X 차례다. 양쪽 모두 최선을 다한다고 할 때 X가 말을 넣을 곳으로 가장 좋은 열은?'
    k = per_stage
    for stage, pool in pools.items():
        twins = [u for u in pool if u[2] is not None][:per_stage // 2]
        plain = [u for u in pool if u[2] is None][:per_stage - len(twins)]
        for n, (b, best, vbest) in enumerate(twins + plain):
            cols = legal_cols(b)
            state = {'규칙': RULE_TEXT['standard'], '표기': NOTATION, '판': render(b)}
            base = make_item(rng, GAME, f'{stage}(판)', n, state, q3, [col_name(c) for c in cols], col_name(best))
            items.append(base)
            ann = {col_name(c): annotate(b, c, 'standard') for c in cols}
            items.append(make_item(rng, GAME, f'{stage}(주석)', n, state, q3, list(ann.values()), ann[col_name(best)],
                                   order=[ann[o] for o in base['options']]))
            if vbest is not None:
                items.append(make_item(rng, GAME, '2-변형', k, dict(state, 규칙=RULE_TEXT['nodiag']), q3,
                                       [col_name(c) for c in cols], col_name(vbest), original=col_name(best),
                                       twin_of=base['id'], order=base['options']))
                k += 1
    return items
