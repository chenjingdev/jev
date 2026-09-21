from ladder_batch import analyze


def test_analyze_counts_from_hybrid_perspective_and_pairs():
    payload = {'games': [
        {'pair': 1, 'opening_name': 'op01', 'result': '1-0', 'white': 'Weak2 + Jev', 'black': 'Weak4'},
        {'pair': 1, 'opening_name': 'op01', 'result': '1-0', 'white': 'Weak4', 'black': 'Weak2 + Jev'},
        {'pair': 2, 'opening_name': 'op02', 'result': '1/2-1/2', 'white': 'Weak2 + Jev', 'black': 'Weak4'},
        {'pair': 2, 'opening_name': 'op02', 'result': '0-1', 'white': 'Weak4', 'black': 'Weak2 + Jev'},
        {'pair': 3, 'opening_name': 'op03', 'result': '*', 'white': 'Weak2 + Jev', 'black': 'Weak4'}]}
    a = analyze(payload, 'Weak2 + Jev')
    assert (a['wins'], a['draws'], a['losses'], a['unfinished']) == (2, 1, 1, 1)
    assert a['games'] == 4 and a['score_fraction'] == 0.625
    assert a['pair_wins'] == 1 and a['pair_losses'] == 0
    assert a['pairs'][0]['hybrid_points'] == 1 and a['pairs'][1]['hybrid_points'] == 1.5
    assert a['elo_diff_estimate'] > 0
