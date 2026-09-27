"""하나빼기 풀이기 손 검사. 기대값은 규칙 문구에서 손으로 따졌다."""
from build import game_rng, validate
from games import hanabbaegi as g

S, R = g.STANDARD, g.REVERSED


def test_result_by_hand():
    assert g.result(S, '바위', '가위') == '내가 이긴다'
    assert g.result(S, '바위', '보') == '상대가 이긴다'
    assert g.result(S, '보', '보') == '비긴다'
    # 뒤집힌 상성: 보는 가위를 이긴다
    assert g.result(R, '보', '가위') == '내가 이긴다'
    assert g.result(R, '바위', '가위') == '상대가 이긴다'


def test_keep_for_by_hand():
    # 나 가위·바위, 상대가 보를 남김: 이기려면 가위, 지려면 바위
    assert g.keep_for(S, ('가위', '바위'), '보', '내가 이긴다') == '가위'
    assert g.keep_for(S, ('가위', '바위'), '보', '상대가 이긴다') == '바위'
    # 비기려면 보가 필요한데 없다
    assert g.keep_for(S, ('가위', '바위'), '보', '비긴다') is None
    # 뒤집힌 상성: 바위가 보를 이긴다
    assert g.keep_for(R, ('가위', '바위'), '보', '내가 이긴다') == '바위'


def test_never_lose_by_hand():
    # 나 가위·바위, 상대 가위·보: 가위는 가위와 비기고 보를 이긴다, 바위는 보에 진다
    assert g.never_lose(S, ('가위', '바위'), ('가위', '보')) == '가위'
    # 상대가 보·보면 가위만 안 진다
    assert g.never_lose(S, ('바위', '가위'), ('보', '보')) == '가위'
    # 나 보·가위, 상대 바위·가위: 보는 가위에 지고, 가위는 바위에 진다 → 없음
    assert g.never_lose(S, ('보', '가위'), ('바위', '가위')) is None
    # 뒤집힌 상성, 나 가위·바위, 상대 가위·보: 가위는 보에 지고, 바위는 가위에 진다 → 없음
    assert g.never_lose(R, ('가위', '바위'), ('가위', '보')) is None
    # 뒤집힌 상성, 나 가위·바위, 상대 바위·보: 바위는 바위와 비기고 보를 이긴다, 가위는 보에 진다
    assert g.never_lose(R, ('가위', '바위'), ('바위', '보')) == '바위'


def test_twins_change_answer():
    items = g.generate(game_rng(20260927, g.GAME), 10)
    assert validate(g, items) == []
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert len(twins) >= 5
    for t in twins:
        base = by_id[t['twin_of']]
        assert t['answer'] != t['original_answer'] == base['answer']
        assert t['state']['상황'] == base['state']['상황'] and t['state']['규칙'] != base['state']['규칙']
