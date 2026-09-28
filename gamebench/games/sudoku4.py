"""미니 스도쿠 (4×4).

판 표기는 틱택토와 같다: 행 A~D, 열 1~4, 빈칸 '.', 좌표 'B2'.
"정해진다"는 규칙을 지키며 판을 끝까지 채우는 모든 방법에서 그 칸의 수가 같다는 뜻이다(풀이기가 전부 센다).

① 판정: 주어진 빈칸에 들어갈 수(1~4).
③ 한 수: 보기로 준 빈칸 중 수가 하나로 정해지는 칸(보기 중 정확히 하나).
② 변형: 구역 네 개를 다르게 묶은 규칙(A·D행끼리, B·C행끼리 2열씩).
   조건을 더하는 규칙(예: 대각선 추가)은 답을 바꿀 수 없다. 조건을 더하면 채우는 방법이 줄어들 뿐이라
   원래 규칙에서 정해진 칸은 그대로 정해진다. 4×4에서는 두 대각선에 1~4가 한 번씩 들어가는 판 48개가
   모두 2×2 구역 조건도 만족해서, 구역을 대각선으로 바꿔도 마찬가지다. 그래서 서로 포함 관계가 없는
   구역 묶음을 짝으로 쓴다. 두 규칙 모두 채우는 방법이 있는 판만 쓴다.
"""
from itertools import permutations

from .common import make_item

GAME = 'sudoku4'
NAME = '미니 스도쿠'
FACET = '논리·정보 추론'

ROWS = 'ABCD'
CELLS = [r + c for r in ROWS for c in '1234']
NOTATION = '판은 행 A~D, 열 1~4로 적고 빈칸은 "."이다. 좌표는 "B2"처럼 행과 열을 붙여 쓴다.'
REGIONS = {
    'box': [(0, 1, 4, 5), (2, 3, 6, 7), (8, 9, 12, 13), (10, 11, 14, 15)],   # 네 등분한 2×2
    'alt': [(0, 1, 12, 13), (2, 3, 14, 15), (4, 5, 8, 9), (6, 7, 10, 11)],   # A·D행, B·C행을 묶은 구역
}


def rules_text(rule):
    regions = ' / '.join('·'.join(CELLS[i] for i in reg) for reg in REGIONS[rule])
    return ('4×4 판의 빈칸에 1~4 중 하나씩을 넣어 판을 채운다. 각 가로줄, 각 세로줄, 그리고 다음 네 구역'
            f'({regions})에 1~4가 한 번씩 들어가야 한다.')


RULE_TEXT = {r: rules_text(r) for r in REGIONS}


def _latin():
    rows = [''.join(p) for p in permutations('1234')]
    out = []
    for a in rows:
        for b in rows:
            if any(x == y for x, y in zip(a, b)):
                continue
            for c in rows:
                if any(x in (y, z) for x, y, z in zip(c, a, b)):
                    continue
                d = ''.join(next(v for v in '1234' if v not in col) for col in zip(a, b, c))
                out.append(a + b + c + d)
    return out


def _ok(g, groups):
    return all(len({g[i] for i in grp}) == 4 for grp in groups)


LATIN = _latin()
SOLUTIONS = {r: [g for g in LATIN if _ok(g, regs)] for r, regs in REGIONS.items()}


def render(board):
    return '  1 2 3 4\n' + '\n'.join(r + ' ' + ' '.join(board[i * 4:i * 4 + 4]) for i, r in enumerate(ROWS))


def completions(board, rule):
    return [s for s in SOLUTIONS[rule] if all(b == '.' or b == v for b, v in zip(board, s))]


def determined(board, rule):
    """빈칸 번호 -> 모든 채우기에서 같은 수. 채우기가 없으면 None."""
    comps = completions(board, rule)
    if not comps:
        return None
    return {i: comps[0][i] for i, b in enumerate(board) if b == '.' and len({s[i] for s in comps}) == 1}


def puzzle(rng, sol, n_given):
    keep = set(rng.sample(range(16), n_given))
    return ''.join(v if i in keep else '.' for i, v in enumerate(sol))


def generate(rng, per_stage):
    items = []
    digits = ['1', '2', '3', '4']
    q_cell = '{}에 들어갈 수는?'
    # ① 판정: 짝수 번째는 짝 있는 판(두 규칙에서 값이 다른 칸), 홀수 번째는 구역 규칙만
    i = 0
    while i < per_stage:
        want_twin = i % 2 == 0
        b = puzzle(rng, rng.choice(SOLUTIONS['box']), rng.randint(5, 9))
        db = determined(b, 'box')
        cands = sorted(db)
        if want_twin:
            dt = determined(b, 'alt')
            if not dt:
                continue
            cands = [c for c in cands if c in dt and dt[c] != db[c]]
        if not cands:
            continue
        c = rng.choice(cands)
        state = {'규칙': RULE_TEXT['box'], '표기': NOTATION, '판': render(b)}
        q = q_cell.format(CELLS[c])
        base = make_item(rng, GAME, '1-판정', i, state, q, digits, db[c])
        items.append(base)
        if want_twin:
            items.append(make_item(rng, GAME, '2-변형', i, dict(state, 규칙=RULE_TEXT['alt']), q, digits, dt[c],
                                   original=db[c], twin_of=base['id'], order=base['options']))
        i += 1
    # ③ 한 수: 보기 5칸 중 정해지는 칸이 하나. 짝수 번째는 짝 있는 판
    q3 = '보기의 빈칸 중 들어갈 수가 하나로 정해지는 칸은?'
    i = 0
    while i < per_stage:
        want_twin = i % 2 == 0
        b = puzzle(rng, rng.choice(SOLUTIONS['box']), rng.randint(4, 7))
        empties = [j for j, v in enumerate(b) if v == '.']
        db = determined(b, 'box')
        dt = determined(b, 'alt') if want_twin else {}
        if dt is None or not db:
            continue
        free = [j for j in empties if j not in db and j not in dt]
        xs = sorted(db.keys() - dt.keys())
        ys = sorted(dt.keys() - db.keys())
        if not xs or (want_twin and not ys) or len(free) < 4:
            continue
        x = rng.choice(xs)
        must = [x] + ([rng.choice(ys)] if want_twin else [])
        opts = [CELLS[j] for j in must + rng.sample(free, 5 - len(must))]
        state = {'규칙': RULE_TEXT['box'], '표기': NOTATION, '판': render(b)}
        base = make_item(rng, GAME, '3-한수', i, state, q3, opts, CELLS[x])
        assert [o for o in opts if CELLS.index(o) in db] == [CELLS[x]]
        items.append(base)
        if want_twin:
            tw = [o for o in opts if CELLS.index(o) in dt]
            assert len(tw) == 1
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=RULE_TEXT['alt']), q3, opts,
                                   tw[0], original=CELLS[x], twin_of=base['id'], order=base['options']))
        i += 1
    return items
