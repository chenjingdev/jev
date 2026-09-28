import copy
import json

from understanding_probe import all_cases, build_jobs, purpose, state_for, summarize


def position():
    return {'id': 'fixture', 'winning_move': 'A1', 'engine_move': 'A1', 'features': {
        'state': {'side_to_move': 'black', 'stones': {'B2': 'black', 'C3': 'white', 'D4': 'black'}},
        'group_status': {'B2': 'critical', 'C3': 'critical', 'D4': 'dead'}, 'reading': {},
        'candidate_notes': {'A1': ['owl-defends B2', 'connects B2 and D4'],
                            'E5': ['threatens to defend B2', 'strategically attacks C3', 'expands moyo']}}}


def test_threats_and_connections_are_not_direct_defense():
    assert not purpose(['threatens to defend B2', 'connects B2 and D4'], 'defense')
    assert purpose(['owl-defends B2'], 'defense')
    assert purpose(['strategically attacks C3'], 'attack')
    assert not purpose(['threatens to attack C3'], 'attack')
    assert purpose(['expands moyo'], 'territory')


def test_friendly_critical_requires_both_colour_and_status():
    answers = {c['target']: c['expected'] for c in all_cases([position()]) if c['task'] == 'friendly_critical'}
    assert answers == {'B2': 'yes', 'C3': 'no', 'D4': 'no'}


def test_gold_mutation_does_not_change_requests_and_order_is_paired():
    p = position()
    cases = all_cases([p])
    first = build_jobs([p], cases, ['full', 'focused'], 7)
    p['winning_move'] = p['engine_move'] = 'E5'
    changed = copy.deepcopy(cases)
    for c in changed:
        c['expected'] = 'deliberately_wrong'
    second = build_jobs([p], changed, ['full', 'focused'], 7)
    assert first == second
    for fwd, rev in zip(first[::2], first[1::2]):
        assert fwd['request']['state'] == rev['request']['state']
        for qid, q in fwd['request']['questions'].items():
            other = rev['request']['questions'][qid]
            assert q['instructions'] == other['instructions']
            assert list(q['criteria']) == list(reversed(other['criteria']))
    assert 'expected' not in json.dumps([j['request'] for j in first])


def test_summary_counts_cases_not_repeats_and_exposes_minority_failure():
    cases = [{'id': str(i), 'task': 'friendly_critical', 'expected': label} for i, label in enumerate(['yes', 'no', 'no'])]
    jobs = [{'mode': 'full', 'order': order, 'case_ids': {str(i): str(i) for i in range(3)},
             'response': {'answers': {str(i): {'choice': 'no'} for i in range(3)}}}
            for order in ['forward', 'reverse']]
    s = summarize({'modes': ['full'], 'cases': cases, 'jobs': jobs})['full']['tasks']['friendly_critical']
    assert s['cases'] == 3
    assert s['balanced_accuracy'] == .5
    assert s['label_recall_order_averaged']['yes'] == 0
    assert not s['passes_gate']


def test_focused_colours_are_projection_of_supplied_stones():
    p = position()
    f = state_for(p, 'focused')
    assert f['groups']['B2'] == {'colour': 'black', 'status': 'critical'}
    assert f['candidate_notes'] == p['features']['candidate_notes']
