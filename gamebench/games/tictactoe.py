"""틱택토 (참조 구현, 판이 있는 게임의 표기 기준).

판 표기(모든 판 게임 공통 원칙): 행은 A~, 열은 1~, 빈칸은 '.', 좌표는 'B2'처럼 쓴다.

① 판정: 지금 판에서 이긴 사람은? (X / O / 아직 없음)
③ 한 수(판): X 차례에서 게임 이론상 최선의 수가 정확히 하나인 국면. 보기는 빈칸 좌표.
③ 한 수(주석): 같은 국면, 보기마다 코드가 계산한 사실 두 가지를 붙인다.
④ 앞보기: 최선의 수가 하나뿐이지만 바로 이기거나 바로 막는 수가 아닌 국면.
② 변형: ①의 짝은 "대각선은 한 줄로 치지 않는다", ③·④의 짝은 "네 귀퉁이 중 세 칸을 차지해도 이긴다".
   (대각선 제외 규칙은 틱택토 판 구조상 수 선택의 답을 바꾸는 국면이 없다.) 답이 달라지는 국면만 쓴다.
"""
from functools import lru_cache

from .common import make_item

GAME = 'tictactoe'
NAME = '틱택토'
FACET = '수 읽기'

ROWS = 'ABC'
CELLS = [r + c for r in ROWS for c in '123']
STRAIGHT = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8)]
DIAG = [(0, 4, 8), (2, 4, 6)]
CORNERS = [(0, 2, 6), (0, 2, 8), (0, 6, 8), (2, 6, 8)]
RULES = {'standard': tuple(STRAIGHT + DIAG), 'nodiag': tuple(STRAIGHT), 'corners': tuple(STRAIGHT + DIAG + CORNERS)}
RULE_TEXT = {
    'standard': '3×3 판에 X와 O가 번갈아 한 칸씩 둔다. 가로·세로·대각선 중 한 줄에 자기 표시 3개를 먼저 놓으면 이긴다. '
                '판이 다 차도록 아무도 못 이기면 비긴다.',
    'nodiag': '3×3 판에 X와 O가 번갈아 한 칸씩 둔다. 가로·세로 중 한 줄에 자기 표시 3개를 먼저 놓으면 이긴다. '
              '대각선은 한 줄로 치지 않는다. 판이 다 차도록 아무도 못 이기면 비긴다.',
    'corners': '3×3 판에 X와 O가 번갈아 한 칸씩 둔다. 가로·세로·대각선 중 한 줄에 자기 표시 3개를 먼저 놓거나, '
               '네 귀퉁이(A1, A3, C1, C3) 중 세 칸을 먼저 차지하면 이긴다. 판이 다 차도록 아무도 못 이기면 비긴다.',
}
NOTATION = '판은 행 A~C, 열 1~3으로 적고 빈칸은 "."이다. 좌표는 "B2"처럼 행과 열을 붙여 쓴다.'


def render(board):
    return '  1 2 3\n' + '\n'.join(r + ' ' + ' '.join(board[i * 3:i * 3 + 3]) for i, r in enumerate(ROWS))


def winner(board, rule):
    for a, b, c in RULES[rule]:
        if board[a] != '.' and board[a] == board[b] == board[c]:
            return board[a]
    return None


@lru_cache(maxsize=None)
def value(board, rule, turn):
    """turn 차례에서의 게임 값 (X 기준: 1 승, 0 무, -1 패)."""
    w = winner(board, rule)
    if w:
        return 1 if w == 'X' else -1
    if '.' not in board:
        return 0
    nxt = 'O' if turn == 'X' else 'X'
    vals = [value(board[:i] + turn + board[i + 1:], rule, nxt) for i, c in enumerate(board) if c == '.']
    return max(vals) if turn == 'X' else min(vals)


def best_moves(board, rule):
    """X 차례에서 최선의 수 목록."""
    scores = {i: value(board[:i] + 'X' + board[i + 1:], rule, 'O') for i, c in enumerate(board) if c == '.'}
    top = max(scores.values())
    return [i for i, v in scores.items() if v == top], scores


def completes(board, i, mark, rule):
    b = board[:i] + mark + board[i + 1:]
    return sum(1 for line in RULES[rule] if i in line and all(b[j] == mark for j in line))


def annotate(board, i, rule):
    b = board[:i] + 'X' + board[i + 1:]
    x_lines = completes(board, i, 'X', rule)
    o_threats = len({j for j, c in enumerate(b) if c == '.' and completes(b, j, 'O', rule)}) if not x_lines else 0
    return f'{CELLS[i]} — 여기 두면 X가 완성하는 줄 {x_lines}개, 그 뒤 O가 바로 한 줄을 완성할 수 있는 빈칸 {o_threats}개'


def positions():
    """합법 국면 전체 (X 차례, 아직 끝나지 않은 판)."""
    seen, out, stack = set(), [], ['.' * 9]
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        xs, os_ = b.count('X'), b.count('O')
        if winner(b, 'standard') or '.' not in b:
            continue
        turn = 'X' if xs == os_ else 'O'
        if turn == 'X':
            out.append(b)
        for i, c in enumerate(b):
            if c == '.':
                stack.append(b[:i] + turn + b[i + 1:])
    return sorted(out)


def finished_positions():
    seen, out, stack = set(), [], ['.' * 9]
    while stack:
        b = stack.pop()
        if b in seen:
            continue
        seen.add(b)
        out.append(b)
        if winner(b, 'nodiag') or '.' not in b:
            continue
        turn = 'X' if b.count('X') == b.count('O') else 'O'
        for i, c in enumerate(b):
            if c == '.':
                stack.append(b[:i] + turn + b[i + 1:])
    return sorted(out)


def verdict(board, rule):
    return {'X': 'X', 'O': 'O', None: '아직 없음'}[winner(board, rule)]


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 변형 짝: 대각선으로만 이긴 판(변형에서는 '아직 없음')과 그 밖의 판을 섞는다
    fins = finished_positions()
    diag_only = [b for b in fins if winner(b, 'standard') and not winner(b, 'nodiag')]
    others = [b for b in fins if verdict(b, 'standard') == verdict(b, 'nodiag') and b.count('.') < 7]
    rng.shuffle(diag_only); rng.shuffle(others)
    opts = ['X', 'O', '아직 없음']
    q1 = '지금 판에서 이긴 사람은?'
    for i in range(per_stage):
        b = diag_only[i // 2] if i % 2 == 0 else others[i // 2]
        state = {'규칙': RULE_TEXT['standard'], '표기': NOTATION, '판': render(b)}
        base = make_item(rng, GAME, '1-판정', i, state, q1, opts, verdict(b, 'standard'))
        items.append(base)
        if verdict(b, 'standard') != verdict(b, 'nodiag'):
            items.append(make_item(rng, GAME, '2-변형', i, dict(state, 규칙=RULE_TEXT['nodiag']), q1, opts,
                                   verdict(b, 'nodiag'), original=verdict(b, 'standard'), twin_of=base['id'],
                                   order=base['options']))
    # ③ 한 수 / ④ 앞보기: 최선의 수가 하나뿐인 국면. 바로 이기거나 바로 막는 수면 ③, 아니면 ④.
    # 짝 변형(귀퉁이 규칙)은 변형 규칙에서도 최선이 하나이고 답이 다른 국면만.
    pools = {'3-한수': [], '4-앞보기': []}
    for b in positions():
        if b.count('.') < 3 or winner(b, 'corners'):
            continue
        best, _ = best_moves(b, 'standard')
        if len(best) != 1:
            continue
        j = best[0]
        tactical = completes(b, j, 'X', 'standard') or completes(b, j, 'O', 'standard')
        vbest, _ = best_moves(b, 'corners')
        twin = vbest[0] if len(vbest) == 1 and vbest[0] != j else None
        pools['3-한수' if tactical else '4-앞보기'].append((b, j, twin))
    q3 = 'X 차례다. X가 둘 곳으로 가장 좋은 자리는?'
    k = per_stage
    for stage, pool in pools.items():
        rng.shuffle(pool)
        twins = [u for u in pool if u[2] is not None][:per_stage // 2]
        plain = [u for u in pool if u[2] is None][:per_stage - len(twins)]
        for i, (b, best, vbest) in enumerate(twins + plain):
            empties = [j for j, c in enumerate(b) if c == '.']
            state = {'규칙': RULE_TEXT['standard'], '표기': NOTATION, '판': render(b)}
            base = make_item(rng, GAME, f'{stage}(판)', i, state, q3, [CELLS[j] for j in empties], CELLS[best])
            items.append(base)
            ann = [annotate(b, j, 'standard') for j in empties]
            order = [ann[empties.index(CELLS.index(c))] for c in base['options']]
            items.append(make_item(rng, GAME, f'{stage}(주석)', i, state, q3, ann, ann[empties.index(best)],
                                   order=order))
            if vbest is not None:
                items.append(make_item(rng, GAME, '2-변형', k, dict(state, 규칙=RULE_TEXT['corners']), q3,
                                       [CELLS[j] for j in empties], CELLS[vbest], original=CELLS[best],
                                       twin_of=base['id'], order=base['options']))
                k += 1
    return items
