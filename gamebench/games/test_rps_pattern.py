"""가위바위보 상대 패턴 풀이기 손 검사. 기대값은 규칙·방식 문구에서 손으로 따졌다."""
from build import game_rng, validate
from games import rps_pattern as g

S, R = g.STANDARD, g.REVERSED
P = {p[0]: p for p in g.PATTERNS}


def test_predict_by_hand():
    h = [('바위', '가위')]  # 직전 판: 나 바위, 상대 가위 (상대가 졌다)
    assert g.predict(S, P['가'], h) == '가위'
    assert g.predict(S, P['나'], h) == '바위'   # 가위를 이기는 손
    assert g.predict(S, P['다'], h) == '보'     # 가위에 지는 손
    assert g.predict(S, P['마'], h) == '보'     # 바위를 이기는 손
    assert g.predict(S, P['바'], h) == '가위'   # 바위에 지는 손
    assert g.predict(S, P['사'], h) == '바위'   # 졌으니 가위를 이기는 바위
    assert g.predict(S, P['사'], [('보', '가위')]) == '가위'  # 이겼으니 그대로
    # 뒤집힌 상성(보가 가위를 이긴다): 가위를 이기는 손은 보
    assert g.predict(R, P['나'], h) == '보'


def test_answer_by_hand():
    h = [('가위', '가위'), ('보', '바위')]
    # (라) 내 직전 손 보를 따라 → 상대 보, 이기려면 가위, 지려면 바위
    assert g.answer(S, P['라'], h, 'next') == '보'
    assert g.answer(S, P['라'], h, 'win') == '가위'
    assert g.answer(S, P['라'], h, 'lose') == '바위'
    # 뒤집힌 상성에서 보를 이기는 손은 바위
    assert g.answer(R, P['라'], h, 'win') == '바위'


def test_matching_by_hand():
    # 상대: 가위→바위→보→가위 (자기 직전 손을 이기는 손). 나는 늘 가위.
    # (라)는 둘째 판 가위≠바위, (마)는 셋째 판 바위≠보, (바)는 둘째 판 보≠바위,
    # (사)는 첫 판 비겨서 바위(맞음), 둘째 판 이겨서 바위여야 하는데 보라서 어긋난다.
    h = [('가위', '가위'), ('가위', '바위'), ('가위', '보'), ('가위', '가위')]
    assert g.matching(S, h) == [P['나']]
    # 뒤집힌 상성에서는 같은 기록이 "자기 직전 손에 지는 손"이다
    assert g.matching(R, h) == [P['다']]
    # 같은 손만 두 번이면 (가)와 (라)를 가를 수 없다. (사)는 비겼으니 바위를 냈어야 해서 빠진다
    assert g.matching(S, [('가위', '가위'), ('가위', '가위')]) == [P['가'], P['라']]


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
