from contextlib import nullcontext
from types import SimpleNamespace
import chess
import chess.engine
import pytest
from jev_engine_match import make_request, shortlist, collect_candidates, ask_jev, summarize


def test_request_contains_only_board_and_unlabelled_coordinates():
    board = chess.Board()
    moves = ['e2e4', 'd2d4', 'g1f3']
    request = make_request(board, moves, 18)
    assert set(request['state']) == {'side_to_move', 'pieces', 'castling_rights', 'en_passant'}
    assert len(request['state']['pieces']) == 32
    assert request == make_request(board, list(reversed(moves)), 18)
    assert request['questions']['move']['criteria'] == dict.fromkeys(request['questions']['move']['criteria'])
    assert set(request['questions']['move']['criteria']) == set(moves)
    with pytest.raises(ValueError):
        make_request(board, ['e2e5', 'e2e4'], 18)


def test_margin_and_mates():
    rows = [{'move': 'e2e4', 'cp': 50}, {'move': 'd2d4', 'cp': 15}, {'move': 'g1f3', 'cp': 14}]
    assert shortlist(rows, 35) == ['e2e4', 'd2d4']
    rows[0]['cp'] = None
    assert shortlist(rows, 35) == ['e2e4']


def test_partial_multipv_depth_is_not_mixed_with_complete_depth():
    infos = []
    for rank, uci in enumerate(['e2e4', 'd2d4', 'g1f3'], 1):
        infos.append({'depth': 4, 'multipv': rank, 'nodes': rank * 100,
                      'score': chess.engine.PovScore(chess.engine.Cp(40-rank), chess.WHITE),
                      'pv': [chess.Move.from_uci(uci)]})
    infos.append({**infos[0], 'depth': 5, 'nodes': 5000})
    infos.append({**infos[1], 'multipv': 1, 'depth': 4, 'nodes': 5001})
    class Engine:
        def configure(self, options): pass
        def analysis(self, board, limit, **kwargs):
            assert limit.nodes == 5000 and kwargs['multipv'] == 3
            return nullcontext(iter(infos))
    rows, info = collect_candidates(Engine(), chess.Board(), 5000)
    assert info['depth'] == 4 and info['nodes'] == 5001
    assert len(rows) == 3
    assert rows[0]['move'] == 'e2e4'


def test_success_response_serializes_installed_sdk_without_model_dump():
    request = make_request(chess.Board(), ['e2e4', 'd2d4'], 1)
    response = SimpleNamespace(model='jev-1.13.0', usage=SimpleNamespace(input_tokens=100, output_tokens=20),
                               answers={'move': SimpleNamespace(choice='d2d4', confidence=.8,
                                                                probabilities={'e2e4': .2, 'd2d4': .8})})
    result = ask_jev(SimpleNamespace(system_one=lambda **kw: response), request, 'e2e4')
    assert result['intervention'] and result['selected_move'] == 'd2d4'
    assert result['response']['usage'] == {'input_tokens': 100, 'output_tokens': 20}


def test_invalid_jev_choice_never_becomes_an_active_move():
    request = make_request(chess.Board(), ['e2e4', 'd2d4'], 1)
    client = SimpleNamespace(system_one=lambda **kw: SimpleNamespace(answers={
        'move': SimpleNamespace(choice='a1a8', probabilities={'e2e4': .5, 'd2d4': .5})}))
    with pytest.raises(ValueError):
        ask_jev(client, request, 'e2e4')


def test_unfinished_games_do_not_count_as_draws():
    result = summarize({'games': [{'result': '*', 'white': 'Stockfish', 'black': 'Stockfish + Jev', 'moves': []}]})
    assert result['finished_games'] == 0
    assert sum(result['points'].values()) == 0


def test_random_control_is_seeded_uniform_and_never_recorded_as_jev():
    from jev_engine_match import random_pick, HYBRID_NAMES
    a = random_pick(['e2e4', 'd2d4', 'g1f3'], 'e2e4', 73419, 1, 9)
    b = random_pick(['g1f3', 'e2e4', 'd2d4'], 'e2e4', 73419, 1, 9)
    assert a == b and a['selected_move'] in a['options'] and a['selector'] == 'random'
    assert 'jev' not in a and 'probabilities' not in a
    picks = {random_pick(['e2e4', 'd2d4', 'g1f3'], 'e2e4', 73419, 1, ply)['selected_move'] for ply in range(60)}
    assert picks == {'e2e4', 'd2d4', 'g1f3'}
    payload = {'engine_a': {'name': HYBRID_NAMES['random']},
               'games': [{'result': '1-0', 'white': 'Stockfish + Random', 'black': 'Stockfish',
                          'moves': [{'jev': None, 'random_control': a}]}]}
    result = summarize(payload)
    assert result['points'] == {'Stockfish + Random': 1, 'Stockfish': 0}
    assert result['calls'] == 0 and result['random_picks'] == 1 and result['random_interventions'] == 1


def test_confidence_gate_plays_base_but_keeps_jev_answer():
    from jev_engine_match import hybrid_name_for
    assert hybrid_name_for('weak', 'jev', 0.2) == 'Weak + Jev(conf>=0.2)'
    assert hybrid_name_for('weak', 'jev', None) == 'Weak + Jev'
    low = {'base_move': 'e2e4', 'selected_move': 'd2d4', 'intervention': True, 'confidence': 0.1,
           'latency_ms': 1, 'response': {'usage': {'input_tokens': 1, 'output_tokens': 0}}}
    # mirror the gate in run(): below the threshold the base move is played, Jev's move is kept aside
    low.update(jev_move=low['selected_move'], selected_move=low['base_move'], intervention=False, gated=True)
    high = {'base_move': 'e2e4', 'selected_move': 'd2d4', 'jev_move': 'd2d4', 'intervention': True, 'gated': False,
            'confidence': 0.6, 'latency_ms': 1, 'response': {'usage': {'input_tokens': 1, 'output_tokens': 0}}}
    payload = {'engine_a': {'name': 'Weak2 + Jev(conf>=0.2)'}, 'engine_b': {'name': 'Weak2'},
               'games': [{'result': '1/2-1/2', 'white': 'Weak2 + Jev(conf>=0.2)', 'black': 'Weak2',
                          'moves': [{'jev': low}, {'jev': high}]}]}
    result = summarize(payload)
    assert result['calls'] == 2 and result['interventions'] == 1 and result['gated'] == 1 and result['jev_disagreed'] == 2
    assert low['selected_move'] == 'e2e4' and low['jev_move'] == 'd2d4'


def test_noise_is_seeded_and_bounded_and_reranks():
    from jev_engine_match import add_noise
    rows = lambda: [{'move': 'a2a3', 'raw': 10, 'cp': 10}, {'move': 'b2b3', 'raw': 10, 'cp': 10}, {'move': 'c2c3', 'raw': -300, 'cp': -300}]
    a = add_noise(rows(), 15, 1, 1, 1); b = add_noise(rows(), 15, 1, 1, 1)
    assert a == b and all(abs(r['noise']) <= 15 for r in a) and [r['rank'] for r in a] == [1, 2, 3]
    assert a[0]['raw'] >= a[1]['raw'] >= a[2]['raw'] and a[2]['move'] == 'c2c3'
    assert add_noise(rows(), 0, 1, 1, 1) == rows()


def test_sparse_random_control_has_explicit_change_probability():
    from jev_engine_match import random_pick
    options = ['e2e4', 'd2d4', 'g1f3']
    for ply in range(20):
        zero = random_pick(options, 'e2e4', 73419, 1, ply, 0)
        one = random_pick(options, 'e2e4', 73419, 1, ply, 1)
        assert zero['selected_move'] == 'e2e4' and not zero['intervention']
        assert one['selected_move'] in ('d2d4', 'g1f3') and one['intervention']
        a = random_pick(options, 'e2e4', 73419, 1, ply, .1)
        b = random_pick(list(reversed(options)), 'e2e4', 73419, 1, ply, .1)
        assert a == b
        assert a['intervention'] == (a['selected_move'] != a['base_move'])
        assert a['intervention'] == (a['gate_draw'] < .1)


def test_stockfish_run_keeps_engine_type_across_turns_and_games(tmp_path, monkeypatch):
    import jev_engine_match as match
    calls = []
    engine = SimpleNamespace(id={'name': 'test engine'}, configure=lambda options: None)
    monkeypatch.setattr(match.chess.engine.SimpleEngine, 'popen_uci', lambda path: nullcontext(engine))
    def collect(engine, board, nodes):
        calls.append(board.fen())
        move = sorted(m.uci() for m in board.legal_moves)[0]
        return [{'move': move, 'cp': 0, 'mate': None}], {'depth': 1, 'nodes': 1}
    monkeypatch.setattr(match, 'collect_candidates', collect)
    d = match.run(tmp_path / 'stockfish', 'unused', selector='none', max_plies=2)
    assert len(calls) == 4 and [g['plies'] for g in d['games']] == [2, 2]
    assert d['status'] == 'complete' and d['base_engine'] == 'stockfish'


def test_sparse_zero_run_matches_plain_and_never_uses_api(tmp_path, monkeypatch):
    import jev_engine_match as match
    def forbidden_client(**kwargs):
        raise AssertionError('This control must not call Jev')
    monkeypatch.setattr(match, 'TypeSafeClient', forbidden_client)
    settings = dict(engine_path='unused', base='weak', depth=1, noise=10, max_plies=4)
    plain = match.run(tmp_path / 'plain', selector='none', **settings)
    sparse = match.run(tmp_path / 'sparse', selector='random', random_intervention_probability=0, **settings)
    assert [[m['uci'] for m in g['moves']] for g in sparse['games']] == [[m['uci'] for m in g['moves']] for g in plain['games']]
    assert sparse['summary']['random_picks'] > 0
    assert sparse['summary']['random_interventions'] == sparse['summary']['calls'] == 0


def test_sparse_probability_rejected_for_other_selectors(tmp_path):
    from jev_engine_match import run
    with pytest.raises(ValueError, match='requires selector=random'):
        run(tmp_path / 'invalid', 'unused', selector='none', random_intervention_probability=.1)
    assert not (tmp_path / 'invalid.json').exists()
