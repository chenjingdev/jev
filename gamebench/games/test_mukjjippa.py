"""묵찌빠 풀이기 손 검사. 기대값은 규칙 문구에서 손으로 따졌다."""
from build import game_rng, validate
from games import mukjjippa as g


def test_rule_text_mentions_both_branches():
    assert '이긴 손을 낸 사람이 공격자' in g.rules_text('winner')
    assert '진 손을 낸 사람이 공격자' in g.rules_text('loser')


def test_outcome_by_hand():
    # 같은 손이면 공격자가 이긴다
    assert g.outcome('winner', '나', '빠', '빠') == '내가 이긴다'
    assert g.outcome('winner', '상대', '묵', '묵') == '상대가 이긴다'
    # 공격자인 내가 찌, 상대 묵: 묵이 찌를 이기므로 상대가 공격자
    assert g.outcome('winner', '나', '찌', '묵') == '상대가 공격자가 되어 다시 낸다'
    # 수비인 내가 빠, 상대 묵: 빠가 묵을 이기므로 내가 공격자
    assert g.outcome('winner', '상대', '빠', '묵') == '내가 공격자가 되어 다시 낸다'
    # 진 사람이 공격자가 되는 규칙: 내가 빠(이김), 상대 묵 → 상대가 공격자
    assert g.outcome('loser', '상대', '빠', '묵') == '상대가 공격자가 되어 다시 낸다'
    assert g.outcome('loser', '나', '찌', '묵') == '내가 공격자가 되어 다시 낸다'


def test_goal_hands_by_hand():
    # 내가 공격자, 상대 찌: 이기려면 찌, 공격자로 남으려면 찌를 이기는 묵, 넘기려면 찌에 지는 빠
    assert g.hand_for('winner', '나', '찌', '내가 이긴다') == '찌'
    assert g.hand_for('winner', '나', '찌', '내가 공격자가 되어 다시 낸다') == '묵'
    assert g.hand_for('winner', '나', '찌', '상대가 공격자가 되어 다시 낸다') == '빠'
    # 상대가 공격자, 상대 빠: 지려면 빠, 공격권을 빼앗으려면 빠를 이기는 찌
    assert g.hand_for('winner', '상대', '빠', '상대가 이긴다') == '빠'
    assert g.hand_for('winner', '상대', '빠', '내가 공격자가 되어 다시 낸다') == '찌'
    # 진 사람이 공격자: 공격권을 빼앗으려면 빠에 지는 묵
    assert g.hand_for('loser', '상대', '빠', '내가 공격자가 되어 다시 낸다') == '묵'


def test_safe_hands_by_hand():
    lose = {'상대가 이긴다'}
    lose_attack = {'상대가 이긴다', '상대가 공격자가 되어 다시 낸다'}
    # 수비: 상대가 묵 아니면 찌 → 둘 다 아닌 빠만 안전
    assert g.safe_hand('winner', '상대', ('묵', '찌'), lose) == '빠'
    # 공격: 상대가 묵 아니면 찌. 묵을 내면 묵→이김, 찌→묵이 이겨 공격 유지
    assert g.safe_hand('winner', '나', ('묵', '찌'), lose_attack) == '묵'
    # 진 사람이 공격자: 찌를 내면 찌→이김, 묵→찌가 져서 내가 공격자
    assert g.safe_hand('loser', '나', ('묵', '찌'), lose_attack) == '찌'


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
