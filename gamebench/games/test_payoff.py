"""보상표 풀이기 손 검사. 기대값은 규칙 문구의 표에서 손으로 따졌다."""
from build import game_rng, validate
from games import payoff as g

PD = [[(3, 3), (0, 5)],
      [(5, 0), (1, 1)]]           # 행: 협력, 배신 / 열: 상대 협력, 배신
T3 = [[(4, 1), (2, 2), (7, 0)],
      [(6, 3), (2, 5), (1, 1)],
      [(5, 0), (3, 3), (0, 9)]]   # 행: A, B, C / 열: X, Y, Z


def test_best_response_by_hand():
    assert g.best_response(PD, 0) == 1           # 상대 협력: 3 vs 5 → 배신
    assert g.best_response(PD, 1) == 1           # 상대 배신: 0 vs 1 → 배신
    assert g.best_response(PD, 1, 'min') == 0    # 가장 작게: 협력(0)
    assert g.best_response(T3, 0) == 1           # X 열: 4, 6, 5 → B
    assert g.best_response(T3, 1) == 2           # Y 열: 2, 2, 3 → C
    assert g.best_response(T3, 1, 'min') is None  # 2, 2 동률
    assert g.best_response(T3, 2, 'min') == 2    # Z 열: 7, 1, 0 → C


def test_dominant_by_hand():
    assert g.dominant(PD) == 1                   # 배신: 5>3, 1>0
    assert g.dominant(T3) is None                # A는 Z열에서만, B는 X열에서만 크다
    dom_a = [[(5, 0), (4, 0), (3, 0)],
             [(4, 0), (3, 0), (2, 0)],
             [(1, 0), (2, 0), (3, 0)]]       # A가 Z열에서 C와 3=3 동률 → 엄격 우월 아님
    assert g.dominant(dom_a) is None
    dom_a[0][2] = (4, 0)
    assert g.dominant(dom_a) == 0


def test_rules_text_table():
    text = g.rules_text(['협력', '배신'], ['협력', '배신'], PD)
    assert '협력 | (3, 3) | (0, 5)' in text and '배신 | (5, 0) | (1, 1)' in text


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
