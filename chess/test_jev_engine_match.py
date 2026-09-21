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
