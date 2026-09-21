"""Explicit preprocessing arm: code groups move pairs, no colour labels added.
This removes counting/pairing from the model's task and is not raw-record skill.
"""
import json
from datetime import datetime,timezone
import colour as C
import colour_encoding as F


def main():
    cases=[c for seed in range(1,21) for c in C.cases_for_seed(seed)]
    trials=F.run([(c,condition,'pairs','paired') for c in cases for condition in ('base','repeat','shuffle')])
    summary={}
    for split in ('first10','last10'):
        for density in ('sparse','dense','all'):
            for condition in ('base','repeat','shuffle'):
                rows=[t for t in trials if (t['seed']<=10)==(split=='first10') and t['condition']==condition and (density=='all' or t['density']==density)]
                summary[f'{split}/{density}/{condition}']={'hit':sum(t['hit'] for t in rows),'n':len(rows),
                    'black_hit':sum(t['hit'] for t in rows if t['answer']=='black'),'white_hit':sum(t['hit'] for t in rows if t['answer']=='white')}
    out={'created_at':datetime.now(timezone.utc).isoformat(),'design':'code-prepaired move tuples; fixed pairs instructions; previously used seeds, exploratory follow-up',
         'summary':summary,'trials':trials,'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*C.B.brain.USD_PER_TOKEN,4)}
    (C.B.HERE/'results_colour_pairs.json').write_text(json.dumps(out,ensure_ascii=False,indent=1))
    print(json.dumps({'summary':summary,'cost_usd':out['cost_usd']}))

if __name__=='__main__':main()
