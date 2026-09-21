"""Post-hoc referee: rescore every selector decision with a deeper Stockfish.

Applied uniformly to every arm (Jev, random, weak-engine). For each decision the
referee analyses the *parent* position with MultiPV restricted to the shortlist
(root_moves), so all candidates are scored at the same depth from the mover's
point of view. Nothing here is ever sent to Jev; games are already finished.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import chess
import chess.engine

HERE = Path(__file__).resolve().parent
MATE_SCORE = 10000


def decisions(payload):
    for g in payload['games']:
        for m in g['moves']:
            d = m.get('jev') or m.get('random_control')
            if d:
                yield g, m, d


def score_shortlist(engine, board, shortlist, nodes):
    roots = [chess.Move.from_uci(u) for u in shortlist]
    if any(mv not in board.legal_moves for mv in roots):
        raise ValueError('Illegal shortlist move')
    engine.configure({'Clear Hash': None})
    infos = engine.analyse(board, chess.engine.Limit(nodes=nodes), multipv=len(roots), root_moves=roots)
    scored = {}
    for info in infos:
        if 'pv' not in info or 'score' not in info:
            continue
        scored[info['pv'][0].uci()] = info['score'].pov(board.turn).score(mate_score=MATE_SCORE)
    missing = set(shortlist) - set(scored)
    if missing:
        raise RuntimeError(f'Referee did not score {missing}')
    return scored


def grade(scored, base, pick):
    best = max(scored.values())
    return {'referee_scores': scored, 'best_moves': sorted(m for m, s in scored.items() if s == best),
            'loss_pick': best - scored[pick], 'loss_base': best - scored[base],
            'pick_is_best': scored[pick] == best, 'base_is_best': scored[base] == best,
            'pick_minus_base': scored[pick] - scored[base]}


def aggregate(rows):
    n = len(rows)
    if not n:
        return {'decisions': 0}
    k = [len(r['shortlist']) for r in rows]
    changed = [r for r in rows if r['pick'] != r['base']]
    return {
        'decisions': n,
        'chance_pick_is_best': round(statistics.mean(1 / x for x in k), 4),
        'pick_is_best_rate': round(statistics.mean(r['grade']['pick_is_best'] for r in rows), 4),
        'base_is_best_rate': round(statistics.mean(r['grade']['base_is_best'] for r in rows), 4),
        'mean_loss_pick_cp': round(statistics.mean(r['grade']['loss_pick'] for r in rows), 2),
        'mean_loss_base_cp': round(statistics.mean(r['grade']['loss_base'] for r in rows), 2),
        'mean_pick_minus_base_cp': round(statistics.mean(r['grade']['pick_minus_base'] for r in rows), 2),
        'changed': len(changed),
        'changed_improved': sum(r['grade']['pick_minus_base'] > 0 for r in changed),
        'changed_worse': sum(r['grade']['pick_minus_base'] < 0 for r in changed),
        'changed_equal': sum(r['grade']['pick_minus_base'] == 0 for r in changed),
        'median_pick_minus_base_when_changed_cp': statistics.median(r['grade']['pick_minus_base'] for r in changed) if changed else None,
    }


def referee(match_path, engine_path, nodes, out_path):
    payload = json.loads(Path(match_path).read_text())
    rows = []
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        engine.configure({'Threads': 1, 'Hash': 64})
        for g, m, d in decisions(payload):
            board = chess.Board(m['fen_before'])
            shortlist = list(m['shortlist'])
            pick, base = d['selected_move'], d['base_move']
            if pick not in shortlist or base not in shortlist:
                raise ValueError('Decision outside shortlist')
            scored = score_shortlist(engine, board, shortlist, nodes)
            rows.append({'game': g['game'], 'ply': m['ply'], 'fen': m['fen_before'], 'shortlist': shortlist,
                         'base': base, 'pick': pick, 'selector': 'jev' if m.get('jev') else 'random',
                         'shallow_cp': {r['move']: r['cp'] for r in m['engine_candidates']},
                         'grade': grade(scored, base, pick)})
    result = {'match': str(match_path), 'selector': payload.get('selector', 'jev'),
              'referee': {'engine': engine_path, 'nodes': nodes, 'note': 'Same evaluator family as the players; deeper, not independent.'},
              'summary': aggregate(rows), 'decisions': rows}
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('match', type=Path)
    p.add_argument('--engine', default='/opt/homebrew/bin/stockfish')
    p.add_argument('--nodes', type=int, default=200000)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    out = a.output or a.match.with_name(a.match.stem + f'.referee-{a.nodes}.json')
    if out.exists():
        raise FileExistsError(out)
    r = referee(a.match, a.engine, a.nodes, out)
    print(json.dumps(r['summary'], indent=2))
