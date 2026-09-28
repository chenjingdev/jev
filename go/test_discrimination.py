"""Tests for the offline discrimination test (go/discrimination_test.py)."""
import json
from discrimination_test import split_reasons, build_request, label_count_pick, collect_positions


def test_split_reasons_splits_joined_gtp_reply_and_strips_judgement():
    text = ('Move reasons: Move at E5 strategically defends D8 Move at E5 attacks F6 (defenseless) '
            'Move at E5 strategically or tactically unsafe Move at E5 expands territory')
    assert split_reasons(text, 'E5') == ['strategically defends D8', 'attacks F6', 'expands territory']
    assert split_reasons('Move reasons:', 'E5') == []


def test_request_never_contains_values_ranks_or_engine_choice():
    position = {'id': 'x', 'moves': ['C6', 'B7']}
    feats = {'engine_move_now': 'C6',
             'state': {'side_to_move': 'black', 'stones': {'C6': 'white'}},
             'candidate_notes': {'C6': ['expands territory'], 'B7': []},
             'group_status': {'C6': 'alive'}, 'reading': {'C6': {'colour': 'white', 'can_be_captured': False, 'can_be_saved': None}}}
    for cond in ['bare', 'reasons', 'status']:
        req = build_request(position, feats, cond, 1)
        text = json.dumps(req).lower()
        for banned in ['value', 'rank', 'engine_move', 'genmove', 'top_moves', 'winning', 'score']:
            assert banned not in text, (cond, banned)
        assert set(req['questions']['move']['criteria']) == {'C6', 'B7'}
    assert 'candidate_notes' not in build_request(position, feats, 'bare', 1)['state']
    assert build_request(position, feats, 'reasons', 1)['state']['candidate_notes']['B7'] == ['no specific purpose recorded']
    assert 'group_status' in build_request(position, feats, 'status', 1)['state']


def test_label_count_pick_is_none_on_tie():
    position = {'moves': ['A1', 'B2']}
    assert label_count_pick(position, {'candidate_notes': {'A1': ['x'], 'B2': ['y']}}) is None
    assert label_count_pick(position, {'candidate_notes': {'A1': ['x', 'z'], 'B2': ['y']}}) == 'A1'


def test_collect_positions_dedupes_and_marks_winner():
    positions = collect_positions()
    keys = {(tuple(v for _, v, _ in p['prefix']), p['color'], tuple(p['moves'])) for p in positions}
    assert len(keys) == len(positions)
    for p in positions:
        assert p['winning_move'] in p['moves'] and len(p['moves']) == 2
        assert p['engine_move'] in p['moves']
