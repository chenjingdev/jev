"""Isolate the state key name: identical value, instructions, options and order.

Five identical repeats per key/position; question uses no field-name reference.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import json,random,time
import knight as K
import probe as P

FIELDS=('pgn_moves','moves','data','x')
INSTRUCTIONS=('Which candidate square currently contains a white knight? Select the square after all recorded moves, '
              'not a square the knight occupied earlier. The supplied text is standard SAN movetext played from '
              'the standard initial chess position; N denotes a knight.')


def request_for(index,field):
    if field not in FIELDS:raise ValueError('Unknown field')
    c=K.cases()[index-1]
    return {'model':P.MODEL,'state':{field:c['pgn_moves']},
            'questions':{'point':{'type':'choice','instructions':INSTRUCTIONS,'criteria':{at:None for at in c['options']}}}}


def ask(index,field,repeat):
    c=K.cases()[index-1];K.validate(c);request=request_for(index,field);q=request['questions']['point']
    started=time.perf_counter()
    response=P.client().system_one(model=request['model'],state=request['state'],
        questions={'point':P.Choice(instructions=q['instructions'],criteria=q['criteria'])})
    a=response.answers['point'];usage=response.usage
    if a.choice not in q['criteria'] or set(a.probabilities)!=set(q['criteria']):raise ValueError('Options mismatch')
    return {'index':index,'length':c['length'],'field':field,'repeat':repeat,'answer':c['answer'],
            'pick':a.choice,'hit':a.choice==c['answer'],'probabilities':dict(a.probabilities),
            'p_target':a.probabilities[c['answer']],'confidence':a.confidence,
            'latency_ms':round(1000*(time.perf_counter()-started)),
            'input_tokens':usage.input_tokens,'output_tokens':usage.output_tokens,'request':request}


def main():
    jobs=[(index,field,repeat) for index in range(1,21) for field in FIELDS for repeat in range(1,6)]
    random.Random(70123).shuffle(jobs)
    with ThreadPoolExecutor(max_workers=4) as pool:trials=[f.result() for f in as_completed([pool.submit(ask,*j) for j in jobs])]
    summary={}
    for field in FIELDS:
        rows=[t for t in trials if t['field']==field]
        summary[field]={'hit':sum(t['hit'] for t in rows),'n':len(rows),
            'per_repeat':[sum(t['hit'] for t in rows if t['repeat']==rep) for rep in range(1,6)],
            'short_hit':sum(t['hit'] for t in rows if t['length']=='short'),
            'long_hit':sum(t['hit'] for t in rows if t['length']=='long'),
            'mean_p_target':round(sum(t['p_target'] for t in rows)/len(rows),4),
            'positions_with_changed_pick_across_repeats':sum(len({t['pick'] for t in rows if t['index']==i})>1 for i in range(1,21))}
    result={'model':P.MODEL,'created_at':datetime.now(timezone.utc).isoformat(),
        'design':'20 existing positions, 4 field names, 5 repeats; fixed generic instructions without key reference; candidates/order/state value identical; randomized job ordering; only state key varies',
        'summary':summary,'trials':trials,'cost_usd':round(sum(t['input_tokens']+t['output_tokens'] for t in trials)*P.USD_PER_TOKEN,4)}
    (P.HERE/'results_field_names.json').write_text(json.dumps(result,ensure_ascii=False,indent=1))
    print(json.dumps({'summary':summary,'cost_usd':result['cost_usd']}))

if __name__=='__main__':main()
