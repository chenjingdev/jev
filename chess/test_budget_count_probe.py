"""Checks for the board-fullness probe. No API calls."""
import chess

import budget_count_probe as probe
import depth_gap


def test_every_question_claims_something_code_can_count():
    assert set(probe.TRUTHS) == set(probe.QUESTIONS)
    full = depth_gap.heuristics(chess.Board())
    empty = depth_gap.heuristics(chess.Board('8/8/4k3/8/8/4K3/8/8 w - - 0 1'))
    for key, truth in probe.TRUTHS.items():
        assert truth(full) is True, key
        assert truth(empty) is False, key


def test_the_state_is_length_constant_so_an_empty_board_is_not_a_short_prompt():
    from budget_judge import state_for
    full = state_for(chess.Board().fen(), every_square=True)
    empty = state_for('8/8/4k3/8/8/4K3/8/8 w - - 0 1', every_square=True)
    assert len(full['pieces']) == len(empty['pieces']) == 64


def test_questions_ask_for_a_count_and_never_mention_the_label():
    for key, question in probe.QUESTIONS.items():
        criteria = getattr(question, 'criteria', None) or []
        text = (question.instructions + ' ' + ' '.join(criteria if isinstance(criteria, list)
                                                       else list(criteria.values()))).lower()
        for leak in ('gap', 'depth', 'search', 'engine', 'evaluation'):
            assert leak not in text, f'{key} leaks {leak}'
        assert 'piece' in text, key


def test_report_scores_each_answer_against_the_piece_count():
    rows = []
    for fen, value in (('8/8/4k3/8/8/4K3/8/8 w - - 0 1', 0.1), (chess.Board().fen(), 0.9)):
        rows.append({'features': depth_gap.heuristics(chess.Board(fen)),
                     'jev': {'answers': {k: {'value': value} for k in probe.QUESTIONS}}})
    out = probe.report(rows)
    for key in probe.QUESTIONS:
        assert out[key]['auc_vs_piece_count'] == 1.0, key
        assert out[key]['rho_vs_piece_count'] == 1.0, key
