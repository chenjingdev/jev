"""Create shared text stimuli from exam pages, without ever loading answer keys.

Sol low performs literal transcription; Terra low checks source fidelity. The
result is a text-adapted benchmark, not a direct visual/audio exam benchmark.
"""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

import requests

from fetch_sources import HERE

ENDPOINT='http://127.0.0.1:11435/v1/chat/completions'
TRANSCRIBER_MODEL='gpt-5.6-sol'
INSTRUCTIONS='''You are transcribing an exam page for a text-only accessibility edition.
Produce faithful question inputs, not solutions. Copy all original words, symbols,
numbers, choices, and relevant shared passages. Preserve negation, underlined span
boundaries with <u> tags, blank positions, labelled statements and question-specific
tables. Convert formulas to unambiguous LaTeX, preserving powers, fractions,
subscripts, roots, integrals, domains, units and geometric marks. Describe visual
data literally: visible objects, printed labels, axes, ticks, curves, relative
positions and connections. Do not name an unlabelled historical object or person,
deduce quantities, calculate, translate foreign-language text, fix exam mistakes,
identify a correct choice, or add a hint. For picture choices provide neutral visual
descriptions of each picture in the options. Include every observation needed to
distinguish the choices. Keep all relevant shared passage text, not a summary.
Each question must be self-contained; include the complete relevant passage from
the current/adjacent images or section text, plus <보기> or dialogue when applicable.
Question numbering in the target list is metadata; do not include year, exam name,
answer keys or other questions in the question/context. Native text is a fallible
reading aid: images govern layout, mathematics, marks and all visual content.
To avoid duplicating long shared passages, copy each shared passage ONCE in
shared_passages with the target question_numbers it applies to. In each question's
context keep only its own additional material (e.g. <보기>). The pipeline will join
the shared passage and the question-specific context before testing.
Return only JSON: {"shared_passages":[{"question_numbers":[integers],"text":string}],
"questions":[{"number":integer,"question":string,
"context":string,"options":[five strings in original 1-5 order],
"has_visual":boolean,"visual_description":string,"uncertainties":[strings]}]}.
Return exactly the requested target questions. If a symbol or data cannot be read,
record the problem in uncertainties, rather than guessing.'''
REVIEW='''Check source fidelity of this text-only exam transcription, without solving
any question or looking up an answer. Compare every target question with the source
images/native text: complete shared passages, prompt polarity, all five choices in
their original order, underlined spans, mathematical symbols, units, table cells,
diagram relationships, blanks, pronoun references and foreign-script diacritics.
Do not require identical whitespace. Figure descriptions must report visible facts,
not derived values or answer hints. Identify missing or changed information that
could change an answer. Return only JSON {"issues":[{"number":integer,
"field":string,"problem":string}],"checked_numbers":[integers]}. Return an empty
issues list only if no consequential source-fidelity problem is found. Do not
provide or discuss correct answers.'''
PATCH='''Correct only the listed source-fidelity problems in the supplied draft,
using the ORIGINAL source images and native text. Do not solve any question.
Return JSON {"patches":[{"numbers":[question numbers, or empty for all matching questions],
"field":"question|context|visual_description|options.0|options.1|options.2|options.3|options.4",
"old":"exact existing substring","new":"exact corrected source transcription"}],
"uncertainty_updates":[{"number":integer,"uncertainties":[remaining genuinely unreadable details]}]}.
Use long enough old substrings to make the intended correction unambiguous. Preserve
all other content. For a repeated shared-passage typo, apply the same correction to
all questions containing that exact text. A patch may add a missing original mark or
passage; it must not add explanation, derived quantities, clues or answers.'''


def decode(text):
    text=text.strip()
    if text.startswith('```'):
        text=text.split('\n',1)[1].rsplit('```',1)[0]
    # Some literal LaTeX transcriptions contain one slash instead of the two
    # required by JSON. Repair known math commands, never their mathematical text.
    commands='frac|dfrac|tfrac|sqrt|sin|cos|tan|cot|sec|csc|sum|prod|int|log|ln|lim|to|theta|pi|alpha|beta|gamma|delta|epsilon|phi|varphi|psi|omega|rho|tau|sigma|mu|lambda|vec|overline|underline|cdot|times|ldots|cdots|infty|left|right|begin|end|mathrm|mathbf|mathbb|text|leq|geq|neq|le|ge|ne|in|binom|displaystyle|rangle|langle|pm|mp|quad|qquad|circ|perp|parallel|angle|triangle|overrightarrow|overleftrightarrow|widehat|wideparen'
    commands+='|rightarrow|leftarrow|leftrightarrow|Rightarrow|Leftrightarrow|rightleftharpoons|leftrightharpoons|nu|nabla|notin|bar|bmod|boxed|boldsymbol|big|bigg|bigl|bigr|forall|flat|fbox|uparrow|underbrace|underset'
    text=re.sub(r'(?<!\\)\\(?=(?:'+commands+r')(?![A-Za-z]))',r'\\\\',text)
    try:return json.loads(text)
    except json.JSONDecodeError:
        text=re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])',r'\\\\',text)
        return json.loads(text)


def image_path(subject,page):
    return HERE/'images'/subject/f'page-{page:02d}.jpg'


def render(task):
    subject,page=task['subject'],task['page']
    wanted=[page]
    if subject=='korean':
        lo,hi=(1,12) if page<=12 else (13,16) if page<=16 else (17,20)
        wanted=list(range(max(lo,page-1),min(hi,page+1)+1))
    for p in wanted:
        path=image_path(subject,p)
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            subprocess.run(['pdftoppm','-f',str(p),'-l',str(p),'-scale-to','2600',
                            '-jpeg','-jpegopt','quality=93','-singlefile',
                            str(HERE/'sources/exam'/f'{subject}.pdf'),str(path.with_suffix(''))],check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    return wanted


def material(task,pages):
    subject=task['subject']
    native=(HERE/'sources/exam'/f'{subject}.txt').read_text().split('\f')
    if subject=='korean':
        lo,hi=(0,12) if task['page']<=12 else (12,16) if task['page']<=16 else (16,20)
        reference='\n'.join(native[lo:hi])
    else:reference='\n'.join(native[p-1] for p in pages)
    text=f'Current PDF page: {task["page"]}. Target question numbers: {task["targets"]}.\nNative reading aid:\n{reference}'
    if subject=='english':
        script=(HERE/'sources/exam/english-listening-script.txt').read_text().split('\f')
        indices=set(n-1 if n<16 else 15 for n in task['targets'])
        text+='\nOFFICIAL LISTENING SCRIPT: include relevant dialogue in each question context.\n'+'\n'.join(script[i] for i in sorted(indices))
    content=[{'type':'text','text':text}]
    for page in pages:
        content.append({'type':'text','text':f'Source PDF page {page}'+(' (current target page)' if page==task['page'] else ' (context page)')})
        data=base64.b64encode(image_path(subject,page).read_bytes()).decode()
        content.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+data}})
    return content


def call(model,system,content):
    start=time.perf_counter()
    r=requests.post(ENDPOINT,json={'model':model,'reasoning_effort':'low',
        'messages':[{'role':'system','content':system},{'role':'user','content':content}],
        'tools':[],'tool_choice':'none','stream':False},timeout=(10,300))
    r.raise_for_status();raw=r.json()
    traces=HERE/'call-traces';traces.mkdir(exist_ok=True)
    trace_path=traces/f'{uuid4()}.json'
    trace_path.write_text(json.dumps({'model':model,'reasoning_effort':'low','raw_response':raw},ensure_ascii=False,indent=1))
    if raw['choices'][0]['finish_reason']!='stop':raise ValueError('Incomplete transcription')
    parsed=decode(raw['choices'][0]['message']['content'])
    return parsed,{'model':model,'reasoning_effort':'low','usage':raw.get('usage'),
                   'elapsed_seconds':round(time.perf_counter()-start,2),'raw_response':raw,'trace_path':str(trace_path)}


def validate(data,task):
    qs=data['questions']
    assert sorted(q['number'] for q in qs)==sorted(task['targets'])
    for q in qs:
        assert len(q['options'])==5 and all(isinstance(s,str) and s.strip() for s in q['options'])
        assert q['question'].strip() and isinstance(q['context'],str)
        assert isinstance(q['uncertainties'],list)
        assert not any(k in q for k in ['answer','correct_answer','solution'])


def expand_shared(data):
    for q in data['questions']:
        shared=[p['text'] for p in data.get('shared_passages',[]) if q['number'] in p['question_numbers']]
        if shared:q['context']='\n\n'.join([*shared,q['context']]).strip()
    return {'questions':data['questions']}


def apply_patches(data,corrections):
    data=json.loads(json.dumps(data))
    for patch in corrections['patches']:
        matches=0
        for q in data['questions']:
            if patch['numbers'] and q['number'] not in patch['numbers']:continue
            key=patch['field']
            if key.startswith('options.'):
                target=q['options'];field=int(key.split('.')[1]);assert 0<=field<5
            else:
                assert key in ['question','context','visual_description'];target=q;field=key
            old=patch['old'];assert old
            if old in target[field]:
                target[field]=target[field].replace(old,patch['new']);matches+=1
        assert matches,patch
    for update in corrections.get('uncertainty_updates',[]):
        q=next(q for q in data['questions'] if q['number']==update['number'])
        q['uncertainties']=update['uncertainties']
    return data


def process(task):
    name=f'{task["subject"]}-{task["page"]:02d}'
    out=HERE/'transcriptions'/f'{name}.json'
    if out.exists():
        existing=json.loads(out.read_text())
        if existing.get('status') in ['reviewed','human_reviewed','reviewed_with_minor_warnings']:return name,'cached'
    pages=render(task)
    content=material(task,pages)
    record={'task':task,'source_images':[{ 'path':str(image_path(task['subject'],p)),
        'sha256':hashlib.sha256(image_path(task['subject'],p).read_bytes()).hexdigest()} for p in pages],
        'transcription_instructions':INSTRUCTIONS,'review_instructions':REVIEW,'attempts':[]}
    data=None
    if out.exists():
        previous=json.loads(out.read_text())
        if previous.get('questions'):
            data={'questions':previous['questions']}
            record['previous_attempts']=previous.get('previous_attempts',[])+previous.get('attempts',[])
    issues=[]
    for attempt in range(3):
        if data is None:
            raw_data,trace=call(TRANSCRIBER_MODEL,INSTRUCTIONS,content)
            data=expand_shared(raw_data)
        elif issues:
            patch,trace=call(TRANSCRIBER_MODEL,PATCH,content+[{'type':'text','text':'Draft:\n'+json.dumps(data,ensure_ascii=False)+'\nProblems:\n'+json.dumps(issues,ensure_ascii=False)}])
            data=apply_patches(data,patch)
            trace['source_patches']=patch
        else:
            trace={'model':'reuse-existing-draft','elapsed_seconds':0,'usage':{}}
        validate(data,task)
        review,rtrace=call('gpt-5.6-terra',REVIEW,content+[{'type':'text','text':'Transcription to verify:\n'+json.dumps(data,ensure_ascii=False)}])
        assert sorted(review['checked_numbers'])==sorted(task['targets'])
        record['attempts'].append({'transcription':data,'trace':trace,'review':review,'review_trace':rtrace})
        record['questions']=data['questions']
        uncertainties=[{'number':q['number'],'field':'uncertainties','problem':s} for q in data['questions'] for s in q['uncertainties']]
        issues=review['issues']+uncertainties
        record['status']='reviewed' if not issues else 'needs_review'
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(record,ensure_ascii=False,indent=1))
        if not issues:return name,'reviewed'
    return name,'needs_review'


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--subjects',nargs='*');ap.add_argument('--workers',type=int,default=6)
    ap.add_argument('--transcriber-model',choices=['gpt-5.6-sol','gpt-5.6-luna'],default='gpt-5.6-sol')
    ap.add_argument('--reverse',action='store_true');ap.add_argument('--limit',type=int)
    args=ap.parse_args()
    global TRANSCRIBER_MODEL
    TRANSCRIBER_MODEL=args.transcriber_model
    tasks=json.loads((HERE/'page-tasks.json').read_text())
    if args.subjects:tasks=[t for t in tasks if t['subject'] in args.subjects]
    if args.reverse:tasks.reverse()
    if args.limit:tasks=tasks[:args.limit]
    # Render once, sequentially, so adjacent Korean pages do not race writes.
    for task in tasks:render(task)
    print(f'{len(tasks)} pages prepared',flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        pending={pool.submit(process,t):t for t in tasks}
        for i,future in enumerate(as_completed(pending),1):
            task=pending[future]
            try:result=future.result()
            except Exception as e:result=(f'{task["subject"]}-{task["page"]:02d}',type(e).__name__+': '+str(e)[:200])
            print(i,'/',len(tasks),*result,flush=True)


if __name__=='__main__':main()
