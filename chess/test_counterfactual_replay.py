import chess
from counterfactual_replay import finish, collect_jobs, summarize


def test_finish_scores_from_hybrid_side_and_detects_immediate_mate():
    # Fool's mate position with Black to move: Qh4# is the depth-2 engine's move.
    board = chess.Board('rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2')
    score, term = finish(board, 4, hybrid_white=True, depth_hybrid=2, depth_opponent=2)
    assert term == 'checkmate' and score == 0.0  # hybrid is White and gets mated


def test_collect_jobs_only_takes_disagreements_and_keeps_jev_answer_when_gated():
    payload = {'engine_a': {'name': 'H'}, 'depth': 2, 'opponent_depth': 2,
               'games': [{'game': 1, 'white': 'H', 'black': 'B', 'result': '1/2-1/2', 'opening_uci': ['e2e4', 'e7e5'],
                          'moves': [{'ply': 1, 'uci': 'g1f3', 'jev': {'base_move': 'g1f3', 'selected_move': 'g1f3', 'jev_move': 'b1c3', 'gated': True, 'confidence': 0.1}},
                                    {'ply': 2, 'uci': 'b8c6', 'jev': None},
                                    {'ply': 3, 'uci': 'f1c4', 'jev': {'base_move': 'f1c4', 'selected_move': 'f1c4', 'confidence': 0.9}}]}]}
    jobs = collect_jobs(payload)
    assert len(jobs) == 1 and jobs[0][3] == 'b1c3' and jobs[0][4] == 'g1f3' and jobs[0][-1]['played'] is False


def test_summarize_counts_better_same_worse():
    rows = [{'sel_result': 1, 'base_result': .5, 'played': True, 'confidence': .5},
            {'sel_result': 0, 'base_result': .5, 'played': False, 'confidence': .1},
            {'sel_result': .5, 'base_result': .5, 'played': True, 'confidence': .45}]
    s = summarize(rows)
    assert s['all_disagreements']['better'] == 1 and s['all_disagreements']['worse'] == 1 and s['all_disagreements']['same'] == 1
    assert s['played']['n'] == 2 and s['gated_out']['n'] == 1 and '0.4-0.5' in s['by_confidence']
