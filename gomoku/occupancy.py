"""Tune only occupied-coordinate recognition. Candidate sets and state stay fixed.

Seeds 1..10 tune four prompts; seeds 11..20 are held out until prompt selection.
One occupied option (either colour) plus four empty options, same in both densities.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import asdict
from datetime import datetime,timezone
from functools import lru_cache
import json
from pathlib import Path
import random
import basics as B

PROMPTS={
 'short_en':'Which candidate coordinate appears as a move in moves? Choose that coordinate.',
 'short_ko':'moves에 실제로 등장하는 착수 좌표를 선택하세요. 돌의 색은 구분하지 마세요.',
 'parse_en':'moves lists occupied coordinates concatenated without separators. Each coordinate is one letter a-o followed by a number 1-15. Match whole coordinates, not partial substrings. Which candidate is present? Ignore stone colour.',
 'baseline':B.QUESTIONS['occupied']+' '+B.sight.BOARD_COMPACT,
}
CONFIG=B.HERE/'occupancy_prompt.json'


def selected_prompt():
    if CONFIG.exists():return json.loads(CONFIG.read_text())['prompt']
    return 'short_en'


@lru_cache(maxsize=64)
def cases_for_seed(seed):
    pair=[c for c in B.cases_for_seed(seed) if c.stage=='complete']
    sparse,dense=pair
    board_sparse=B.replay(sparse.moves);board_dense=B.replay(dense.moves)
    rng=random.Random(817000+seed)
    # Balance target colour across each ten-seed split, vary its move index.
    colour=1 if seed%2 else 2
    targets=[at for i,at in enumerate(sparse.moves) if 1+i%2==colour]
    target=rng.choice(targets)
    pool=[B.E.coord(r,c) for r in range(15) for c in range(15)
          if not board_sparse[r][c] and not board_dense[r][c] and B.E.neighbours(board_sparse,r,c,2)]
    options=[target,*rng.sample(pool,4)];rng.shuffle(options)
    cases=[B.Case(seed,'occupied',c.density,c.direction,c.moves,options[:],target) for c in pair]
    for c in cases:B.validate(c)
    return cases


def ask(case,condition='base',prompt=None):
    prompt=prompt or selected_prompt()
    if prompt not in PROMPTS:raise ValueError('Unknown occupancy prompt')
    result=B.ask(case,condition,instructions_override=PROMPTS[prompt])
    return {**result,'prompt':prompt}


def run(jobs,workers):
    random.Random(781).shuffle(jobs)
    result=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(ask,*job) for job in jobs]):
            result.append(future.result())
    return result


def score(rows):return {'hit':sum(t['hit'] for t in rows),'n':len(rows)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    tuning=[c for seed in range(1,11) for c in cases_for_seed(seed)]
    trials=run([(c,'base',p) for c in tuning for p in PROMPTS],args.workers)
    tuning_scores={p:score([t for t in trials if t['prompt']==p]) for p in PROMPTS}
    chosen=min(PROMPTS,key=lambda p:(-tuning_scores[p]['hit'],len(PROMPTS[p]),p))
    print('Tuning:',json.dumps(tuning_scores),'selected:',chosen,flush=True)
    # Selection is frozen before constructing/calling the held-out problems.
    heldout=[c for seed in range(11,21) for c in cases_for_seed(seed)]
    evaluation=run([(c,condition,p) for c in heldout for condition in ('base','repeat','shuffle')
                    for p in dict.fromkeys((chosen,'baseline'))],args.workers)
    summaries={}
    for p in dict.fromkeys((chosen,'baseline')):
        for density in ('sparse','dense','all'):
            for condition in ('base','repeat','shuffle'):
                rows=[t for t in evaluation if t['prompt']==p and t['condition']==condition and (density=='all' or t['density']==density)]
                summaries[f'{p}/{density}/{condition}']=score(rows)
    result={'model':B.brain.MODEL,'created_at':datetime.now(timezone.utc).isoformat(),
        'design':'same compact state and options across prompts; one occupied (balanced black/white) and four empty coordinates; tuning seeds1-10, heldout11-20; selected by hits then shortest instructions',
        'prompts':PROMPTS,'chosen':chosen,'tuning_summary':tuning_scores,'heldout_summary':summaries,
        'cases':[asdict(c) for c in tuning+heldout], 'tuning_trials':trials,'heldout_trials':evaluation,
        'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials+evaluation)*B.brain.USD_PER_TOKEN,4)}
    (B.HERE/'results_occupancy.json').write_text(json.dumps(result,ensure_ascii=False,indent=1))
    CONFIG.write_text(json.dumps({'prompt':chosen,'instructions':PROMPTS[chosen]},ensure_ascii=False,indent=2))
    print(json.dumps({'heldout':summaries,'cost_usd':result['cost_usd']},ensure_ascii=False))

if __name__=='__main__':main()
