"""윷놀이 (칸 번호로 적은 간단한 윷판).

판은 글로만 준다: 바깥 길 1~20번, 지름길 21~27번(5번·10번에서 이동을 시작할 때만 들어간다).
빽도는 쓰지 않는다. 윷·모·잡기 뒤 한 번 더 던지는 규칙은 문항에서 다루지 않는다(한 번 또는 두 번의 결과가 주어진다).

① 판정: 한 말이 주어진 결과로 도착하는 칸 (또는 난다).
③ 한 수: 내 말 여러 개 중 이번 결과로 상대 말을 잡는(또는 판에서 나가는) 말이 정확히 하나인 상황.
④ 앞보기: 두 결과를 한 말에 차례로 쓸 때, 상대 말을 잡는 (말, 순서)가 정확히 하나인 상황. 모서리(5·10번)에 멈추는지에
   따라 길이 갈려 순서가 답을 바꾼다.
② 변형: "5·10번에서 지름길로 들어가지 않는다" 또는 "20번에 도착하기만 해도 난다" 규칙. 답이 달라지는 상황만 짝으로 쓴다.
"""
from .common import make_item

GAME = 'yut'
NAME = '윷놀이'
FACET = '수 읽기'

THROWS = {'도': 1, '개': 2, '걸': 3, '윷': 4, '모': 5}
OUT = '난다'
LABELS = '가나다라'
SHORT5 = [21, 22, 23, 24, 25, 20]
SHORT10 = [26, 27, 23, 24, 25, 20]

_BOARD = ('윷판의 칸은 1~27번이다. 말은 판 밖에서 출발하고, 판 밖의 말은 1번 칸부터 센다(도가 나오면 1번에 선다). '
          '바깥 길은 1→2→…→19→20 순서다. ')
_SHORT = ('지름길: 5번 칸에서 이동을 시작하는 말은 5→21→22→23→24→25→20으로, 10번 칸에서 이동을 시작하는 말은 '
          '10→26→27→23→24→25→20으로 간다. 5번·10번을 지나가기만 하는 말은 바깥 길로 계속 간다. '
          '21~27번 칸에 있는 말은 그 칸이 있는 지름길을 따라 20번 쪽으로 간다. ')
_NOSHORT = ('5번·10번 칸에서 이동을 시작해도 지름길로 들어가지 않고 바깥 길로 계속 간다. '
            '21~27번 칸에 이미 있는 말은 그 칸이 있는 지름길(5→21→22→23→24→25→20, 10→26→27→23→24→25→20)을 따라 20번 쪽으로 간다. ')
_STEPS = '도는 1칸, 개는 2칸, 걸은 3칸, 윷은 4칸, 모는 5칸 간다. '
_PASS = ('20번 칸을 지나칠 만큼 가면 그 말은 판에서 나간다(난다). 20번 칸에 딱 맞게 도착하면 20번에 선다. '
         '20번에 선 말은 다음에 무엇이 나오든 난다. ')
_ARRIVE = '20번 칸에 도착하거나 지나칠 만큼 가면 그 말은 판에서 나간다(난다). '
_CAPTURE = '말이 움직임을 마친 칸에 상대 말이 있으면 그 상대 말을 잡는다. 잡힌 말은 판 밖으로 돌아간다.'

RULES = {  # 이름: (지름길 있음, 20번 도착만으로 남)
    'standard': (True, False),
    'noshort': (False, False),
    'arrive': (True, True),
}


def rule_text(rule):
    short, arrive = RULES[rule]
    return _BOARD + (_SHORT if short else _NOSHORT) + _STEPS + (_ARRIVE if arrive else _PASS) + _CAPTURE


def path_from(pos, rule):
    """pos(0 = 판 밖)에서 이동을 시작할 때 차례로 밟는 칸 (20번까지)."""
    short, _ = RULES[rule]
    if pos == 0:
        return list(range(1, 21))
    if pos == 20:
        return []
    if short and pos == 5:
        return SHORT5
    if short and pos == 10:
        return SHORT10
    for route in (SHORT5, SHORT10):
        if pos in route:
            return route[route.index(pos) + 1:]
    return list(range(pos + 1, 21))


def dest(pos, steps, rule):
    """pos에서 steps칸 간 칸. 판에서 나가면 OUT."""
    _, arrive = RULES[rule]
    p = path_from(pos, rule)
    if steps > len(p) or (arrive and steps == len(p)):
        return OUT
    return p[steps - 1]


def josa(word, batchim, plain):
    """윷 결과 이름 뒤 조사 (걸·윷은 받침이 있다)."""
    return word + (batchim if word in ('걸', '윷') else plain)


def where(pos):
    return '판 밖' if pos == 0 else f'{pos}번 칸'


def place_name(d):
    return OUT if d == OUT else f'{d}번 칸'


def captures(mine, theirs, label, throw, rule):
    d = dest(mine[label], THROWS[throw], rule)
    return d != OUT and d in theirs


def exits(mine, label, throw, rule):
    return dest(mine[label], THROWS[throw], rule) == OUT


def two_step(pos, first, second, theirs, rule):
    """한 말에 두 결과를 차례로 쓴다. 상대 말을 하나라도 잡으면 True. 첫 결과로 나가면 두 번째는 못 쓴다."""
    left = set(theirs)
    got = False
    for t in (first, second):
        if pos == OUT:
            break
        pos = dest(pos, THROWS[t], rule)
        if pos != OUT and pos in left:
            left.discard(pos)
            got = True
    return got


def situation(mine, theirs):
    m = ', '.join(f'{k}({where(v)})' for k, v in mine.items())
    t = ', '.join(where(v) for v in sorted(theirs))
    return f'내 말: {m}. 상대 말: {t}.'


def _stations(rule):
    return list(range(1, 20)) + ([21, 22, 23, 24, 25, 26, 27] if RULES[rule][0] else [])


def _one_twin(solve, base_ans):
    """변형 규칙 중 답이 하나로 정해지고 달라지는 첫 규칙 (없으면 None)."""
    for r in ('noshort', 'arrive'):
        a = solve(r)
        if a is not None and a != base_ans:
            return r, a
    return None


def generate(rng, per_stage):
    items = []
    k2 = 0

    def add_twin(base, state, q, opts, twin):
        nonlocal k2
        r, a = twin
        items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=rule_text(r)), q, opts, a,
                               original=next(o for o in opts if base['options'][base['answer'] - 1] == o),
                               twin_of=base['id'], order=base['options']))
        k2 += 1

    # ① 판정: 말 하나의 도착 칸. 시작 칸은 모서리·지름길·끝 근처를 골고루 섞는다.
    starts = [0, 5, 10, 3, 8, 22, 27, 17, 18, 24, 25, 16, 2, 13]
    rng.shuffle(starts)
    n = 0
    for pos in starts:
        if n >= per_stage:
            break
        throw = rng.choice(list(THROWS))
        if pos in (17, 18, 16, 24, 25):   # 20번에 딱 맞게 서는 결과를 자주 쓴다
            throw = next(t for t, s in THROWS.items() if s == len(path_from(pos, 'standard')))
        ans = place_name(dest(pos, THROWS[throw], 'standard'))
        twin = _one_twin(lambda r: place_name(dest(pos, THROWS[throw], r)) if pos not in (21, 22, 23, 24, 25, 26, 27)
                         or RULES[r][0] else None, ans)
        cands = {ans} | {place_name(dest(pos, s, r)) for r in RULES for s in {THROWS[throw] - 1, THROWS[throw] + 1, THROWS[throw]} if 1 <= s <= 5
                         and (pos < 21 or RULES[r][0])}
        cands.discard(None)
        pool = [place_name(s) for s in _stations('standard') + [20]] + [OUT]
        rng.shuffle(pool)
        opts = sorted(cands, key=str)[:5]
        for p in pool:
            if len(opts) >= 6:
                break
            if p not in opts:
                opts.append(p)
        if ans not in opts:
            opts[0] = ans
        state = {'규칙': rule_text('standard'), '상황': f'내 말 하나가 {where(pos)}에 있다. 이번에 {josa(throw, "이", "가")} 나왔다.'}
        q = '이 말을 움직이면 어디에 도착하는가?'
        base = make_item(rng, GAME, '1-판정', n, state, q, opts, ans)
        items.append(base)
        if twin is not None and twin[1] in opts:
            add_twin(base, state, q, opts, twin)
        n += 1

    # ③ 한 수: 이번 결과로 상대 말을 잡는(또는 나는) 내 말이 하나뿐
    n, tries = 0, 0
    need_twin = per_stage // 2
    got_twin = 0
    while n < per_stage:
        tries += 1
        assert tries < 200000
        goal = 'capture' if n % 3 != 2 else 'exit'
        k = rng.randint(2, 4)
        # 지름길 규칙만 바꿔 답이 달라지려면 두 모서리(5·10번)에 모두 내 말이 있어야 한다(한 말만 길이 바뀌면
        # 다른 말의 잡기 여부는 그대로라 답이 둘이 되거나 그대로다). 짝을 모으는 동안에는 두 모서리에 말을 둔다.
        hot = [5, 10] if got_twin < need_twin and tries % 5 else []
        rest = rng.sample([s for s in _stations('standard') + [0] if s not in hot], k - len(hot))
        mine = dict(zip(LABELS, rng.sample(hot + rest, k)))
        theirs = set(rng.sample([s for s in _stations('standard') if s not in mine.values()], rng.randint(2, 4)))
        throw = rng.choice(list(THROWS))
        if hot:   # 한 모서리 말은 지름길로, 다른 모서리 말은 바깥 길로 가야 잡도록 상대 말을 놓아 본다
            goal = 'capture'
            a, b = rng.sample(hot, 2)
            want = {dest(a, THROWS[throw], 'standard'), dest(b, THROWS[throw], 'noshort')} - set(mine.values())
            theirs = (want | set(rng.sample(sorted(theirs), 1))) - {OUT}

        def solve(r):
            if not RULES[r][0] and any(v > 20 for v in mine.values()):
                return None   # 지름길이 없는 규칙에서는 지름길 칸에 말이 있을 수 없다
            ok = [lab for lab in mine if (captures(mine, theirs, lab, throw, r) if goal == 'capture'
                                          else exits(mine, lab, throw, r))]
            return ok[0] if len(ok) == 1 else None
        ans = solve('standard')
        if ans is None:
            continue
        twin = _one_twin(solve, ans)
        if twin is None and got_twin < need_twin and tries % 5:
            continue   # 짝이 되는 상황을 먼저 모은다
        q = (f'이번에 {josa(throw, "이", "가")} 나왔다. 상대 말을 잡으려면 어느 말을 움직여야 하는가?' if goal == 'capture'
             else f'이번에 {josa(throw, "이", "가")} 나왔다. 말 하나를 판에서 나가게 하려면 어느 말을 움직여야 하는가?')
        state = {'규칙': rule_text('standard'), '상황': situation(mine, theirs)}
        opts = list(mine)
        base = make_item(rng, GAME, '3-한수', n, state, q, opts, ans)
        items.append(base)
        if twin is not None:
            add_twin(base, state, q, opts, twin)
            got_twin += 1
        n += 1

    # ④ 앞보기: 두 결과를 한 말에 차례로 쓸 때 상대 말을 잡는 (말, 순서)가 하나뿐
    n, tries = 0, 0
    while n < per_stage:
        tries += 1
        assert tries < 200000
        k = rng.randint(2, 3)
        mine = dict(zip(LABELS, rng.sample([s for s in range(1, 20) if s not in (5, 10)] + [21, 26, 0], k)))
        theirs = set(rng.sample([s for s in _stations('standard') if s not in mine.values()], rng.randint(2, 3)))
        t1, t2 = rng.sample(list(THROWS), 2)
        opts = {f'{lab}: {a} 먼저, {b} 나중': (lab, a, b) for lab in mine for a, b in ((t1, t2), (t2, t1))}

        def solve4(r):
            if not RULES[r][0] and any(v > 20 for v in mine.values()):
                return None
            ok = [o for o, (lab, a, b) in opts.items() if two_step(mine[lab], a, b, theirs, r)]
            return ok[0] if len(ok) == 1 else None
        ans = solve4('standard')
        if ans is None:
            continue
        q = (f'이번 차례에 {josa(t1, "과", "와")} {josa(t2, "이", "가")} 나왔다. 두 결과를 모두 한 말에 차례로 쓴다(어느 것을 먼저 쓸지는 고를 수 있다). '
             '각 결과로 움직임을 마칠 때마다 잡기를 따진다. 상대 말을 하나라도 잡으려면 어느 말을 어떤 순서로 움직여야 하는가?')
        state = {'규칙': rule_text('standard'), '상황': situation(mine, theirs)}
        base = make_item(rng, GAME, '4-앞보기', n, state, q, list(opts), ans)
        items.append(base)
        twin = _one_twin(solve4, ans)
        if twin is not None:
            add_twin(base, state, q, list(opts), twin)
        n += 1
    return items
