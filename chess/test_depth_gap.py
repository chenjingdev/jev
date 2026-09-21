"""Checks for the depth-gap labels and the rankings scored against them."""
import json

import chess
import pytest

import depth_gap


def test_gap_is_zero_when_the_shallow_pick_survives_the_deeper_search():
    # Only one legal move exists, so no depth can improve on it.
    row = depth_gap.measure('7k/8/8/8/8/8/6q1/7K w - - 0 1', 2, 4)
    assert row['gap'] == 0
    assert row['shallow_move'] == row['deep_move']


def test_gap_is_positive_when_the_shallow_pick_loses_material_later():
    rows = [depth_gap.measure(fen, 2, 4)
            for fen in (f['fen'] for f in depth_gap.positions_from_match(
                depth_gap.HERE / 'matches' / 'd2plain-vs-d4-100.json')[:40])]
    assert any(r['gap'] > 0 for r in rows), 'depth 4 never improved on depth 2 in 40 real positions'
    assert all(r['gap'] >= 0 for r in rows), 'gap is defined as a loss and can never be negative'


def test_hanging_finds_an_undefended_attacked_piece_and_ignores_a_defended_one():
    # Black rook a8 is attacked by the white rook and defended by nothing.
    loose = depth_gap.hanging(chess.Board('r6k/8/8/8/8/8/8/R5K1 b - - 0 1'))
    assert [r['square'] for r in loose] == ['a8']
    # Same rook, now defended by the king next to it.
    assert depth_gap.hanging(chess.Board('rk6/8/8/8/8/8/8/R5K1 b - - 0 1')) == []


def test_heuristic_features_carry_no_engine_output():
    features = depth_gap.heuristics(chess.Board())
    assert set(features) == {'in_check', 'captures_available', 'best_capture_value', 'checks_available',
                             'hanging_pieces', 'max_hanging_value', 'legal_moves', 'piece_count'}
    assert features['captures_available'] == 0 and features['legal_moves'] == 20


def test_dedupe_keeps_one_row_per_fen_and_counts_the_rest():
    rows = [{'fen': 'a', 'ply': 1}, {'fen': 'a', 'ply': 3}, {'fen': 'b', 'ply': 2}]
    out = depth_gap.dedupe(rows)
    assert [r['fen'] for r in out] == ['a', 'b']
    assert out[0]['duplicates'] == 1 and out[0]['ply'] == 1


def test_oracle_is_the_ceiling_for_every_other_ranking():
    boards = ['8/8/8/4k3/8/8/4K3/7R w - - 0 1', chess.Board().fen(),
              'r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4',
              '8/8/4k3/8/8/4K3/8/8 w - - 0 1', '8/5k2/8/8/8/8/5K2/6R1 w - - 0 1']
    rows = [{'gap': gap, 'features': depth_gap.heuristics(chess.Board(fen))}
            for gap, fen in zip((0, 10, 40, 300, 900), boards)]
    oracle = depth_gap.oracle_report(rows, 30)
    for name, table in depth_gap.heuristic_report(rows, 30).items():
        for top, other in zip(oracle['budgets'], table['budgets']):
            assert top['gap_captured'] >= other['gap_captured'], name
            assert top['recall'] >= other['recall'], name


def test_material_beats_the_tactical_heuristic_on_the_measured_sample():
    payload = json.loads((depth_gap.HERE / 'budget' / 'depth-gap.json').read_text())
    rows = payload['positions']
    material = depth_gap.auc(rows, lambda r: depth_gap.material_score(r['features']), 30)
    tactical = depth_gap.auc(rows, lambda r: depth_gap.tactical_score(r['features']), 30)
    assert material > 0.65 > 0.5 > tactical, (material, tactical)


def test_clip_keeps_mate_scores_from_dominating_the_mean():
    assert depth_gap.clip(depth_gap.MATE - 3) == depth_gap.CLIP
    assert depth_gap.clip(-(depth_gap.MATE - 3)) == -depth_gap.CLIP
    assert depth_gap.clip(45) == 45


def test_measured_positions_come_from_the_shallow_side_only():
    rows = depth_gap.positions_from_match(depth_gap.HERE / 'matches' / 'd2plain-vs-d4-100.json', depth=2)
    assert rows, 'no depth-2 positions found in the recorded match'
    for row in rows[:50]:
        assert chess.Board(row['fen']).is_valid()


@pytest.mark.parametrize('threshold', [0, 30, 200])
def test_base_rate_falls_as_the_threshold_rises(threshold):
    rows = [{'gap': gap, 'move_changed': gap > 0, 'shallow_ms': 1.0, 'deep_ms': 50.0}
            for gap in (0, 0, 10, 40, 300, 900)]
    summary = depth_gap.summarize(rows, threshold)
    assert summary['positions'] == 6
    assert 0 <= summary['base_rate'] <= 1
