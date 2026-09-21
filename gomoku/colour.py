"""Prompt structure study: colour of one given occupied coordinate.

All prompts receive identical compact moves and coordinate; only instructions
vary. No code-derived move index, pair grouping or colour is sent to the model.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from functools import lru_cache
import copy
import json
import random
import time
import basics as B
from typesafe_sdk import Choice

FORMAT='`moves` contains coordinates concatenated without separators. Each coordinate is a letter a-o followed by its complete number 1-15.'
PROMPTS={
 'rules':FORMAT+' Black moves first, then black and white alternate. What colour is the stone at `coordinate`?',
 'index':FORMAT+' Find the complete coordinate in `coordinate` within this sequence. Count moves starting at 1, not characters: moves 1,3,5,... are black; moves 2,4,6,... are white. What colour is the stone at `coordinate`?',
 'pairs':FORMAT+' Read the sequence as consecutive pairs of moves from the beginning. In each pair, the first coordinate is black and the second is white. An unpaired final move is black. What colour is the stone at `coordinate`?',
 'structured':{'question':'What colour is the stone at `coordinate`?',
               'encoding':FORMAT,
               'rules':['The first move is black.','Moves alternate black, white.','Odd move numbers (1-based) are black; even move numbers are white.'],
               'focus':'Match a complete coordinate. The numerical row in a coordinate is not its move number.'},
}
CONFIG=B.HERE/'colour_prompt.json'


def selected_prompt():
    return json.loads(CONFIG.read_text())['prompt'] if CONFIG.exists() else 'rules'


@lru_cache(maxsize=64)
def cases_for_seed(seed):
    pair=[c for c in B.cases_for_seed(seed) if c.stage=='complete']
    sparse,dense=pair;rng=random.Random(66000+seed)
    cases=[]
    for colour in ('black','white'):
        parity=0 if colour=='black' else 1
        choices=[at for i,at in enumerate(sparse.moves) if i%2==parity]
        coordinate=rng.choice(choices)
        for original in pair:
            assert (original.moves.index(coordinate)%2==0)==(colour=='black')
            cases.append({'seed':seed,'density':original.density,'moves':original.moves[:],
                          'coordinate':coordinate,'answer':colour})
    return cases


def ask(case,condition='base',prompt=None,encoding='compact'):
    if condition not in B.CONDITIONS:raise ValueError('Unknown condition')
    prompt=prompt or selected_prompt()
    if prompt not in PROMPTS:raise ValueError('Unknown colour prompt')
    case=copy.deepcopy(case)
    turns={'rotate90':1,'rotate180':2,'rotate270':3}.get(condition,0)
    case['moves']=[B.sight.rotate_coord(at,turns) for at in case['moves']]
    case['coordinate']=B.sight.rotate_coord(case['coordinate'],turns)
    board=B.replay(case['moves'])
    r,c=B.E.parse_coord(case['coordinate'])
    if B.E.NAME[board[r][c]]!=case['answer']:raise ValueError('Colour answer mismatch')
    if encoding not in ('compact','spaced','array','paired'):raise ValueError('Unknown encoding')
    moves_value=case['moves'] if encoding=='array' else (' ' if encoding=='spaced' else '').join(case['moves'])
    if encoding=='paired':moves_value=[case['moves'][i:i+2] for i in range(0,len(case['moves']),2)]
    state={'moves':moves_value,'coordinate':case['coordinate']}
    instructions=copy.deepcopy(PROMPTS[prompt])
    if encoding!='compact':
        note='`moves` is an ordered JSON array of complete coordinates.' if encoding=='array' else '`moves` is an ordered sequence of complete coordinates separated by spaces.'
        if encoding=='paired':note='`moves` is an ordered array of consecutive move pairs. Each inner array contains two complete coordinates, or one coordinate for an unpaired final move.'
        if isinstance(instructions,str):instructions=instructions.replace(FORMAT,note)
        else:instructions['encoding']=note
    labels=['black','white'] if case['seed']%2 else ['white','black']
    if condition=='shuffle':labels.reverse()
    criteria={label:None for label in labels}
    started=time.perf_counter()
    response=B.brain.client().system_one(model=B.brain.MODEL,state=state,
        questions={'point':Choice(instructions=instructions,criteria=criteria)})
    answer=response.answers['point'];usage=getattr(response,'usage',None)
    if answer.choice not in criteria or set(answer.probabilities)!=set(criteria):raise ValueError('Response label mismatch')
    return {**case,'stage':'colour','encoding':encoding,'condition':condition,'prompt':prompt,'board':board,
            'target':case['answer'],'pick':answer.choice,'hit':answer.choice==case['answer'],
            'probabilities':dict(answer.probabilities),'confidence':answer.confidence,
            'latency_ms':round(1000*(time.perf_counter()-started)),
            'input_tokens':usage.input_tokens if usage else 0,'output_tokens':usage.output_tokens if usage else 0,
            'request':{'model':B.brain.MODEL,'state':state,'questions':{'point':{'type':'choice','instructions':instructions,'criteria':criteria}}}}


def run(jobs):
    random.Random(92300).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [f.result() for f in as_completed([pool.submit(ask,*j) for j in jobs])]


def summary(trials):
    out={}
    for t in trials:
        key='/'.join(t[k] for k in ('prompt','density','condition'))
        row=out.setdefault(key,{'hit':0,'n':0,'black_hit':0,'black_n':0,'white_hit':0,'white_n':0})
        row['n']+=1;row['hit']+=int(t['hit']);row[t['answer']+'_n']+=1;row[t['answer']+'_hit']+=int(t['hit'])
    return dict(sorted(out.items()))


def main():
    tuning=[c for seed in range(1,11) for c in cases_for_seed(seed)]
    trials=run([(c,'base',p) for c in tuning for p in PROMPTS])
    scores={p:sum(t['hit'] for t in trials if t['prompt']==p) for p in PROMPTS}
    chosen=min(PROMPTS,key=lambda p:(-scores[p],len(json.dumps(PROMPTS[p]))))
    print('Tuning /40:',scores,'selected',chosen,flush=True)
    evaluation=[c for seed in range(11,21) for c in cases_for_seed(seed)]
    heldout=run([(c,condition,p) for c in evaluation for condition in ('base','repeat','shuffle','rotate90') for p in dict.fromkeys((chosen,'rules'))])
    result={'model':B.brain.MODEL,'created_at':datetime.now(timezone.utc).isoformat(),
            'design':'same compact moves and occupied coordinate; two unlabelled colour options; balanced black/white and option order; tune1-10 then heldout11-20',
            'prompts':PROMPTS,'chosen':chosen,'tuning_scores':scores,'heldout_summary':summary(heldout),
            'cases':tuning+evaluation,'tuning_trials':trials,'heldout_trials':heldout,
            'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials+heldout)*B.brain.USD_PER_TOKEN,4)}
    (B.HERE/'results_colour.json').write_text(json.dumps(result,ensure_ascii=False,indent=1))
    CONFIG.write_text(json.dumps({'prompt':chosen,'instructions':PROMPTS[chosen]},indent=2))
    print(json.dumps({'heldout_summary':result['heldout_summary'],'cost_usd':result['cost_usd']}))

if __name__=='__main__':main()
