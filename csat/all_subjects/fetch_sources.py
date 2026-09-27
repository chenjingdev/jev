"""Download source exam PDFs separately from answer PDFs; preserve provenance."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess

import requests

HERE = Path(__file__).resolve().parent
NAMES = {
 'korean':'국어','math':'수학','english':'영어','korean-history':'한국사',
 'east-asia-history':'동아시아사','economics':'경제','ethics-thought':'윤리와 사상',
 'korean-geography':'한국지리','life-ethics':'생활과 윤리','politics-law':'정치와 법',
 'social-culture':'사회·문화','world-geography':'세계지리','world-history':'세계사',
 'biology-1':'생명과학Ⅰ','biology-2':'생명과학Ⅱ','chemistry-1':'화학Ⅰ','chemistry-2':'화학Ⅱ',
 'earth-science-1':'지구과학Ⅰ','earth-science-2':'지구과학Ⅱ','physics-1':'물리학Ⅰ','physics-2':'물리학Ⅱ',
 'agriculture':'농업 기초 기술','commerce-economics':'상업 경제','fishery-maritime':'수산·해운 산업 기초',
 'human-development':'인간 발달','industrial-general':'공업 일반','successful-career':'성공적인 직업생활',
 'arabic-1':'아랍어Ⅰ','chinese-1':'중국어Ⅰ','french-1':'프랑스어Ⅰ','german-1':'독일어Ⅰ',
 'hanja-1':'한문Ⅰ','japanese-1':'일본어Ⅰ','russian-1':'러시아어Ⅰ','spanish-1':'스페인어Ⅰ','vietnamese-1':'베트남어Ⅰ',
}


def download(job):
    subject, kind, url = job
    folder = HERE / 'sources' / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{subject}.pdf'
    if not path.exists():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        assert r.content.startswith(b'%PDF'), (subject, kind, r.headers.get('Content-Type'))
        path.write_bytes(r.content)
    text_path = path.with_suffix('.txt')
    subprocess.run(['pdftotext','-layout',str(path),str(text_path)],check=True)
    info = subprocess.check_output(['pdfinfo',str(path)],text=True)
    return {'subject':subject,'name':NAMES[subject],'kind':kind,'url':url,'path':str(path),
            'pages':int(re.search(r'^Pages:\s+(\d+)',info,re.M)[1]),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    page = requests.get('https://www.haksi.kr/exams/2026/11',timeout=30)
    page.raise_for_status()
    links = set(html.unescape(x) for x in re.findall(r'href="([^\"]*api/mock-exams/file[^\"]+)"',page.text))
    jobs = []
    for subject in NAMES:
        for kind in ['exam','answer']:
            route = f'/api/mock-exams/file?id=2026-11-g3-{subject}-{kind}'
            assert route in links,route
            jobs.append((subject,kind,'https://www.haksi.kr'+route))
    records = []
    with ThreadPoolExecutor(6) as pool:
        for i,f in enumerate(as_completed([pool.submit(download,j) for j in jobs]),1):
            records.append(f.result())
            print(f'{i}/{len(jobs)} sources ready',flush=True)
    manifest = {'exam_year':2026,'forms':'Use odd form where two forms are present; retain all electives.',
                'excluded':'All numeric short-answer mathematics questions.',
                'records':sorted(records,key=lambda r:(r['subject'],r['kind']))}
    (HERE/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    for r in manifest['records']:
        if r['kind']=='exam':print(r['subject'],r['name'],r['pages'])


if __name__=='__main__':main()
