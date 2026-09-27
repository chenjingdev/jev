"""배스킨라빈스 31: 규칙 문구에서 손으로 구한 예제."""
from games import br31
from games.br31 import BASE, MAX4, WIN31, legal, loser, winning_counts
from build import game_rng


def test_winning_counts_by_hand():
    # 31을 말하면 지고 1~3개: 30, 26, 22, ..., 2를 내가 말하고 끝내면 이긴다
    assert winning_counts(27, BASE) == [3]   # 28, 29, 30
    assert winning_counts(0, BASE) == [2]    # 1, 2
    assert winning_counts(19, BASE) == [3]   # 20, 21, 22
    assert winning_counts(26, BASE) == []    # 상대가 이미 26을 말했다
    # 1~4개: 30, 25, 20, ...
    assert winning_counts(19, MAX4) == [1]   # 20
    # 31을 말하면 이긴다: 31, 27, 23, ...
    assert winning_counts(28, WIN31) == [3]  # 29, 30, 31
    assert winning_counts(20, WIN31) == [3]  # 21, 22, 23


def test_legal_by_hand():
    assert legal(10, [11, 12, 13], BASE)
    assert not legal(10, [11, 12, 13, 14], BASE)
    assert legal(10, [11, 12, 13, 14], MAX4)
    assert not legal(10, [11, 13], BASE)
    assert not legal(10, [10, 11], BASE)


def test_loser_by_hand():
    turns = [('민수', [1, 2, 3])] + [('지우' if j % 2 == 0 else '민수', list(range(4 + 3 * j, 7 + 3 * j))) for j in range(9)]
    turns.append(('민수', [31]))
    assert turns[-2][1] == [28, 29, 30]
    assert loser(turns, BASE) == '민수'
    assert loser(turns, WIN31) == '지우'
    assert loser(turns[:5], BASE) is None


def test_twins_differ():
    items = br31.generate(game_rng(20260927, 'br31'), 10)
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        t = by_id[x['twin_of']]
        assert x['answer'] != t['answer'] and x['state']['상황'] == t['state']['상황']
        assert x['state']['규칙'] != t['state']['규칙']
