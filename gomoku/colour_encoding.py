"""Follow-up: keep the selected prompt, vary coordinate separators only.

No move numbers or colours are added to state. Reuse compact results from the
preceding prompt comparison; select encoding on tuning seeds, freeze for heldout.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json,random
import colour as C

CONFIG=C.B.HERE/'colour_encoding.json'


def selected_encoding():
    return json.loads(CONFIG.read_text())['encoding'] if CONFIG.exists() else 'compact'


def run(jobs):
    random.Random(9300).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=4) as pool:
        return [f.result() for f in as_completed([pool.submit(C.ask,*j) for j in jobs])]


def main():
    earlier=json.loads((C.B.HERE/'results_colour.json').read_text());prompt=earlier['chosen']
    base_tune=[{**t,'encoding':'compact'} for t in earlier['tuning_trials'] if t['prompt']==prompt]
    tuning=[c for seed in range(1,11) for c in C.cases_for_seed(seed)]
    new_tune=run([(c,'base',prompt,e) for c in tuning for e in ('spaced','array')])
    trials=base_tune+new_tune
    scores={e:sum(t['hit'] for t in trials if t['encoding']==e) for e in ('compact','spaced','array')}
    # Prefer less transformed input on ties.
    chosen=max(scores,key=scores.get)
    print('Encoding tuning /40',scores,'chosen',chosen,flush=True)
    base_eval=[{**t,'encoding':'compact'} for t in earlier['heldout_trials'] if t['prompt']==prompt and t['condition'] in ('base','repeat','shuffle')]
    cases=[c for seed in range(11,21) for c in C.cases_for_seed(seed)]
    new_eval=run([(c,condition,prompt,chosen) for c in cases for condition in ('base','repeat','shuffle')]) if chosen!='compact' else []
    evaluation=base_eval+new_eval;summary={}
    for encoding in dict.fromkeys(('compact',chosen)):
        for density in ('sparse','dense','all'):
            for condition in ('base','repeat','shuffle'):
                rows=[t for t in evaluation if t['encoding']==encoding and t['condition']==condition and (density=='all' or t['density']==density)]
                summary[f'{encoding}/{density}/{condition}']={'hit':sum(t['hit'] for t in rows),'n':len(rows),
                    'black_hit':sum(t['hit'] for t in rows if t['answer']=='black'),'white_hit':sum(t['hit'] for t in rows if t['answer']=='white')}
    out={'created_at':datetime.now(timezone.utc).isoformat(),'prompt':prompt,'chosen_encoding':chosen,
         'tuning_scores':scores,'heldout_summary':summary,'tuning_trials':trials,'heldout_trials':evaluation,
         'reuse':'compact trials copied from results_colour.json; heldout seeds previously evaluated there, so this is follow-up validation, not a fully untouched test set',
         'additional_cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in new_tune+new_eval)*C.B.brain.USD_PER_TOKEN,4)}
    (C.B.HERE/'results_colour_encoding.json').write_text(json.dumps(out,ensure_ascii=False,indent=1))
    CONFIG.write_text(json.dumps({'encoding':chosen,'prompt':prompt},indent=2))
    print(json.dumps({'summary':summary,'additional_cost_usd':out['additional_cost_usd']}))

if __name__=='__main__':main()
