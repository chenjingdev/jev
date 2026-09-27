"""One-call Jev ablations, interleaved and scored only after collection."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import random
import sys

from prompts import VARIANTS,build_job
from run_exam import ask,save

HERE=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dataset',type=Path,required=True);ap.add_argument('--gold',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--variants',nargs='+',choices=VARIANTS,default=VARIANTS)
    ap.add_argument('--workers',type=int,default=8);args=ap.parse_args()
    raw=args.dataset.read_bytes();data=json.loads(raw);questions=data['questions']
    args.output.mkdir(parents=True,exist_ok=False)
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'dataset_sha256':hashlib.sha256(raw).hexdigest(),
              'prompts_sha256':hashlib.sha256((HERE/'prompts.py').read_bytes()).hexdigest(),
              'variants':args.variants,'questions':len(questions),'model':'jev-1.13.0','call_budget_per_question_variant':1,
              'question_ids':[q['id'] for q in questions],'seed':20260923,'status':'running'}
    save(args.output/'manifest.json',manifest)
    jobs=[]
    rng=random.Random(20260923)
    for q in questions:
        variants=list(args.variants);rng.shuffle(variants)
        jobs.extend((q,build_job(q,v)) for v in variants)
    def work(item):
        q,job=item
        record={'id':q['id'],'subject':q['subject'],'section':q['section'],'number':q['number'],
                'source_page':q.get('source_page'), 'variant':job['variant'],'job':job}
        try:record['job']['response']=ask(job);record['status']='complete'
        except Exception as exc:record['status']='error';record['error_type']=type(exc).__name__;record['error_message']=str(exc)[:180]
        path=args.output/job['variant']/(q['id'].replace(':','-')+'.json');path.parent.mkdir(exist_ok=True)
        save(path,record)
        return record
    records=[]
    with ThreadPoolExecutor(args.workers) as pool:
        for i,f in enumerate(as_completed([pool.submit(work,j) for j in jobs]),1):
            records.append(f.result())
            if i%100==0 or i==len(jobs):print(i,'/',len(jobs),'responses collected',flush=True)
    assert all(r['status']=='complete' for r in records), 'Do not score an incomplete batch'
    gold_raw=args.gold.read_bytes();gold=json.loads(gold_raw)
    summary={}
    for variant in args.variants:
        rows=[r for r in records if r['variant']==variant]
        correct=sum(r['job']['response']['original_option']==gold[r['id']]['answer'] for r in rows)
        summary[variant]={'n':len(rows),'correct':correct,'accuracy':correct/len(rows),
                          'input_tokens':sum(r['job']['response']['usage']['input_tokens'] for r in rows),
                          'output_tokens':sum(r['job']['response']['usage']['output_tokens'] for r in rows)}
    manifest.update(status='complete',gold_sha256=hashlib.sha256(gold_raw).hexdigest(),summary=summary)
    save(args.output/'manifest.json',manifest);print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
