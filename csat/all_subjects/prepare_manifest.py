"""Map objective question IDs to odd-form source pages; keep gold separate."""
import json
from pathlib import Path
import re

from fetch_sources import HERE, NAMES

DIGITS = '①②③④⑤'


def section(subject, page):
    if subject == 'korean':
        return 'korean-common' if page <= 12 else 'korean-speech' if page <= 16 else 'korean-language'
    if subject == 'math':
        return ('math-common' if page <= 8 else 'math-probability' if page <= 12
                else 'math-calculus' if page <= 16 else 'math-geometry')
    return subject


def main():
    gold = {}
    for subject in NAMES:
        text = (HERE/'sources/answer'/f'{subject}.txt').read_text().split('\f')[0]
        text = text.translate(str.maketrans('０１２３４５６７８９','0123456789'))
        for line in text.splitlines():
            triples = [(int(n),DIGITS.index(a)+1,int(w)) for n,a,w in re.findall(r'(\d{1,2})\s+([①②③④⑤])\s+([1-4])\b',line)]
            elective_index = 0
            for number, answer, points in triples:
                sec = subject
                if subject == 'korean':
                    if number < 35: sec='korean-common'
                    else:
                        sec=['korean-speech','korean-language'][elective_index];elective_index+=1
                elif subject == 'math':
                    if number <= 15: sec='math-common'
                    elif 23 <= number <= 28:
                        sec=['math-probability','math-calculus','math-geometry'][elective_index];elective_index+=1
                    else: raise AssertionError((subject,number))
                qid=f'{sec}:{number}'
                assert qid not in gold,qid
                gold[qid]={'answer':answer,'points':points,'subject':subject,'section':sec,'number':number}
    assert len(gold)==884,len(gold)
    tasks=[]
    ownership={}
    next_number={sec:min(g['number'] for g in gold.values() if g['section']==sec) for sec in {g['section'] for g in gold.values()}}
    for subject in NAMES:
        pages=(HERE/'sources/exam'/f'{subject}.txt').read_text().split('\f')
        limit=20 if subject in ['math','korean'] else 8 if subject=='english' else 4
        for page,text in enumerate(pages[:limit],1):
            sec=section(subject,page)
            numbers=sorted(set(int(n) for n in re.findall(r'(?:^|\s{3,})(\d{1,2})\.\s',text,re.M)))
            if subject=='agriculture' and page==1:
                # A numbered lab-procedure step is not question 5; question 5
                # starts on page 2. Confirmed against the source page image.
                numbers=[n for n in numbers if n!=5]
            if subject=='arabic-1':
                visible=re.sub('[\u202a-\u202e\u2066-\u2069]','',text)
                numbers=sorted(set(int(n) for n in re.findall(r'(\d{1,2})\.\s*',visible)))
            targets=[]
            n=next_number[sec]
            while n in numbers and f'{sec}:{n}' in gold:
                targets.append(n)
                n+=1
            next_number[sec]=n
            if subject=='english':targets=[n for n in targets if n<=17] # reuse validated reading inputs
            if not targets:continue
            for n in targets:
                qid=f'{sec}:{n}'
                assert qid not in ownership,(qid,page,ownership.get(qid))
                ownership[qid]=page
            tasks.append({'subject':subject,'name':NAMES[subject],'section':sec,'page':page,'targets':targets})
    missing=set(gold)-set(ownership)-{f'english:{n}' for n in range(18,46)}
    assert not missing,missing
    (HERE/'gold.json').write_text(json.dumps(gold,ensure_ascii=False,indent=2))
    (HERE/'page-tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2))
    print('Objective questions:',len(gold),'new page extraction tasks:',len(tasks),'new questions:',len(ownership))


if __name__=='__main__':main()
