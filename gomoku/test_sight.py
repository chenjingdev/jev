import copy
import random

import pytest
import engine as E
import sight


@pytest.mark.parametrize('seed', range(1, 21))
def test_selfplay_history_and_all_representations(seed):
    p = sight.position_for_seed(seed)
    sight.validate(p)
    b = E.new_board()
    sequence = sight.state_for(p, 'sequence')['moves']
    for i, token in enumerate(sequence.split()):
        r, c = E.parse_coord(token.split('.')[1])
        player = E.BLACK if i % 2 == 0 else E.WHITE
        assert not b[r][c]
        assert not E.forbidden(b, r, c, player)
        if i:
            assert E.neighbours(b, r, c, 2)
        b[r][c] = player
        assert not E.winner(b)
    assert b == p.board
    assert sum(v == E.BLACK for row in b for v in row) == 1 + sum(v == E.WHITE for row in b for v in row)
    assert len(sight.options_for(b, 'all')) == 225 - len(p.moves)
    for kind in ('all', 'near', 'sheet'):
        assert E.coord(*p.hole) in sight.options_for(b, kind)
    for kind in ('all', 'near', 'sheet'):
        assert all(v is None for v in sight.options_for(b, kind).values())
    stones = sight.state_for(p, 'stones')
    for colour, value in [('white_stones', E.WHITE), ('black_stones', E.BLACK)]:
        assert set(stones[colour]) == {E.coord(r,c) for r in range(15) for c in range(15) if b[r][c] == value}
    r,c = p.hole
    b[r][c] = E.WHITE
    assert E.winner(b) == E.WHITE


def test_corruption_is_rejected_before_api(monkeypatch):
    p = copy.deepcopy(sight.position_for_seed(1))
    r,c = E.parse_coord(p.moves[1]); p.board[r][c] = E.BLACK
    monkeypatch.setattr(sight.brain, 'client', lambda: pytest.fail('API must not be called'))
    with pytest.raises(ValueError, match='reconstruct'):
        sight.ask(p, 'all', 'sequence')


def test_wrong_turn_and_target_rejected():
    p = copy.deepcopy(sight.position_for_seed(1)); p.moves.pop()
    with pytest.raises(ValueError, match='white to move'):
        sight.validate(p)
    p = copy.deepcopy(sight.position_for_seed(1)); p.hole = (0, 0)
    with pytest.raises(ValueError, match='winning point'):
        sight.validate(p)


def test_parallel_requests_do_not_share_mutable_board(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    p = sight.position_for_seed(1)
    original = copy.deepcopy(p.board)
    target = E.coord(*p.hole)
    fake = SimpleNamespace(system_one=lambda **kwargs: SimpleNamespace(
        answers={'point': SimpleNamespace(choice=target, probabilities={target:1.0}, confidence=1.0)}, usage=None))
    monkeypatch.setattr(sight.brain, 'client', lambda: fake)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: sight.ask(p, 'sheet', sight.REPS[i % 4]), range(32)))
    assert all(r['hit'] for r in results)
    assert p.board == original


def test_batch_deduplicates_positions(monkeypatch, tmp_path):
    import json
    import sys
    from types import SimpleNamespace
    first, second = sight.position_for_seed(1), sight.position_for_seed(2)
    monkeypatch.setattr(sight, 'position_for_seed', lambda seed: first if seed < 3 else second)
    def respond(**kwargs):
        choice = next(iter(kwargs['questions']['point'].criteria))
        return SimpleNamespace(answers={'point': SimpleNamespace(choice=choice, probabilities={choice:1.0}, confidence=1.0)}, usage=None)
    monkeypatch.setattr(sight.brain, 'client', lambda: SimpleNamespace(system_one=respond))
    out = tmp_path / 'results.json'
    monkeypatch.setattr(sys, 'argv', ['sight.py', '--positions', '2', '--kinds', 'all', '--reps', 'sequence', '--out', str(out)])
    assert sight.main() == 0
    result = json.loads(out.read_text())
    assert result['position_seeds'] == [1, 3]
    assert len(result['dataset']) == len(result['trials']) == 2
