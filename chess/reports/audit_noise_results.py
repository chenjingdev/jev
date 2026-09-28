"""Recount recorded noise experiments without engine/model calls or match-file changes.

From repo root: .venv/bin/python chess/reports/audit_noise_results.py
Writes noise-audit-20260922.json beside this script.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import chess
import numpy as np

HERE = Path(__file__).resolve().parent
MATCHES = HERE.parent / 'matches'
NAMES = [
    'd2plain-vs-d2-100',
    'd2plain-vs-d2-100-noise10',
    'd2plain-vs-d2-100-noise30',
    'd2plain-noise10-vs-d2plain-100',
    'd2plain-noise30-vs-d2plain-100',
    'd2rand-vs-d2-100-noise10',
    'd2jev-vs-d2-100-noise10',
    'd2jevc04-vs-d2-100-noise10',
]
MATERIAL = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
            chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
SEED, BOOTSTRAPS = 20260922, 100000


def interval(values):
    values = np.array(values, dtype=float)
    rng = np.random.default_rng(SEED)
    samples = values[rng.integers(0, len(values), (BOOTSTRAPS, len(values)))].mean(axis=1)
    return np.round(np.quantile(samples, [.025, .975]) * 100, 3).tolist()


def main():
    output = {'created_at': datetime.now(timezone.utc).isoformat(),
              'definitions': {'early': 'threefold repetition at <=30 post-opening plies',
                              'material_gap': 'absolute White-minus-Black material >=300; P100 N300 B300 R500 Q900',
                              'bootstrap': f'opening cluster, both colors kept together; {BOOTSTRAPS} samples, seed {SEED}',
                              'scope': 'descriptive/exploratory; one opening set and seed schedule'},
              'matches': {}, 'contrasts': []}
    datasets, pair_scores = {}, {}
    for name in NAMES:
        path = MATCHES / f'{name}.json'
        raw = path.read_bytes()
        d = datasets[name] = json.loads(raw)
        assert d['status'] == 'complete' and not d.get('failures') and len(d['games']) == 100
        hybrid = d['engine_a']['name']
        scores = defaultdict(list)
        counts = Counter()
        material_gaps = []
        noise = d.get('noise', 0)
        opponent_noise = d.get('opponent_noise')
        if opponent_noise is None:
            opponent_noise = noise
        for g in d['games']:
            b = chess.Board()
            for u in g['opening_uci']:
                b.push_uci(u)
            assert b.fen() == g['initial_fen']
            initial_pieces = len(b.piece_map())
            for m in g['moves']:
                assert b.fen() == m['fen_before']
                move = chess.Move.from_uci(m['uci'])
                assert move in b.legal_moves
                expected_noise = noise if m['engine'] == hybrid else opponent_noise
                for r in m['engine_candidates']:
                    assert -expected_noise <= r.get('noise', 0) <= expected_noise
                    assert ('noise' in r) == bool(expected_noise)
                if j := m.get('jev'):
                    req = j['request']
                    assert set(req['state']) == {'pieces', 'side_to_move', 'castling_rights', 'en_passant'}
                    assert req['state']['pieces'] == {
                        chess.square_name(s): ('white ' if pc.color else 'black ') + chess.piece_name(pc.piece_type)
                        for s, pc in b.piece_map().items()}
                    criteria = req['questions']['move']['criteria']
                    assert set(criteria) == set(m['shortlist']) and all(v is None for v in criteria.values())
                    assert j['selected_move'] == m['uci']
                    counts['validated_jev_requests'] += 1
                b.push(move)
                counts['replayed_plies'] += 1
            assert b.fen() == g['final_fen'] and g['plies'] == len(g['moves'])
            outcome = b.outcome(claim_draw=True)
            assert outcome and outcome.result() == g['result'] and outcome.termination.name.lower() == g['termination']
            points = .5 if g['result'] == '1/2-1/2' else float((g['result'] == '1-0') == (g['white'] == hybrid))
            scores[g['pair']].append(points)
            counts[g['termination']] += 1
            if g['termination'] == 'threefold_repetition':
                early = g['plies'] <= 30
                counts['early_repetition_postopening_30ply'] += early
                counts['early_repetition_no_captures'] += early and len(b.piece_map()) == initial_pieces
                counts['repetition_total_60ply'] += g['plies'] + len(g['opening_uci']) <= 60
                material = abs(sum((1 if pc.color else -1) * MATERIAL[pc.piece_type] for pc in b.piece_map().values()))
                material_gaps.append(material)
                counts['repetition_material_gap_ge300'] += material >= 300
        assert len(scores) == 50 and all(len(v) == 2 for v in scores.values())
        pair_scores[name] = np.array([np.mean(scores[k]) for k in sorted(scores)])
        output['matches'][name] = {
            'source': str(path.relative_to(HERE.parent)), 'sha256': hashlib.sha256(raw).hexdigest(),
            'noise': noise, 'opponent_noise': opponent_noise,
            'wdl': [d['analysis'][k] for k in ('wins', 'draws', 'losses')],
            'score_percent': round(float(pair_scores[name].mean() * 100), 3),
            'score_ci95_percent': interval(pair_scores[name]),
            **counts, 'repetition_material_gaps': material_gaps}
    for i, j in [(6, 5), (7, 5), (6, 1), (7, 1)]:
        a, b = NAMES[i], NAMES[j]
        signature = lambda d: [(g['opening_uci'], g['pair_game'], g['seed']) for g in d['games']]
        assert signature(datasets[a]) == signature(datasets[b])
        delta = pair_scores[a] - pair_scores[b]
        output['contrasts'].append({'a': a, 'b': b, 'difference_pp': round(float(delta.mean() * 100), 3),
                                    'ci95_pp': interval(delta)})
    transitions, early_transitions = Counter(), Counter()
    for a, b in zip(datasets[NAMES[0]]['games'], datasets[NAMES[1]]['games']):
        assert (a['game'], a['opening_uci']) == (b['game'], b['opening_uci'])
        transitions[f"{a['termination']} -> {b['termination']}"] += 1
        if a['termination'] == 'threefold_repetition' and a['plies'] <= 30:
            kind = 'checkmate' if b['termination'] == 'checkmate' else 'early_repetition' if b['plies'] <= 30 else 'later_repetition'
            early_transitions[kind] += 1
    output['no_noise_to_both_noise10_transitions'] = dict(transitions)
    output['baseline_52_early_repetition_transitions'] = dict(early_transitions)
    (HERE / 'noise-audit-20260922.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({n: {k: v for k, v in a.items() if k not in ('sha256', 'repetition_material_gaps')}
                      for n, a in output['matches'].items()}, indent=2))
    print(json.dumps({'transitions': transitions, 'early_transitions': early_transitions, 'contrasts': output['contrasts']}, indent=2))


if __name__ == '__main__':
    main()
