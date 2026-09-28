"""Prepare the prospectively chosen 2025 validation set, separately from development."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

import requests

HERE=Path(__file__).resolve().parent
ROOT=HERE/'validation_2025'
SUBJECTS={'english':('영어','english-odd'),'korean-history':('한국사','korean-history-odd'),
          'life-ethics':('생활과 윤리','life-ethics'),'politics-law':('정치와 법','politics-law'),
          'physics-1':('물리학Ⅰ','physics-1'),'chemistry-1':('화학Ⅰ','chemistry-1')}


def fetch(job):
    subject,kind,url=job;folder=ROOT/'sources'/kind;folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{subject}.pdf'
    if not path.exists():
        r=requests.get(url,timeout=60);r.raise_for_status();assert r.content.startswith(b'%PDF');path.write_bytes(r.content)
    subprocess.run(['pdftotext','-layout',str(path),str(path.with_suffix('.txt'))],check=True)
    return {'subject':subject,'kind':kind,'url':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ROOT.mkdir(exist_ok=True)
    page=requests.get('https://www.haksi.kr/exams/2025/11',timeout=30);page.raise_for_status()
    urls=set(html.unescape(s) for s in re.findall(r'href="([^\"]*api/mock-exams/file[^\"]+)"',page.text))
    jobs=[]
    for subject,(_,slug) in SUBJECTS.items():
        for kind in ['exam','answer']:
            route=f'/api/mock-exams/file?id=2025-11-g3-{slug}-{kind}';assert route in urls
            jobs.append((subject,kind,'https://www.haksi.kr'+route))
    with ThreadPoolExecutor(6) as pool:sources=list(pool.map(fetch,jobs))
    (ROOT/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
    tasks=[];gold={}
    for subject,(name,_) in SUBJECTS.items():
        wanted=set(range(18,46) if subject=='english' else range(1,21))
        text=(ROOT/'sources/answer'/f'{subject}.txt').read_text().split('\f')[0]
        text=text.translate(str.maketrans('０１２３４５６７８９','0123456789'))
        for n,a,w in re.findall(r'(\d{1,2})\s+([①②③④⑤])\s+([1-4])\b',text):
            if int(n) in wanted:gold[f'{subject}:{int(n)}']={'answer':'①②③④⑤'.index(a)+1,'points':int(w)}
        assigned=set()
        pages=(ROOT/'sources/exam'/f'{subject}.txt').read_text().split('\f')
        for page,text in enumerate(pages[:8 if subject=='english' else 4],1):
            numbers=sorted(set(int(n) for n in re.findall(r'(?:^|\s{3,})(\d{1,2})\.\s',text,re.M)))
            targets=[n for n in numbers if n in wanted and n not in assigned]
            if targets:
                tasks.append({'subject':subject,'name':name,'section':subject,'page':page,'targets':targets});assigned.update(targets)
        assert assigned==wanted,(subject,assigned,wanted)
    if not gold:
        gold=json.loads((ROOT/'gold-manual.json').read_text())['answers']
    assert len(gold)==128,len(gold)
    (ROOT/'gold.json').write_text(json.dumps(gold,ensure_ascii=False,indent=2))
    (ROOT/'page-tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2))
    print('Prepared',len(tasks),'source pages for 128 validation questions')


if __name__=='__main__':main()
