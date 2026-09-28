"""Reuse the source-only transcription/checking pipeline in a separate directory."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import sys
import base64

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'all_subjects'))
import transcribe as t

t.HERE=HERE/'validation_2025'
t.INSTRUCTIONS+='\nDo not assign unknown labels (가), (나), A, B, etc. to named regions, entities or solved values. Preserve unknown correspondences. Transcribe the printed prompt, including any question instructions shared across adjacent questions.'


def material(task,pages):
    native=(t.HERE/'sources/exam'/f'{task["subject"]}.txt').read_text().split('\f')
    aid='\n'.join(native[:8]) if task['subject']=='english' else '\n'.join(native[p-1] for p in pages)
    content=[{'type':'text','text':f'Current page {task["page"]}. Target questions: {task["targets"]}. Native reading aid (fallible layout):\n'+aid}]
    for p in pages:
        content.extend([{'type':'text','text':f'Source page {p}'},
                        {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(t.image_path(task['subject'],p).read_bytes()).decode()}}])
    return content

t.material=material


if __name__=='__main__':
    tasks=json.loads((t.HERE/'page-tasks.json').read_text())
    for task in tasks:t.render(task)
    with ThreadPoolExecutor(8) as pool:
        futures={pool.submit(t.process,task):task for task in tasks}
        for i,f in enumerate(as_completed(futures),1):
            try:r=f.result()
            except Exception as e:r=(futures[f],type(e).__name__,str(e)[:150])
            print(i,'/',len(tasks),r,flush=True)
