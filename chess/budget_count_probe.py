"""Can Jev tell a full board from an emptying one at all?

The budget run found Jev at chance on which positions deserve a deeper search,
and the signal that does predict it is how much material is left. The four
tactical questions in `budget_judge.py` are defensible - scored against the
ground truth each one literally asks for, they land at AUC 0.58 to 0.82. The
`complexity` question is not: its top level says "many pieces interact at once"
and its answers correlate -0.013 with the piece count, so there is no evidence
it landed at all, and the wording is as likely a culprit as the model.

This asks board fullness directly, in three shapes, against a ground truth that
is a `len()` call. If Jev counts, the earlier `complexity` wording was the
problem and that question deserves a rerun. If it does not, the budget result
stands as a perception limit and the wording is off the hook.

State is the constant-length one (all 64 squares), so a shorter prompt cannot
stand in for an emptier board.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from typesafe_sdk import Choice, Noul, Score

from budget_judge import MODEL, RULES, client, state_for
from depth_gap import auc

HERE = Path(__file__).resolve().parent

QUESTIONS = {
    'mostly_full': Noul(instructions=(
        RULES + ' A chess game starts with 32 pieces on the board and they come off as it goes on. '
        'More than 24 pieces are still on this board.')),
    'how_many': Score(criteria=[
        'Almost empty: about 8 pieces or fewer are left, the bare kings and a handful of others.',
        'Half gone: somewhere around 16 pieces are left.',
        'Almost untouched: nearly all 32 pieces are still there, very little has been captured.',
    ], instructions=RULES + ' How many pieces are still on this board?'),
    'stage': Choice(criteria={
        'opening': 'Barely anything has been captured yet and most pieces are still on their own side.',
        'middlegame': 'Some pieces have been traded off and the rest are spread across the board.',
        'endgame': 'Most pieces are gone and only a few, with the kings, are left.',
    }, instructions=RULES + ' Which stage of the game is this position in?'),
}

# What each question claims, as something code can count from the same position.
TRUTHS = {
    'mostly_full': lambda features: features['piece_count'] > 24,
    'how_many': lambda features: features['piece_count'] > 24,
    'stage': lambda features: features['piece_count'] > 24,
}


def ask(row):
    started = time.perf_counter()
    result = client().system_one(model=MODEL, state=state_for(row['fen'], every_square=True),
                                 questions=QUESTIONS)
    answers = {}
    for key, answer in result.answers.items():
        value = getattr(answer, 'noul', None)
        if value is None:
            value = getattr(answer, 'score', None)
        if value is None and getattr(answer, 'choice', None) is not None:
            # Rank the three stages the way the board empties, so one number is comparable.
            value = {'endgame': 0.0, 'middlegame': 1.0, 'opening': 2.0}[answer.choice]
        answers[key] = {'value': value, 'confidence': getattr(answer, 'confidence', None),
                        'choice': getattr(answer, 'choice', None),
                        'probabilities': dict(getattr(answer, 'probabilities', {}) or {})}
    return {**row, 'jev': {'answers': answers,
                           'latency_ms': round((time.perf_counter() - started) * 1000, 2),
                           'usage': {'input_tokens': result.usage.input_tokens,
                                     'output_tokens': result.usage.output_tokens},
                           'model': result.model}}


def report(rows):
    """AUC of each answer against the piece count it claims to describe."""
    out = {}
    for key, truth in TRUTHS.items():
        tagged = [{'gap': 100 if truth(r['features']) else 0,
                   'value': r['jev']['answers'][key]['value']} for r in rows]
        positives = sum(1 for t in tagged if t['gap'])
        out[key] = {'true_positions': positives, 'positions': len(rows),
                    'auc_vs_piece_count': auc(tagged, lambda r: r['value'], 30)}
    counts = [r['features']['piece_count'] for r in rows]
    for key in QUESTIONS:
        values = [r['jev']['answers'][key]['value'] for r in rows]
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0] * len(values)
        for place, index in enumerate(order):
            ranks[index] = place
        order2 = sorted(range(len(counts)), key=lambda i: counts[i])
        ranks2 = [0] * len(counts)
        for place, index in enumerate(order2):
            ranks2[index] = place
        n = len(values)
        ma, mb = sum(ranks) / n, sum(ranks2) / n
        num = sum((a - ma) * (b - mb) for a, b in zip(ranks, ranks2))
        den = (sum((a - ma) ** 2 for a in ranks) * sum((b - mb) ** 2 for b in ranks2)) ** 0.5
        out[key]['rho_vs_piece_count'] = round(num / den, 4) if den else None
    return out


def run(gap_file: Path, output: Path, limit: int, workers: int):
    if output.exists():
        raise FileExistsError('Use a new output name to preserve previous evidence')
    source = json.loads(gap_file.read_text())
    rows = source['positions'][:limit] if limit else source['positions']
    done = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(ask, row) for row in rows]
        for index, future in enumerate(as_completed(futures), 1):
            done.append(future.result())
            if index % 100 == 0:
                print(f'{index}/{len(rows)} {round(time.perf_counter() - started, 1)}s', flush=True)
    done.sort(key=lambda r: (r['match'], r['game'], r['ply']))
    usage = [r['jev']['usage'] for r in done]
    payload = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'design': ('Board fullness asked directly in three shapes over the constant-length state, '
                   'scored against the piece count. Separates "the complexity question was worded '
                   'badly" from "Jev does not read how full the board is".'),
        'model': MODEL,
        'questions': {key: {'type': type(q).__name__, 'instructions': q.instructions,
                            **({'criteria': list(q.criteria)} if getattr(q, 'criteria', None) else {})}
                      for key, q in QUESTIONS.items()},
        'report': report(done),
        'usage': {'requests': len(done),
                  'input_tokens': sum(u['input_tokens'] for u in usage),
                  'output_tokens': sum(u['output_tokens'] for u in usage)},
        'elapsed_seconds': round(time.perf_counter() - started, 2),
        'positions': done,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({'report': payload['report'], 'usage': payload['usage']}, ensure_ascii=False, indent=2), flush=True)
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--gap-file', type=Path, default=HERE / 'budget' / 'depth-gap.json')
    p.add_argument('--output', type=Path, default=HERE / 'budget' / 'count-probe-01.json')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--workers', type=int, default=4)
    args = p.parse_args()
    run(args.gap_file, args.output, args.limit, args.workers)
