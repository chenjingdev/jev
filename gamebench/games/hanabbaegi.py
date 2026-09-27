"""하나빼기 (가위바위보 하나 빼기).

규칙 문구는 BEATS에서 만들고, 풀이기도 같은 상성을 읽는다.
① 판정: 두 사람이 남긴 손으로 누가 이기는지, 또는 상대가 남길 손을 알 때 이기기·비기기·지기 위해 남길 손.
③ 한 수: 상대가 어느 손을 남길지 모를 때 어떤 경우에도 지지 않는 손(정확히 하나인 국면만).
② 변형: 같은 상황·보기에서 상성이 모두 뒤집힌 규칙. 답이 달라지는 문항만 짝으로 쓴다.
"""
from .common import make_item

GAME = 'hanabbaegi'
NAME = '하나빼기'
FACET = '규칙 판정'

HANDS = ['가위', '바위', '보']
STANDARD = {'가위': '보', '바위': '가위', '보': '바위'}  # 키가 값을 이긴다
REVERSED = {v: k for k, v in STANDARD.items()}
RESULTS = ['내가 이긴다', '상대가 이긴다', '비긴다']
GOALS = {'이기려면': '내가 이긴다', '비기려면': '비긴다', '지려면': '상대가 이긴다'}


def rules_text(beats):
    return ('두 사람이 각자 양손에 가위, 바위, 보 중 하나씩을 동시에 낸다. 두 손에 같은 것을 내도 된다. '
            '그다음 두 사람이 동시에 한 손을 빼고, 남은 한 손끼리 겨룬다. '
            + ', '.join(f'{a}는 {b}를 이긴다' for a, b in beats.items())
            + '. 남은 손이 같으면 비긴다.')


def result(beats, mine, opp):
    if mine == opp:
        return '비긴다'
    return '내가 이긴다' if beats[mine] == opp else '상대가 이긴다'


def keep_for(beats, my_pair, opp_kept, goal):
    hs = [h for h in my_pair if result(beats, h, opp_kept) == goal]
    return hs[0] if len(hs) == 1 else None


def never_lose(beats, my_pair, opp_pair):
    hs = [h for h in my_pair if all(result(beats, h, o) != '상대가 이긴다' for o in opp_pair)]
    return hs[0] if len(hs) == 1 else None


def situation(my_pair, opp_pair):
    return f'나는 {my_pair[0]}와 {my_pair[1]}를 냈고, 상대는 {opp_pair[0]}와 {opp_pair[1]}를 냈다.'


def generate(rng, per_stage):
    items = []
    std, rev = rules_text(STANDARD), rules_text(REVERSED)
    my_pairs = [(a, b) for a in HANDS for b in HANDS if a != b]            # 순서 있는 서로 다른 두 손
    opp_pairs = [(a, b) for a in HANDS for b in HANDS]
    # ① (가) 남은 손으로 결과 판정
    judge = [(m, o, mk, ok) for m in my_pairs for o in opp_pairs for mk in m for ok in o]
    rng.shuffle(judge)
    # ① (나) 상대가 남길 손을 알 때 목표를 이루는 손 (정확히 하나)
    goal = [(m, o, ok, g) for m in my_pairs for o in opp_pairs for ok in o for g in GOALS
            if keep_for(STANDARD, m, ok, GOALS[g])]
    rng.shuffle(goal)
    n_judge = per_stage // 2
    k = 0
    for i in range(per_stage):
        if i < n_judge:
            m, o, mk, ok = judge[i]
            sit = situation(m, o) + f' 한 손씩 뺀 뒤 나는 {mk}, 상대는 {ok}를 남겼다.'
            q, opts = '결과는?', RESULTS
            ans, twin = result(STANDARD, mk, ok), result(REVERSED, mk, ok)
        else:
            m, o, ok, gk = goal[i - n_judge]
            sit = situation(m, o) + f' 상대가 {ok}를 남긴다는 것을 알고 있다.'
            q, opts = f'내가 {gk} 어느 손을 남겨야 하는가?', list(m)
            ans, twin = keep_for(STANDARD, m, ok, GOALS[gk]), keep_for(REVERSED, m, ok, GOALS[gk])
        base = make_item(rng, GAME, '1-판정', i, {'규칙': std, '상황': sit}, q, opts, ans)
        items.append(base)
        if twin is not None and twin != ans:
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rev, '상황': sit}, q, opts, twin,
                                   original=ans, twin_of=base['id'], order=base['options']))
            k += 1
    # ③ 상대가 어느 손을 남길지 모를 때 지지 않는 손
    q3 = '상대가 어느 손을 남길지 모른다. 어떤 경우에도 지지 않으려면 나는 어느 손을 남겨야 하는가?'
    pool = [(m, o) for m in my_pairs for o in opp_pairs if never_lose(STANDARD, m, o)]
    rng.shuffle(pool)
    for i, (m, o) in enumerate(pool[:per_stage]):
        sit = situation(m, o)
        ans, twin = never_lose(STANDARD, m, o), never_lose(REVERSED, m, o)
        base = make_item(rng, GAME, '3-한수', i, {'규칙': std, '상황': sit}, q3, list(m), ans)
        items.append(base)
        if twin is not None and twin != ans:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, {'규칙': rev, '상황': sit}, q3, list(m), twin,
                                   original=ans, twin_of=base['id'], order=base['options']))
    return items
