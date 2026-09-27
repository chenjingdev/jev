"""Assemble source-checked validation inputs; no answer key is read."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent/'validation_2025'


def main():
    tasks=json.loads((HERE/'page-tasks.json').read_text());items=[];pending=[]
    for task in tasks:
        path=HERE/'transcriptions'/f'{task["subject"]}-{task["page"]:02d}.json'
        if not path.exists():pending.append((task['subject'],task['page'],'missing'));continue
        r=json.loads(path.read_text())
        if r['status'] not in ['reviewed','human_reviewed','reviewed_with_minor_warnings']:
            pending.append((task['subject'],task['page'],r['status']));continue
        assert sorted(q['number'] for q in r['questions'])==task['targets']
        for q in r['questions']:
            options=[f'원문에 표시된 {s.strip()}' if s.strip() in '①②③④⑤' and len(s.strip())==1 else re.sub(r'^\s*[①②③④⑤]\s*','',s).strip() for s in q['options']]
            state={'question':q['question'],'passage':q['context']}
            if q['visual_description']:state['visual_description']=q['visual_description']
            assert len(options)==5 and all(options)
            visible='\n'.join([*state.values(),*options])
            assert not re.search('[\x08\x0c]|\t(?:heta|imes|ext)|\r(?:ight|ho|angle)',visible),(task,q['number'])
            items.append({'id':f'{task["subject"]}:{q["number"]}','subject':task['subject'],'section':task['subject'],
                          'number':q['number'],'state':state,'options':options,'source_page':task['page'],
                          'source_record_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'quality_status':r['status']})
    print(len(items),'/128 inputs ready; pending:',pending)
    assert len(items)==128 and not pending
    assert len({q['id'] for q in items})==128
    (HERE/'dataset.json').write_text(json.dumps({'year':2025,'status':'complete','questions':sorted(items,key=lambda q:(q['subject'],q['number']))},ensure_ascii=False,indent=1))


if __name__=='__main__':main()
