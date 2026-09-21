"""Paired-input experiment for five completion, matched against compact records.

Same 20 paired 9/29-stone puzzles, same 5 coordinate-only options, 6 conditions.
No winning line, colour lists, scores or target are supplied to the model.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import copy
from functools import lru_cache
import json
import random
import basics as B

COMMON=('White to move on a 15x15 gomoku board. Which candidate empty coordinate completes '
        'five white stones in a consecutive horizontal, vertical or diagonal line and wins immediately? '
        'Choose that coordinate. Coordinates use columns a-o from left to right and rows 1-15 from bottom to top. ')
NOTES={
 'compact':B.sight.BOARD_COMPACT,
 'spaced':'`moves` is an ordered space-separated sequence of coordinates. Black plays first and the colours alternate.',
 'array':'`moves` is an ordered array of coordinates. Black plays first and the colours alternate.',
 'paired':'`moves` is an ordered array of consecutive move pairs. Within each pair, the first coordinate is black and the second is white. An unpaired final coordinate is black.',
}


def distance(at):
    return max(abs(ord(at[0])-ord('h')),abs(int(at[1:])-8))


@lru_cache(maxsize=64)
def cases_for_seed(seed):
    cases=copy.deepcopy([c for c in B.cases_for_seed(seed) if c.stage=='complete'])
    boards=[B.replay(c.moves) for c in cases];target=cases[0].target
    pool=[B.E.coord(r,c) for r in range(15) for c in range(15)
          if B.E.coord(r,c)!=target and all(not board[r][c] for board in boards)
          and B.E.neighbours(boards[0],r,c,2)]
    rng=random.Random(611900+seed)
    same=[at for at in pool if distance(at)==distance(target)]
    farther=[at for at in pool if distance(at)>distance(target)]
    closer=[at for at in pool if distance(at)<distance(target)]
    if not same or not farther or len(closer)<2:raise ValueError('Cannot balance distance distractors')
    options=[target,rng.choice(same),rng.choice(farther),*rng.sample(closer,2)]
    rng.shuffle(options)
    for case in cases:
        case.options=options[:];B.validate(case)
    return cases


def ask(case,condition='base',encoding='paired'):
    if encoding not in NOTES:raise ValueError('Unknown completion encoding')
    if case.stage!='complete':raise ValueError('Expected a completion case')
    transformed,_=B.transform(case,condition)
    moves=transformed.moves
    if encoding=='paired':value=[moves[i:i+2] for i in range(0,len(moves),2)]
    elif encoding=='array':value=moves
    else:value=('' if encoding=='compact' else ' ').join(moves)
    result=B.ask(case,condition,instructions_override=COMMON+NOTES[encoding],state_override={'moves':value})
    return {**result,'encoding':encoding}


def main():
    cases=[c for seed in range(1,21) for c in cases_for_seed(seed)]
    jobs=[(case,condition,encoding) for case in cases for condition in B.CONDITIONS for encoding in ('compact','paired')]
    random.Random(32200).shuffle(jobs)
    trials=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(ask,*job) for job in jobs]):
            trials.append(future.result())
            if len(trials)%80==0:print(f'{len(trials)}/{len(jobs)} complete',flush=True)
    summary={}
    for encoding in ('compact','paired'):
        lookup={(t['seed'],t['density']):t for t in trials if t['encoding']==encoding and t['condition']=='base'}
        for density in ('sparse','dense'):
            for direction in ('all','axis','diagonal'):
                for condition in B.CONDITIONS:
                    rows=[t for t in trials if t['encoding']==encoding and t['density']==density and t['condition']==condition and (direction=='all' or t['direction']==direction)]
                    summary[f'{encoding}/{density}/{direction}/{condition}']={
                        'hit':sum(t['hit'] for t in rows),'n':len(rows),
                        'same_as_base':sum(t['unrotated_pick']==lookup[t['seed'],density]['pick'] for t in rows)}
    out={'created_at':datetime.now(timezone.utc).isoformat(),'model':B.brain.MODEL,
         'design':'existing 20 paired 9/29-stone puzzles; distance-balanced choices (target + equal-distance + farther + 2 nearer); same choices; compact vs code-prepaired moves; common task and coordinate rules; exploratory comparison, no fresh heldout claim',
         'version':'distance-balanced-v2','summary':summary,'trials':trials,
         'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*B.brain.USD_PER_TOKEN,4)}
    (B.HERE/'results_completion_encoding.json').write_text(json.dumps(out,ensure_ascii=False,indent=1))
    print(json.dumps({'summary':{k:v for k,v in summary.items() if '/all/' in k},'cost_usd':out['cost_usd']}))

if __name__=='__main__':main()
