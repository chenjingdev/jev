"""포켓몬 타입 상성 풀이기 손 검사. 기대값은 규칙 문구의 표에서 손으로 따졌다."""
from build import game_rng, validate
from games import pokemon_types as g

C = g.CHART


def test_mult_by_hand():
    assert g.mult(C, '물', ('불',)) == 2
    assert g.mult(C, '불', ('비행',)) == 1          # 표에 없음
    assert g.mult(C, '전기', ('물', '비행')) == 4    # 2 × 2
    assert g.mult(C, '전기', ('물', '땅')) == 0      # 2 × 0
    assert g.mult(C, '풀', ('물', '비행')) == 1      # 2 × 0.5
    assert g.mult(C, '땅', ('불', '전기')) == 4


def test_extreme_by_hand():
    # 불 하나: 물 2, 땅 2 → 가장 큰 게 둘이라 정해지지 않는다
    assert g.extreme(C, ('불',), ['물', '땅', '풀'], 'max') is None
    # 불 하나, 보기 물·풀·비행: 물 2, 풀 0.5, 비행 1
    assert g.extreme(C, ('불',), ['물', '풀', '비행'], 'max') == '물'
    assert g.extreme(C, ('불',), ['물', '풀', '비행'], 'min') == '풀'
    # 비행 하나, 보기 땅·전기·불: 땅 0 → 가장 작다
    assert g.extreme(C, ('비행',), ['땅', '전기', '불'], 'min') == '땅'
    # 물·땅: 풀 2×2=4, 전기 2×0=0, 불 0.5×1=0.5, 물 0.5×2=1
    assert g.extreme(C, ('물', '땅'), ['풀', '전기', '불', '물'], 'max') == '풀'
    # 풀·비행: 불 2, 비행 2, 전기 0.5×2=1, 땅 0.5×0=0 → 불·비행 동률
    assert g.extreme(C, ('풀', '비행'), ['불', '비행', '전기'], 'max') is None


def test_modified_chart():
    c = g.modified(C, '땅', '불', 0.5)
    assert g.mult(c, '땅', ('불',)) == 0.5 and g.mult(C, '땅', ('불',)) == 2
    assert '땅 기술: 전기에 2배, 불·풀에 0.5배' in g.rules_text(c)


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
        # 표가 정확히 한 줄만 다르다
        diff = [a for a, b in zip(t['state']['규칙'].split('\n'), base['state']['규칙'].split('\n')) if a != b]
        assert len(diff) == 1
