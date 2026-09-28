"""369 풀이기 손 검사. 기대값은 규칙 문구에서 손으로 따졌다."""
from build import game_rng, validate
from games import game369 as g


def test_action_by_hand():
    assert g.action('369', 47) == '수를 그대로 말한다'
    assert g.action('369', 13) == '짝'
    assert g.action('369', 36) == '짝짝'
    assert g.action('369', 939) == '짝짝짝'
    assert g.action('369', 100) == '수를 그대로 말한다'
    # 2, 5, 8에 치는 규칙
    assert g.action('258', 36) == '수를 그대로 말한다'
    assert g.action('258', 52) == '짝짝'
    assert g.action('258', 13) == '수를 그대로 말한다'


def test_with_count_by_hand():
    # 두 번: 369 규칙에서는 33만, 258 규칙에서는 28만
    assert g.with_count('369', [33, 28, 41, 16], 2) == '33'
    assert g.with_count('258', [33, 28, 41, 16], 2) == '28'
    # 한 번: 369 규칙에서 16만 (33은 두 번)
    assert g.with_count('369', [33, 28, 41, 16], 1) == '16'
    # 0번: 369 규칙에서 28, 41 둘 → 하나로 정해지지 않는다
    assert g.with_count('369', [33, 28, 41, 16], 0) is None


def test_twins_change_answer():
    items = g.generate(game_rng(20260927, g.GAME), 10)
    assert validate(g, items) == []
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert len(twins) >= 5
    for t in twins:
        base = by_id[t['twin_of']]
        assert t['answer'] != t['original_answer'] == base['answer']
        assert '2, 5, 8' in t['state']['규칙'] and '3, 6, 9' in base['state']['규칙']
