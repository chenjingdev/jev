"""Validate and compare the preregistered, exploratory sparse-random control.

Run after the batch: .venv/bin/python chess/reports/analyze_sparse_random.py
No engine or model calls. Existing match files remain unchanged.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

import chess
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROTOCOL = HERE / 'sparse-random-audit01-protocol.json'


def main():
    protocol = json.loads(PROTOCOL.read_text())
    sparse_name = protocol['match']
    names = [sparse_name, 'd2jevc04-vs-d2-100-noise10',
             'd2plain-vs-d2-100-noise10', 'd2rand-vs-d2-100-noise10']
    datasets, points, arms, hashes = {}, {}, {}, {}
    for name in names:
        raw = (ROOT / 'matches' / f'{name}.json').read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        d = datasets[name] = json.loads(raw)
        assert d['status'] == 'complete' and not d.get('failures') and len(d['games']) == 100
        hy = d['engine_a']['name']
        groups = defaultdict(list)
        for g in d['games']:
            assert g['result'] != '*'
            score = .5 if g['result'] == '1/2-1/2' else float((g['result'] == '1-0') == (g['white'] == hy))
            groups[g['pair']].append(score)
        assert len(groups) == 50 and all(len(v) == 2 for v in groups.values())
        points[name] = np.array([np.mean(groups[k]) for k in sorted(groups)])
        s = d['summary']
        opportunities = s['calls'] or s['random_picks']
        changes = s['interventions'] or s['random_interventions']
        arms[name] = {'wdl': [d['analysis'][k] for k in ('wins', 'draws', 'losses')],
                      'score_percent': round(float(points[name].mean() * 100), 3),
                      'eligible_decisions': opportunities, 'changes': changes,
                      'change_rate': changes / opportunities if opportunities else None,
                      'new_api_calls': s['calls'] if name == sparse_name else 0}
    q = protocol['intervention_probability']
    d = datasets[sparse_name]
    assert d['random_intervention_probability'] == q
    assert d['summary']['calls'] == d['summary']['tokens'] == 0
    checked = Counter()
    for g in d['games']:
        b = chess.Board()
        for move in g['opening_uci']:
            b.push_uci(move)
        assert b.fen() == g['initial_fen']
        for m in g['moves']:
            assert b.fen() == m['fen_before']
            move = chess.Move.from_uci(m['uci'])
            assert move in b.legal_moves and m['uci'] in m['shortlist'] and m['jev'] is None
            if c := m.get('random_control'):
                assert c['intervention_probability'] == q
                draw = random.Random(f"intervene-{g['seed']}-{g['pair_game']}-{m['ply']}").random()
                options = sorted(set(m['shortlist']) - {m['base_move']})
                expected = random.Random(f"pick-{g['seed']}-{g['pair_game']}-{m['ply']}").choice(options) if draw < q else m['base_move']
                assert c['gate_draw'] == draw and c['intervention'] == (draw < q)
                assert m['uci'] == c['selected_move'] == expected
                checked['random_decisions'] += 1
            b.push(move)
            checked['plies'] += 1
        outcome = b.outcome(claim_draw=True)
        assert b.fen() == g['final_fen'] and outcome and outcome.result() == g['result']
        assert outcome.termination.name.lower() == g['termination']
        checked[g['termination']] += 1
    contrasts = []
    signature = lambda data: [(g['opening_uci'], g['pair_game'], g['seed']) for g in data['games']]
    for a, b in [(names[1], names[0]), (names[0], names[2]), (names[0], names[3])]:
        assert signature(datasets[a]) == signature(datasets[b])
        delta = points[a] - points[b]
        rng = np.random.default_rng(20260922)
        samples = delta[rng.integers(0, len(delta), (100000, len(delta)))].mean(axis=1)
        contrasts.append({'a': a, 'b': b, 'difference_pp': round(float(delta.mean() * 100), 3),
                          'ci95_pp': np.round(np.quantile(samples, [.025, .975]) * 100, 3).tolist()})
    out = {'protocol': PROTOCOL.name, 'source_sha256': hashes, 'arms': arms, 'validation': dict(checked),
           'contrasts': contrasts, 'analysis': 'Paired opening bootstrap, 100000 samples, seed 20260922.',
           'limitations': protocol['limitations']}
    (HERE / 'sparse-random-audit01-analysis.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
