"""Matched coordinate-token tests. One negative is replaced with a false prefix.

Examples: a10 exists but a1 is empty. All variants share the same legal history,
positive coordinate, and option slot. Two English prompts; minimal vs rich state.
Select on seeds 1..10, then freeze and evaluate seeds 11..20 with repeat/shuffle.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import asdict
from datetime import datetime,timezone
from functools import lru_cache
import copy
import json
import random
import basics as B
import occupancy as O

PROMPTS={
 'short_en':'Which candidate coordinate appears as a move in `moves`? Choose that coordinate.',
 'exact_en':'`moves` is a sequence of coordinates with no separators. Each coordinate is one letter a-o followed by its complete number 1-15. Select the candidate that matches a whole coordinate in `moves`. A prefix of a longer coordinate is not a match. Ignore stone colour.',
}
CONFIG=B.HERE/'occupancy_boundary_prompt.json'


def selected_prompt():
    return json.loads(CONFIG.read_text())['prompt'] if CONFIG.exists() else 'exact_en'


@lru_cache(maxsize=64)
def cases_for_seed(seed):
    # A local, alternating path connects the centre to row 1. Both i10/j10
    # occur, but exactly one of i1/j1 is occupied. No distant stone insertion.
    rng=random.Random(771300+seed)
    backbone='h8 i9 j10 i10 j9 k8 j7 i6 j5 k4 j3 i2'.split()
    edge='i1' if seed%4 in (0,1) else 'j1'
    trap='j1' if edge=='i1' else 'i1'
    for attempt in range(200):
        prefix=backbone[:];board=B.replay(prefix)
        fixed={'i1','j1'}
        okay=True
        for _ in range(4):
            player=B.E.BLACK if len(prefix)%2==0 else B.E.WHITE
            pool=[a for a in B.E.candidates(board,player,cap=225,radius=1)
                  if a['id'] not in fixed and a['r']<13 and not a['wins']]
            if not pool or not B.legal_drop(board,prefix,rng.choice(pool[:16])['id']):okay=False;break
        if not okay:continue
        sparse=prefix+[edge]
        try:B.replay(sparse)
        except ValueError:continue
        dense=prefix[:];dense_board=B.replay(prefix)
        for _ in range(20):
            player=B.E.BLACK if len(dense)%2==0 else B.E.WHITE
            pool=[a for a in B.E.candidates(dense_board,player,cap=225,radius=1)
                  if a['id'] not in fixed and a['r']<13 and not a['wins']]
            if not pool or not B.legal_drop(dense_board,dense,rng.choice(pool[:16])['id']):okay=False;break
        if not okay:continue
        dense.append(edge)
        try:B.replay(dense)
        except ValueError:continue
        # Half the seeds have a genuine row-1 answer, half another row.
        target=edge if seed%2 else rng.choice([at for at in prefix if int(at[1:])!=1])
        empty=[B.E.coord(r,c) for r in range(15) for c in range(15)
               if B.E.coord(r,c) not in ''.join(dense)
               and B.E.coord(r,c) not in ''.join(sparse)
               and B.E.neighbours(board,r,c,2)]
        if len(empty)<4:continue
        options=[target,*rng.sample(empty,4)];rng.shuffle(options)
        slot=rng.choice([i for i,at in enumerate(options) if at!=target])
        cases=[]
        for density,moves in [('sparse',sparse),('dense',dense)]:
            for variant in ('control','boundary'):
                choices=options[:]
                if variant=='boundary':choices[slot]=trap
                case=B.Case(seed,'occupied',density,'mixed',moves[:],choices,target)
                B.validate(case);cases.append((variant,case))
        return cases
    raise ValueError('Could not build a balanced row-1 case')


def ask(case,variant='boundary',condition='base',prompt=None,state_mode='minimal'):
    if condition not in ('base','repeat','shuffle'):raise ValueError('Boundary test supports original, repeat or shuffle')
    prompt=prompt or selected_prompt()
    if prompt not in PROMPTS or state_mode not in ('minimal','rich'):raise ValueError('Unknown prompt or state mode')
    state={'moves':''.join(case.moves)}
    if state_mode=='rich':state={'game':'gomoku, 15x15','to_move':'white',**state}
    out=B.ask(case,condition,instructions_override=PROMPTS[prompt],state_override=state)
    trap=next((at for at in case.options if at not in case.moves and at in state['moves']),None)
    return {**out,'variant':variant,'prompt':prompt,'state_mode':state_mode,
            'target_row1':int(case.target[1:])==1,'prefix_trap':trap,'picked_prefix':out['pick']==trap if trap else False}


def run(jobs):
    random.Random(2900).shuffle(jobs)
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(ask,*job) for job in jobs]):results.append(future.result())
    return results


def summary(trials):
    out={}
    for t in trials:
        key='/'.join(t[k] for k in ('prompt','state_mode','variant','density','condition'))
        r=out.setdefault(key,{'hit':0,'n':0,'picked_prefix':0,'row1_hit':0,'row1_n':0})
        r['hit']+=int(t['hit']);r['n']+=1;r['picked_prefix']+=int(t['picked_prefix'])
        r['row1_n']+=int(t['target_row1']);r['row1_hit']+=int(t['target_row1'] and t['hit'])
    return dict(sorted(out.items()))


def main():
    tuning=[(v,c) for seed in range(1,11) for v,c in cases_for_seed(seed)]
    trials=run([(c,v,'base',p,state) for v,c in tuning for p in PROMPTS for state in ('minimal','rich')])
    score={p:sum(t['hit'] for t in trials if t['prompt']==p and t['state_mode']=='minimal') for p in PROMPTS}
    chosen=min(PROMPTS,key=lambda p:(-score[p],len(PROMPTS[p])))
    print('Tuning minimal hits /40:',score,'chosen:',chosen,flush=True)
    # Freeze selection before constructing held-out data.
    evaluation=[(v,c) for seed in range(11,21) for v,c in cases_for_seed(seed)]
    heldout=run([(c,v,cond,p,'minimal') for v,c in evaluation for p in PROMPTS for cond in ('base','repeat','shuffle')])
    result={'created_at':datetime.now(timezone.utc).isoformat(),'model':B.brain.MODEL,
        'design':'balanced row1 answers (half of seeds) and false row1 prefixes; local legal 17/37-stone sequences; tune1-10 then heldout11-20; matched control/boundary',
        'version':'row1-balanced-v2',
        'prompts':PROMPTS,'chosen':chosen,'tuning_summary':summary(trials),'heldout_summary':summary(heldout),
        'cases':[{'variant':v,**asdict(c)} for v,c in tuning+evaluation],
        'tuning_trials':trials,'heldout_trials':heldout,
        'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials+heldout)*B.brain.USD_PER_TOKEN,4)}
    (B.HERE/'results_occupancy_boundaries.json').write_text(json.dumps(result,ensure_ascii=False,indent=1))
    CONFIG.write_text(json.dumps({'prompt':chosen,'instructions':PROMPTS[chosen]},indent=2))
    print(json.dumps({'heldout_summary':result['heldout_summary'],'cost_usd':result['cost_usd']}))

if __name__=='__main__':main()
