import copy

from priority_probe import fixed_rule, jobs_for, route, life_status


def test_critical_gtp_reply_does_not_leak_recommended_moves():
    assert life_status('critical F8 F8') == 'critical'
    assert life_status('alive') == 'alive'


def position():
    return {'id': 'fixture', 'engine_move': 'A1', 'ranked_options': ['A1', 'B2', 'C3'],
            'priority_state': {'side_to_move': 'black', 'groups': {
                'D4': {'colour': 'black', 'status': 'critical'},
                'E5': {'colour': 'white', 'status': 'critical'}},
                'candidate_reports': {
                    'A1': {'purposes': ['territory'], 'targets': {'defense': [], 'attack': []}},
                    'B2': {'purposes': ['defense', 'connection'], 'targets': {'defense': ['D4'], 'attack': []}},
                    'C3': {'purposes': ['attack'], 'targets': {'defense': [], 'attack': ['E5']}}}}}


def test_rule_uses_same_objective_execution_and_falls_back():
    p = position()
    assert fixed_rule(p) == 'defense'
    assert route(p, fixed_rule(p)) == 'B2'
    assert route(p, 'undecided') == 'A1'
    p['priority_state']['groups']['D4']['status'] = 'alive'
    assert fixed_rule(p) == 'attack'


def test_outcomes_and_engine_rank_never_enter_model_request():
    p = position()
    jobs = jobs_for([p], 11)
    changed = copy.deepcopy(p)
    changed['rollouts'] = {'A1': 0, 'B2': 1, 'C3': 1}
    changed['engine_move'] = 'C3'
    changed['ranked_options'] = list(reversed(p['ranked_options']))
    assert [j['request'] for j in jobs] == [j['request'] for j in jobs_for([changed], 11)]
    assert list(jobs[0]['request']['questions']['priority']['criteria']) == list(reversed(jobs[1]['request']['questions']['priority']['criteria']))


def test_no_call_when_all_objectives_execute_same_move():
    p = position()
    for r in p['priority_state']['candidate_reports'].values():
        r['purposes'] = ['territory']
    assert jobs_for([p], 11) == []
