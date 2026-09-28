"""Counterfactual replay: score a selector decision by the game result it leads to against the actual opponent.

For every decision where the selector (Jev or the random control) disagreed with the engine #1, the game is
replayed from that point twice, once after the selector's move and once after the engine's move, with the
plain weak engine on both sides at the match's depths. Engines are deterministic, so no API is needed.
This is the yardstick that matches the opponent; the Stockfish referee (referee.py) measures against best
play instead, which a depth-2 opponent cannot enforce. Writes matches/<name>.counterfactual.json."""
import json, sys, statistics, collections
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import chess
from weak_engine import candidates

HERE = Path(__file__).resolve().parent

def finish(board, ply, hybrid_white, depth_hybrid, depth_opponent, max_plies=400):
    """Play out with the plain weak engine on both sides; returns (hybrid points, termination)."""
    while ply < max_plies:
        oc = board.outcome(claim_draw=True)
        if oc: break
        rows, _ = candidates(board, depth=depth_hybrid if board.turn == hybrid_white else depth_opponent)
        board.push_uci(rows[0]['move']); ply += 1
    oc = board.outcome(claim_draw=True)
    if not oc: return 0.5, 'unfinished'
    r = oc.result()
    if r == '1/2-1/2': return 0.5, oc.termination.name.lower()
    return (1.0 if (r == '1-0') == hybrid_white else 0.0), oc.termination.name.lower()

def job(args):
    opening, prior, ply, sel, base, hybrid_white, depths, meta = args
    board = chess.Board()
    for u in opening: board.push_uci(u)
    for u in prior: board.push_uci(u)
    bj = board.copy(); bj.push_uci(sel); sj, tj = finish(bj, ply, hybrid_white, *depths)
    bb = board.copy(); bb.push_uci(base); sb, tb = finish(bb, ply, hybrid_white, *depths)
    return {**meta, 'sel_result': sj, 'base_result': sb, 'sel_term': tj, 'base_term': tb}

def collect_jobs(d):
    hy = d['engine_a']['name']
    depths = (d.get('depth', 2), d.get('opponent_depth', d.get('depth', 2)))
    jobs = []
    for g in d['games']:
        hybrid_white = g['white'] == hy
        prior = []
        for m in g['moves']:
            dec = m.get('jev') or m.get('random_control')
            if dec:
                sel = dec.get('jev_move', dec['selected_move'])
                if sel != dec['base_move']:
                    jobs.append((g['opening_uci'], list(prior), m['ply'], sel, dec['base_move'], hybrid_white, depths,
                                 {'game': g['game'], 'ply': m['ply'], 'confidence': dec.get('confidence'),
                                  'gated': bool(dec.get('gated')), 'played': m['uci'] == sel, 'actual': g['result']}))
            prior.append(m['uci'])
    return jobs


def summarize(rows):
    out = {}
    def block(rs):
        d = [r['sel_result'] - r['base_result'] for r in rs]
        b = sum(x > 0 for x in d); w = sum(x < 0 for x in d)
        return {'n': len(d), 'selector_move_outcome': round(statistics.mean(r['sel_result'] for r in rs), 4),
                'engine_move_outcome': round(statistics.mean(r['base_result'] for r in rs), 4),
                'better': b, 'same': len(d) - b - w, 'worse': w, 'net_per_decision': round(statistics.mean(d), 4)}
    out['all_disagreements'] = block(rows)
    played = [r for r in rows if r['played']]
    if len(played) != len(rows):
        out['played'] = block(played); out['gated_out'] = block([r for r in rows if not r['played']])
    if rows and rows[0]['confidence'] is not None:
        out['by_confidence'] = {f'{lo:.1f}-{hi:.1f}': block(b) for lo, hi in [(0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,.5),(.5,1.01)] if (b := [r for r in rows if lo <= r['confidence'] < hi])}
    return out


if __name__ == '__main__':
    name = sys.argv[1]
    path = HERE / 'matches' / f'{name}.json'
    out_path = HERE / 'matches' / f'{name}.counterfactual.json'
    if out_path.exists():
        raise FileExistsError(out_path)
    d = json.load(open(path))
    jobs = collect_jobs(d)
    print(name, 'decisions where selector disagreed with engine:', len(jobs), flush=True)
    with ProcessPoolExecutor(10) as pool:
        rows = list(pool.map(job, jobs, chunksize=4))
    summary = summarize(rows)
    json.dump({'match': name, 'method': 'plain weak engine both sides from the decision point, deterministic, claim_draw at threefold/fifty-move, max 400 plies',
               'summary': summary, 'decisions': rows}, open(out_path, 'w'), indent=1)
    print(json.dumps(summary, indent=1))
