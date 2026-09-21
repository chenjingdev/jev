"""Checks for the Jev side of the budget experiment. No API calls."""
import re

import chess

import budget_judge
import depth_gap


def test_state_carries_only_placement_and_never_an_answer():
    fen = 'r1bqkb1r/1ppppppp/p1n2n2/8/P7/2N2N2/1PPPPPPP/R1BQKB1R w KQkq - 0 5'
    state = budget_judge.state_for(fen)
    assert set(state) == {'side_to_move', 'pieces', 'castling_rights', 'en_passant'}
    assert len(state['pieces']) == len(chess.Board(fen).piece_map())
    blob = repr(state).lower()
    for leak in ('gap', 'depth', 'score', 'cp', 'best', 'legal', 'attack', 'check'):
        assert leak not in blob, f'state leaks {leak}'


def test_state_gives_both_algebraic_and_numeric_coordinates():
    state = budget_judge.state_for(chess.Board().fen())
    assert state['pieces']['White king e1'] == 'column 5, rank 1'
    assert state['pieces']['Black knight g8'] == 'column 7, rank 8'


def test_questions_never_mention_the_engine_or_the_label():
    for key, question in budget_judge.QUESTIONS.items():
        text = (question.instructions + ' ' + ' '.join(getattr(question, 'criteria', None) or [])).lower()
        for leak in ('depth', 'engine', 'search', 'ply', 'plies', 'centipawn', 'evaluation'):
            # Whole words only: "rules apply" is not the search term "ply".
            assert not re.search(rf'\b{leak}\b', text), f'{key} phrases the question in engine terms: {leak}'


def test_rankings_include_chance_heuristic_and_oracle_for_each_question():
    rows = []
    for index, gap in enumerate((0, 0, 20, 60, 400, 900, 5, 120)):
        rows.append({
            'gap': gap,
            'features': depth_gap.heuristics(chess.Board()),
            'jev': {'answers': {key: {'value': index / 10} for key in budget_judge.QUESTIONS}},
        })
    report = budget_judge.report(rows, 30)
    assert set(report) >= {'heuristic.material', 'heuristic.tactical', 'oracle'} | {
        f'jev.{k}' for k in budget_judge.QUESTIONS}
    for name, table in report.items():
        assert table['auc'] is not None
        for entry, ceiling in zip(table['budgets'], report['oracle']['budgets']):
            assert entry['gap_captured'] <= ceiling['gap_captured'] + 1e-9, f'{name} beats the oracle'


def test_a_missing_answer_ranks_last_instead_of_crashing():
    row = {'jev': {'answers': {'trap': {'value': None}}}}
    assert budget_judge.answer_value(row, 'trap') == -1.0
