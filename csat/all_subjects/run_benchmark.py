"""Resumable primary-pass benchmark. No answer keys are opened by this runner."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_exam import make_job,ask as ask_jev
from run_openai_comparison import chat_job,ask as ask_openai,MODELS

HERE=Path(__file__).resolve().parent
ALL_MODELS=['jev-1.13.0',*MODELS]


def request_hash(job):
    return hashlib.sha256(json.dumps(job['request'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def run_one(model,q,output,reuse):
    job=make_job(q,0) if model=='jev-1.13.0' else chat_job(q,0,model)
    digest=request_hash(job)
    target=output/model/f'{q["id"].replace(":","-")}-{digest[:12]}.json'
    if target.exists():
        cached=json.loads(target.read_text())
        if cached.get('status') in ['complete','invalid_answer']:return 'cached',model,q['id']
    record={'id':q['id'],'subject':q['subject'],'section':q['section'],'number':q['number'],
            'model':model,'reasoning_effort':None if model=='jev-1.13.0' else 'low',
            'request_sha256':digest,'quality_status':q['quality_status'],'has_visual':q['has_visual'],
            'job':job,'attempts':[],'status':'running'}
    if target.exists():
        old_record=json.loads(target.read_text())
        record['previous_attempts']=old_record.get('previous_attempts',[])+old_record.get('attempts',[])
    old=reuse.get((model,q['number'])) if q['subject']=='english' and q['number']>=18 else None
    if old and old['request']==job['request']:
        record['job']=old;record['status']='complete';record['reused_previous_english_reading']=True
    else:
        for attempt in range(3):
            try:
                result={'response':ask_jev(job)} if model=='jev-1.13.0' else ask_openai(job)
                record['attempts'].append(result)
                if 'response' in result:
                    record['job'].update(result);record['status']='complete';break
                if result.get('error_type')=='invalid_answer':
                    record['status']='invalid_answer';break
                record['status']='transport_error'
            except Exception as exc:
                record['attempts'].append({'error_type':type(exc).__name__,'message':str(exc)[:180]})
                record['status']='transport_error'
            if attempt<2:time.sleep(2**attempt)
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(record,ensure_ascii=False,indent=1));tmp.replace(target)
    return record['status'],model,q['id']


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=6)
    ap.add_argument('--models',nargs='+',choices=ALL_MODELS,default=ALL_MODELS)
    ap.add_argument('--output',type=Path,default=HERE/'results');args=ap.parse_args()
    dataset=json.loads((HERE/'dataset.json').read_text())
    reuse={}
    for model in args.models:
        path=(HERE.parent/'results/2026-english-reading-jev-1.13.0.json' if model=='jev-1.13.0'
              else HERE.parent/'results/openai-low-20260922'/f'{model}-low.json')
        for job in json.loads(path.read_text())['jobs']:
            if job['rotation']==0:reuse[model,job['number']]=job
    jobs=[(model,q) for q in dataset['questions'] for model in args.models]
    print(f'{len(dataset["questions"])} source-reviewed questions; {len(jobs)} model/question pairs',flush=True)
    counts={}
    with ThreadPoolExecutor(args.workers) as pool:
        futures=[pool.submit(run_one,m,q,args.output,reuse) for m,q in jobs]
        for i,f in enumerate(as_completed(futures),1):
            status,model,qid=f.result();counts[status]=counts.get(status,0)+1
            if i%50==0 or status not in ['complete','cached'] or i==len(jobs):
                print(i,'/',len(jobs),counts,model,qid,flush=True)


if __name__=='__main__':main()
