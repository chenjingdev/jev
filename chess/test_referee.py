from types import SimpleNamespace
import chess
import chess.engine
from referee import grade, aggregate, score_shortlist, decisions


def test_grade_measures_loss_against_best_in_shortlist():
    g = grade({'e2e4': 30, 'd2d4': 30, 'g1f3': 10}, base='e2e4', pick='g1f3')
    assert g['best_moves'] == ['d2d4', 'e2e4'] and g['loss_pick'] == 20 and g['loss_base'] == 0
    assert not g['pick_is_best'] and g['base_is_best'] and g['pick_minus_base'] == -20


def test_aggregate_reports_chance_baseline_and_change_direction():
    rows = [{'shortlist': ['a', 'b'], 'base': 'a', 'pick': 'b', 'grade': grade({'a': 0, 'b': 5}, 'a', 'b')},
            {'shortlist': ['a', 'b', 'c'], 'base': 'a', 'pick': 'a', 'grade': grade({'a': 9, 'b': 0, 'c': 0}, 'a', 'a')},
            {'shortlist': ['a', 'b', 'c'], 'base': 'a', 'pick': 'c', 'grade': grade({'a': 9, 'b': 0, 'c': -1}, 'a', 'c')}]
    s = aggregate(rows)
    assert s['decisions'] == 3 and s["chance_pick_is_best"] == round((0.5 + 1/3 + 1/3) / 3, 4)
    assert s['changed'] == 2 and s['changed_improved'] == 1 and s['changed_worse'] == 1
    assert s['pick_is_best_rate'] == round(2 / 3, 4)


def test_score_shortlist_uses_mover_pov_and_root_moves():
    board = chess.Board()
    seen = {}
    class Engine:
        def configure(self, o): pass
        def analyse(self, b, limit, multipv, root_moves):
            seen.update(multipv=multipv, roots=[m.uci() for m in root_moves], nodes=limit.nodes)
            return [{'pv': [chess.Move.from_uci('e2e4')], 'score': chess.engine.PovScore(chess.engine.Cp(25), chess.WHITE)},
                    {'pv': [chess.Move.from_uci('d2d4')], 'score': chess.engine.PovScore(chess.engine.Mate(-3), chess.WHITE)}]
    scored = score_shortlist(Engine(), board, ['d2d4', 'e2e4'], 777)
    assert seen == {'multipv': 2, 'roots': ['d2d4', 'e2e4'], 'nodes': 777}
    assert scored['e2e4'] == 25 and scored['d2d4'] < -9000


def test_decisions_include_random_control_but_skip_engine_only_moves():
    payload = {'games': [{'game': 1, 'moves': [
        {'jev': {'selected_move': 'a', 'base_move': 'a'}, 'random_control': None},
        {'jev': None, 'random_control': {'selected_move': 'b', 'base_move': 'a'}},
        {'jev': None, 'random_control': None}]}]}
    assert [d['selected_move'] for _, _, d in decisions(payload)] == ['a', 'b']
