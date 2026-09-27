"""보상표 최선 응답.

보상표(2×2 또는 3×3)를 규칙 안에 표로 준다. 칸은 (내 점수, 상대 점수). 규칙 문구는 표 데이터에서 만든다.
① 판정: 상대 행동을 알 때 내 점수가 가장 큰(또는 가장 작은) 내 행동. 하나로 정해지는 경우만.
③ 한 수: 상대가 무엇을 고르든 다른 모든 내 행동보다 내 점수가 항상 더 높은 행동(엄격 우월 행동)이
   정확히 하나 있는 표만 쓴다.
② 변형: 같은 상황·보기에서 표의 내 점수 한 칸(③은 필요하면 같은 행의 두 칸)만 바꾼 규칙.
   바꾼 표에서도 답이 하나이고 달라지는 경우만 짝으로 쓴다.
"""
from itertools import combinations

from .common import make_item

GAME = 'payoff'
NAME = '보상표 최선 응답'
FACET = '상대 파악'

LABELS = {2: (['협력', '배신'], ['협력', '배신']), 3: (['A', 'B', 'C'], ['X', 'Y', 'Z'])}


def rules_text(mine_names, opp_names, table):
    """table[r][c] = (내 점수, 상대 점수)."""
    head = '나 \\ 상대 | ' + ' | '.join(opp_names)
    rows = [f'{m} | ' + ' | '.join(f'({a}, {b})' for a, b in table[r]) for r, m in enumerate(mine_names)]
    return ('나와 상대가 각자 행동 하나를 동시에 고른다. 두 사람이 받는 점수는 아래 표대로 정해진다. '
            '행은 내 행동, 열은 상대 행동이고, 칸의 (앞 수, 뒤 수)는 (내 점수, 상대 점수)다. 점수가 클수록 좋다.\n'
            + head + '\n' + '\n'.join(rows))


def best_response(table, col, goal='max'):
    vals = [row[col][0] for row in table]
    top = (max if goal == 'max' else min)(vals)
    rs = [r for r, v in enumerate(vals) if v == top]
    return rs[0] if len(rs) == 1 else None


def dominant(table):
    n = len(table)
    rs = [r for r in range(n) if all(all(table[r][c][0] > table[s][c][0] for c in range(len(table[r])))
                                     for s in range(n) if s != r)]
    assert len(rs) <= 1
    return rs[0] if rs else None


def with_mine(table, changes):
    t = [list(row) for row in table]
    for (r, c), v in changes.items():
        t[r][c] = (v, t[r][c][1])
    return t


def random_table(rng, n):
    return [[(rng.randint(0, 9), rng.randint(0, 9)) for _ in range(n)] for _ in range(n)]


def pd_table(rng):
    """죄수의 딜레마 꼴: 배신 유혹 T > 서로 협력 R > 서로 배신 P > 혼자 협력 S."""
    s_, p_, r_, t_ = sorted(rng.sample(range(10), 4))
    return [[(r_, r_), (s_, t_)], [(t_, s_), (p_, p_)]]


def twin_best(rng, table, col, goal, ans):
    cands = [(r, v) for r in range(len(table)) for v in range(10) if v != table[r][col][0]]
    rng.shuffle(cands)
    for r, v in cands:
        t = with_mine(table, {(r, col): v})
        b = best_response(t, col, goal)
        if b is not None and b != ans:
            return t, b
    return None, None


def twin_dominant(rng, table, ans):
    n = len(table)
    single = [{(r, c): v} for r in range(n) for c in range(n) for v in range(10) if v != table[r][c][0]]
    double = [{(r, c1): v1, (r, c2): v2} for r in range(n) for c1, c2 in combinations(range(n), 2)
              for v1 in range(10) for v2 in range(10) if v1 != table[r][c1][0] and v2 != table[r][c2][0]]
    rng.shuffle(single); rng.shuffle(double)
    for ch in single + double:
        t = with_mine(table, ch)
        d = dominant(t)
        if d is not None and d != ans:
            return t, d
    return None, None


QUESTIONS = {'max': '내 점수를 가장 크게 하려면 나는 어떤 행동을 골라야 하는가?',
             'min': '내 점수를 가장 작게 하려면 나는 어떤 행동을 골라야 하는가?',
             'dom': '상대가 무엇을 고르든, 다른 어떤 내 행동보다 내 점수가 항상 더 큰 행동은?'}


def generate(rng, per_stage):
    items = []
    k = 0
    for stage in ('1-판정', '3-한수'):
        made = 0
        while made < per_stage:
            n = 2 if made % 3 == 0 else 3
            mine, opp = LABELS[n]
            table = pd_table(rng) if stage == '3-한수' and made % 6 == 0 else random_table(rng, n)
            if stage == '1-판정':
                col = rng.randrange(n)
                goal = 'max' if made % 3 else 'min'
                ans = best_response(table, col, goal)
                sit = f'상대가 {opp[col]}{"을" if n == 2 else "를"} 고른다는 것을 알고 있다.'
                twin_fn = lambda: twin_best(rng, table, col, goal, ans)
            else:
                goal = 'dom'
                ans = dominant(table)
                sit = '상대가 무엇을 고를지는 모른다.'
                twin_fn = lambda: twin_dominant(rng, table, ans)
            if ans is None:
                continue
            state = {'규칙': rules_text(mine, opp, table), '상황': sit}
            # 보기 수가 2~3개라 무작위로 섞으면 시드에 따라 정답 위치가 쏠린다. 정답 위치를 돌려 가며 둔다.
            order = rng.sample(mine, n)
            shift = (order.index(mine[ans]) - (made + len(items))) % n
            order = order[shift:] + order[:shift]
            base = make_item(rng, GAME, stage, made, state, QUESTIONS[goal], mine, mine[ans], order=order)
            items.append(base)
            if made % 4 != 3:  # 넷에 하나는 짝 없이 둔다
                t, twin = twin_fn()
                if twin is not None:
                    items.append(make_item(rng, GAME, '2-변형', k, dict(state, 규칙=rules_text(mine, opp, t)),
                                           QUESTIONS[goal], mine, mine[twin], original=mine[ans],
                                           twin_of=base['id'], order=base['options']))
                    k += 1
            made += 1
    return items
