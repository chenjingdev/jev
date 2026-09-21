"""Paired representation/order/rotation experiment, no option descriptions.

Uses the existing 20 validated self-play positions, not external game content.
Run under op run: python gomoku/sight_diagnostics.py
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

import engine as E
import sight

REPS = ('sequence', 'compact', 'spaced', 'stones', 'sgf', 'sgf_native')
CONDITIONS = ('base', 'repeat', 'shuffle', 'rotate90', 'rotate180', 'rotate270')


def jobs_for(dataset):
    jobs = []
    for i, row in enumerate(dataset):
        original = sight.Position(row['board'], E.parse_coord(row['target']), row['moves'])
        sight.validate(original)
        original_options = list(sight.options_for(original.board, 'all'))
        for rep in REPS:
            for condition in CONDITIONS:
                turns = {'rotate90': 1, 'rotate180': 2, 'rotate270': 3}.get(condition, 0)
                position = sight.rotate_position(original, turns)
                sight.validate(position)
                # Preserve option ordinal under rotation: only coordinates/board change.
                options = [sight.rotate_coord(at, turns) for at in original_options]
                if condition == 'shuffle':
                    random.Random(31000 + i).shuffle(options)
                jobs.append((i, rep, condition, turns, position, options))
    # Interleave conditions to avoid confounding each condition with time/load.
    random.Random(20260920).shuffle(jobs)
    return jobs


def run_job(job):
    i, rep, condition, turns, position, options = job
    result = sight.ask(position, 'all', rep, probabilities=True, option_order=options, audit=True)
    return {'position_id': i, 'condition': condition, 'rotation': turns * 90,
            'unrotated_pick': sight.rotate_coord(result['pick'], -turns), **result}


def summarize(trials):
    lookup = {(t['position_id'], t['rep'], t['condition']): t for t in trials}
    out = {}
    for rep in REPS:
        for condition in CONDITIONS:
            group = [t for t in trials if t['rep'] == rep and t['condition'] == condition]
            same = sum(t['unrotated_pick'] == lookup[t['position_id'],rep,'base']['pick'] for t in group)
            out[f'{rep}/{condition}'] = {'hit': sum(t['hit'] for t in group), 'n': len(group),
                'same_as_base_after_inverse_rotation': same}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default=str(sight.HERE / 'results_sight.json'))
    parser.add_argument('--out', default=str(sight.HERE / 'results_sight_diagnostics.json'))
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    source = Path(args.dataset).read_bytes()
    dataset = json.loads(source)['dataset']
    jobs = jobs_for(dataset)
    trials = []
    checkpoint = Path(args.out).with_suffix('.jsonl')
    with checkpoint.open('w') as log, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_job, j) for j in jobs]
        for future in as_completed(futures):
            result = future.result()
            trials.append(result)
            log.write(json.dumps(result, ensure_ascii=False) + '\n'); log.flush()
            if len(trials) % 60 == 0:
                print(f'{len(trials)}/{len(jobs)} complete', flush=True)
    out = {'model': sight.brain.MODEL, 'created_at': datetime.now(timezone.utc).isoformat(),
           'dataset_sha256': hashlib.sha256(source).hexdigest(), 'dataset': dataset,
           'design': 'all empty points; no descriptions; same option ordinals under rotation; repeat baseline and one deterministic shuffle; randomized job order',
           'summary': summarize(trials), 'trials': sorted(trials, key=lambda t:(t['position_id'],t['rep'],t['condition'])),
           'cost_usd': round(sum(t['input_tokens'] + t['output_tokens'] for t in trials) * sight.brain.USD_PER_TOKEN, 4)}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    checkpoint.unlink()
    print(json.dumps({'summary':out['summary'], 'cost_usd':out['cost_usd']}, indent=1))


if __name__ == '__main__':
    main()
