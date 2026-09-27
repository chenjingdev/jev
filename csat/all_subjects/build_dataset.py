"""Assemble only source-reviewed text stimuli; never load gold answers."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from fetch_sources import HERE, NAMES


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--require-complete',action='store_true');args=ap.parse_args()
    tasks=json.loads((HERE/'page-tasks.json').read_text())
    items=[];pending=[]
    for task in tasks:
        file=HERE/'transcriptions'/f'{task["subject"]}-{task["page"]:02d}.json'
        if not file.exists():pending.append({'task':task,'status':'missing'});continue
        try:record=json.loads(file.read_text())
        except json.JSONDecodeError:pending.append({'task':task,'status':'being_written'});continue
        if record['status'] not in ['reviewed','reviewed_with_minor_warnings','human_reviewed']:
            pending.append({'task':task,'status':record['status']});continue
        assert sorted(q['number'] for q in record['questions'])==task['targets']
        for q in record['questions']:
            options=[(f'원문에 표시된 {s.strip()}' if s.strip() in '①②③④⑤' and len(s.strip())==1
                      else re.sub(r'^\s*[①②③④⑤]\s*','',s).strip()) for s in q['options']]
            assert len(options)==5 and all(options)
            state={'question':q['question'],'passage':q['context']}
            if q['visual_description']:state['visual_description']=q['visual_description']
            visible='\n'.join([*state.values(),*options])
            assert not re.search('[\x08\x0c]|\t(?:heta|imes|ext)|\r(?:ight|ho|angle)',visible),(task,q['number'],'corrupt math escape')
            items.append({'id':f'{task["section"]}:{q["number"]}','subject':task['subject'],
                          'subject_name':NAMES[task['subject']],'section':task['section'],'number':q['number'],
                          'state':state,'options':options,'has_visual':q['has_visual'],
                          'quality_status':record['status'],'source_page':task['page'],
                          'source_record_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
                          'source_record':str(file),'warnings':q['uncertainties']})
    english=json.loads((HERE.parent/'data/2026-english-reading.json').read_text())
    for q in english['questions']:
        items.append({'id':f'english:{q["number"]}','subject':'english','subject_name':'영어',
                      'section':'english','number':q['number'],'state':q['state'],'options':q['options'],
                      'has_visual':q['number']==25,'quality_status':'previously_source_checked',
                      'source_record':str(HERE.parent/'data/2026-english-reading.json'),'warnings':[]})
    assert len({q['id'] for q in items})==len(items)
    for q in items:
        if q['subject']=='math':assert q['number']<=15 or 23<=q['number']<=28
    payload={'status':'complete' if len(items)==884 else 'partial','expected_objective_questions':884,
             'short_answer_excluded':13,'comparison_mode':'Text-only adapted input, original option order, one independent question call per model.',
             'questions':sorted(items,key=lambda q:(q['section'],q['number'])),'pending_pages':pending}
    path=HERE/'dataset.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=1));tmp.replace(path)
    print(f'{len(items)}/884 reviewed inputs assembled; {len(pending)} pages pending')
    if args.require_complete:assert payload['status']=='complete'


if __name__=='__main__':main()
