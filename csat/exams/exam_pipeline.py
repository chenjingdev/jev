"""Exam-parameterized version of the csat/all_subjects pipeline.

Usage: python csat/exams/exam_pipeline.py <exam-dir-name> fetch|manifest|transcribe|build

Per-exam settings live in csat/exams/<exam>/config.json. Prompts and pure helpers
(decode/validate/expand_shared/apply_patches) are imported unchanged from the
2026 reference so the transcription protocol is identical; nothing here writes
into csat/all_subjects. Answer keys are parsed only in `manifest`, into gold.json;
transcription requests never read gold.json or answer PDFs.
"""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

import requests

EXAMS = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMS.parent / 'all_subjects'))
import transcribe as ref  # noqa: E402  (2026 reference: prompts + pure helpers)
from fetch_sources import NAMES  # noqa: E402

decode, validate, expand_shared, apply_patches = ref.decode, ref.validate, ref.expand_shared, ref.apply_patches
INSTRUCTIONS, REVIEW, PATCH = ref.INSTRUCTIONS, ref.REVIEW, ref.PATCH
ENDPOINT = ref.ENDPOINT
DIGITS = '①②③④⑤'
OK_STATUSES = ['reviewed', 'reviewed_with_minor_warnings', 'human_reviewed']
KOREAN_SECTIONS = {'화법과 작문': 'korean-speech', '언어와 매체': 'korean-language'}
MATH_SECTIONS = {'확률과 통계': 'math-probability', '미적분': 'math-calculus', '기하': 'math-geometry'}


class Exam:
    def __init__(self, name):
        self.dir = EXAMS / name
        self.cfg = json.loads((self.dir / 'config.json').read_text())
        self.id = self.cfg['exam_id']  # e.g. 2027-09

    def path(self, *parts):
        return self.dir.joinpath(*parts)

    def exam_text(self, subject):
        return self.path('sources/exam', f'{subject}.txt').read_text().split('\f')


# ---------------------------------------------------------------- fetch

def _download(exam, job):
    subject, kind, url = job
    folder = exam.path('sources', kind)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{subject}.pdf'
    final_url = None
    if not path.exists():
        r = requests.get(url, timeout=120, allow_redirects=True)
        r.raise_for_status()
        assert r.content.startswith(b'%PDF'), (subject, kind, r.headers.get('Content-Type'))
        final_url = r.url
        path.write_bytes(r.content)
        path.with_suffix('.source.txt').write_text(f'{url}\n{final_url}\n')
    else:
        src = path.with_suffix('.source.txt')
        final_url = src.read_text().split('\n')[1] if src.exists() else None
    subprocess.run(['pdftotext', '-layout', str(path), str(path.with_suffix('.txt'))], check=True)
    info = subprocess.check_output(['pdfinfo', str(path)], text=True)
    return {'subject': subject, 'name': NAMES.get(subject, subject), 'kind': kind, 'url': url,
            'resolved_url': final_url, 'path': str(path.relative_to(exam.dir)),
            'pages': int(re.search(r'^Pages:\s+(\d+)', info, re.M)[1]),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def fetch(exam):
    cfg = exam.cfg
    page = requests.get(cfg['index_url'], timeout=30)
    page.raise_for_status()
    links = set(html.unescape(x) for x in re.findall(r'href="([^"]*api/mock-exams/file[^"]+)"', page.text))
    ids = sorted(set(re.sub(r'.*id=', '', x) for x in links))
    assert len(ids) == cfg['expected_index_files'], len(ids)
    jobs = []
    for subject in NAMES:
        for kind in ['exam', 'answer']:
            route = f'/api/mock-exams/file?id={cfg["haksi_prefix"]}-{subject}-{kind}'
            assert route in links, route
            jobs.append((subject, kind, 'https://www.haksi.kr' + route))
    covered = {f'{cfg["haksi_prefix"]}-{s}-{k}' for s, k, _ in jobs}
    extra = sorted(set(ids) - covered)
    records = []
    with ThreadPoolExecutor(6) as pool:
        for i, f in enumerate(as_completed([pool.submit(_download, exam, j) for j in jobs]), 1):
            records.append(f.result())
            print(f'{i}/{len(jobs)} sources ready', flush=True)
    # Official listening script (KICE board); the haksi listening file is audio only.
    ls = cfg['listening_script']
    records.append(_download(exam, ('english-listening-script', 'exam', ls['url'])))
    audio = cfg.get('listening_audio')
    audio_record = None
    if audio:
        r = requests.get(audio['url'], timeout=300)
        r.raise_for_status()
        assert r.content.startswith(b'PK'), 'listening audio is expected to be a zip'
        audio_record = {'url': audio['url'], 'resolved_url': r.url, 'bytes': len(r.content),
                        'sha256': hashlib.sha256(r.content).hexdigest(),
                        'note': 'Audio only (mp3 zip); not stored. Text input uses the official script.'}
    manifest = {'exam_id': exam.id, 'exam_name': cfg['exam_name'], 'index_url': cfg['index_url'],
                'forms': cfg.get('forms', 'Use odd form where two forms are present; retain all electives.'),
                'excluded': 'All numeric short-answer mathematics questions.',
                'index_files_not_downloaded_as_pdf': extra,
                'listening_script_page': ls.get('board_page'), 'listening_audio': audio_record,
                'records': sorted(records, key=lambda r: (r['subject'], r['kind']))}
    exam.path('source-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    for r in manifest['records']:
        if r['kind'] == 'exam': print(r['subject'], r['name'], r['pages'])


# ---------------------------------------------------------------- manifest

def page_sections(exam, subject):
    """Section per page, derived from the elective headers printed on each page."""
    pages = exam.exam_text(subject)
    if pages and not pages[-1].strip(): pages = pages[:-1]
    keys = KOREAN_SECTIONS if subject == 'korean' else MATH_SECTIONS if subject == 'math' else None
    if keys is None: return [subject] * len(pages)
    common = f'{subject}-common'
    out = []
    for text in pages:
        head = text[:800]
        found = [sec for label, sec in keys.items() if label in head]
        assert len(found) <= 1, (subject, found)
        out.append(found[0] if found else common)
    # Each section must occupy one contiguous block, common first.
    order = [s for i, s in enumerate(out) if i == 0 or out[i - 1] != s]
    assert len(order) == len(set(order)) and order[0] == common, (subject, out)
    assert order[1:] == list(keys.values()), (subject, order)
    return out


def parse_gold(exam):
    gold, short_answer = {}, []
    for subject in NAMES:
        text = exam.path('sources/answer', f'{subject}.txt').read_text().split('\f')[0]
        text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        for line in text.splitlines():
            triples = [(int(n), DIGITS.index(a) + 1, int(w)) for n, a, w in
                       re.findall(r'(\d{1,2})\s+([①②③④⑤])\s+([1-4])\b', line)]
            if subject == 'math':
                short_answer += [int(n) for n, _ in re.findall(r'(?:^|\s)(\d{1,2})\s+(\d{1,3})\s+[1-4]\b', line)]
            elective_index = 0
            for number, answer, points in triples:
                sec = subject
                if subject == 'korean':
                    if number < 35: sec = 'korean-common'
                    else:
                        sec = list(KOREAN_SECTIONS.values())[elective_index]; elective_index += 1
                elif subject == 'math':
                    if number <= 15 and elective_index == 0: sec = 'math-common'
                    elif 23 <= number <= 28:
                        sec = list(MATH_SECTIONS.values())[elective_index]; elective_index += 1
                    else: raise AssertionError((subject, number))
                qid = f'{sec}:{number}'
                assert qid not in gold, qid
                gold[qid] = {'answer': answer, 'points': points, 'subject': subject, 'section': sec, 'number': number}
    return gold, short_answer


def question_numbers(subject, text):
    if subject == 'arabic-1':
        visible = re.sub('[‪-‮⁦-⁩]', '', text)
        return sorted(set(int(n) for n in re.findall(r'(\d{1,2})\.\s*', visible)))
    return sorted(set(int(n) for n in re.findall(r'(?:^|\s{3,})(\d{1,2})\.\s', text, re.M)))


SET_HEADER = re.compile(r'\[\s*(\d{1,2})\s*[~～∼〜-]\s*(\d{1,2})\s*\]')


def manifest(exam):
    gold, short_answer = parse_gold(exam)
    overrides = exam.cfg.get('page_number_overrides', {})  # "subject:page" -> numbers to drop
    tasks, ownership = [], {}
    next_number = {sec: min(g['number'] for g in gold.values() if g['section'] == sec)
                   for sec in {g['section'] for g in gold.values()}}
    for subject in NAMES:
        pages = exam.exam_text(subject)
        sections = page_sections(exam, subject)
        set_pages = {}  # question number -> page of its [a~b] set header
        for page, text in enumerate(pages[:len(sections)], 1):
            for a, b in SET_HEADER.findall(text):
                for n in range(int(a), int(b) + 1): set_pages.setdefault((sections[page - 1], n), page)
        for page, text in enumerate(pages[:len(sections)], 1):
            sec = sections[page - 1]
            numbers = question_numbers(subject, text)
            drop = overrides.get(f'{subject}:{page}', {}).get('drop', [])
            numbers = [n for n in numbers if n not in drop]
            targets = []
            n = next_number[sec]
            while n in numbers and f'{sec}:{n}' in gold:
                targets.append(n); n += 1
            next_number[sec] = n
            if not targets: continue
            for n in targets:
                qid = f'{sec}:{n}'
                assert qid not in ownership, (qid, page, ownership.get(qid))
                ownership[qid] = page
            header_pages = sorted({set_pages[(sec, n)] for n in targets
                                   if (sec, n) in set_pages and set_pages[(sec, n)] < page})
            task = {'subject': subject, 'name': NAMES[subject], 'section': sec, 'page': page, 'targets': targets}
            if header_pages: task['set_header_pages'] = header_pages
            tasks.append(task)
    missing = set(gold) - set(ownership)
    assert not missing, sorted(missing)
    exam.path('gold.json').write_text(json.dumps(gold, ensure_ascii=False, indent=2))
    exam.path('page-tasks.json').write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    summary = {'objective_questions': len(gold), 'short_answer_excluded': sorted(short_answer),
               'page_tasks': len(tasks)}
    exam.path('manifest-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Objective questions:', len(gold), 'short-answer excluded:', len(short_answer),
          'page tasks:', len(tasks))


# ---------------------------------------------------------------- transcribe

def image_path(exam, subject, page):
    return exam.path('images', subject, f'page-{page:02d}.jpg')


def context_pages(exam, task):
    subject, page = task['subject'], task['page']
    wanted = {page, *task.get('set_header_pages', [])}
    if subject == 'korean':  # same adjacent-page rule as 2026, bounded by the section block
        sections = page_sections(exam, subject)
        block = [i for i, s in enumerate(sections, 1) if s == task['section']]
        wanted |= {p for p in (page - 1, page + 1) if p in block}
    if wanted != {page}:
        wanted = set(range(min(wanted), max(wanted) + 1))
    return sorted(wanted)


def render(exam, task):
    subject = task['subject']
    wanted = context_pages(exam, task)
    for p in wanted:
        path = image_path(exam, subject, p)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            subprocess.run(['pdftoppm', '-f', str(p), '-l', str(p), '-scale-to', '2600',
                            '-jpeg', '-jpegopt', 'quality=93', '-singlefile',
                            str(exam.path('sources/exam', f'{subject}.pdf')), str(path.with_suffix(''))],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return wanted


def script_pages(n, script):
    """Official listening script: one page per question 1-15, 16-17 share page 16;
    page 17 repeats only the question-17 prompt."""
    if n < 16: return [n - 1]
    return [15] + ([16] if n == 17 and len(script) > 16 and script[16].strip() else [])


def material(exam, task, pages):
    subject = task['subject']
    native = exam.exam_text(subject)
    if subject == 'korean':
        sections = page_sections(exam, subject)
        block = [i for i, s in enumerate(sections) if s == task['section']]
        reference = '\n'.join(native[block[0]:block[-1] + 1])
    else: reference = '\n'.join(native[p - 1] for p in pages)
    text = f'Current PDF page: {task["page"]}. Target question numbers: {task["targets"]}.\nNative reading aid:\n{reference}'
    listening = [n for n in task['targets'] if n <= 17] if subject == 'english' else []
    if listening:
        script = exam.path('sources/exam/english-listening-script.txt').read_text().split('\f')
        indices = sorted({i for n in listening for i in script_pages(n, script)})
        text += '\nOFFICIAL LISTENING SCRIPT: include relevant dialogue in each question context.\n' + '\n'.join(script[i] for i in indices)
    content = [{'type': 'text', 'text': text}]
    for page in pages:
        content.append({'type': 'text', 'text': f'Source PDF page {page}' + (' (current target page)' if page == task['page'] else ' (context page)')})
        data = base64.b64encode(image_path(exam, subject, page).read_bytes()).decode()
        content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + data}})
    return content


def call(exam, model, system, content):
    start = time.perf_counter()
    for attempt in range(3):  # transport failures only; same request
        try:
            r = requests.post(ENDPOINT, json={'model': model, 'reasoning_effort': 'low',
                'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}],
                'tools': [], 'tool_choice': 'none', 'stream': False}, timeout=(10, 600))
            r.raise_for_status(); break
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == 2: raise
            time.sleep(10 * (attempt + 1))
    raw = r.json()
    traces = exam.path('call-traces'); traces.mkdir(exist_ok=True)
    trace_path = traces / f'{uuid4()}.json'
    trace_path.write_text(json.dumps({'model': model, 'reasoning_effort': 'low', 'raw_response': raw}, ensure_ascii=False, indent=1))
    if raw['choices'][0]['finish_reason'] != 'stop': raise ValueError('Incomplete transcription')
    parsed = decode(raw['choices'][0]['message']['content'])
    return parsed, {'model': model, 'reasoning_effort': 'low', 'usage': raw.get('usage'),
                    'elapsed_seconds': round(time.perf_counter() - start, 2), 'raw_response': raw, 'trace_path': str(trace_path)}


def record_name(task):
    return f'{task["subject"]}-{task["page"]:02d}'


def process(exam, task, transcriber):
    name = record_name(task)
    out = exam.path('transcriptions', f'{name}.json')
    if out.exists():
        existing = json.loads(out.read_text())
        if existing.get('status') in OK_STATUSES: return name, 'cached'
    pages = render(exam, task)
    content = material(exam, task, pages)
    record = {'task': task, 'source_images': [{'path': str(image_path(exam, task['subject'], p)),
        'sha256': hashlib.sha256(image_path(exam, task['subject'], p).read_bytes()).hexdigest()} for p in pages],
        'transcription_instructions': INSTRUCTIONS, 'review_instructions': REVIEW, 'attempts': []}
    data = None
    if out.exists():
        previous = json.loads(out.read_text())
        if previous.get('questions'):
            data = {'questions': previous['questions']}
            record['previous_attempts'] = previous.get('previous_attempts', []) + previous.get('attempts', [])
            for key in ('human_review', 'page_boundary_repair'):
                if key in previous: record[key] = previous[key]
    issues = []
    for attempt in range(3):
        if data is None:
            raw_data, trace = call(exam, transcriber, INSTRUCTIONS, content)
            data = expand_shared(raw_data)
        elif issues:
            patch, trace = call(exam, transcriber, PATCH, content + [{'type': 'text', 'text': 'Draft:\n' + json.dumps(data, ensure_ascii=False) + '\nProblems:\n' + json.dumps(issues, ensure_ascii=False)}])
            data = apply_patches(data, patch)
            trace['source_patches'] = patch
        else:
            trace = {'model': 'reuse-existing-draft', 'elapsed_seconds': 0, 'usage': {}}
        validate(data, task)
        review, rtrace = call(exam, 'gpt-5.6-terra', REVIEW, content + [{'type': 'text', 'text': 'Transcription to verify:\n' + json.dumps(data, ensure_ascii=False)}])
        assert sorted(review['checked_numbers']) == sorted(task['targets'])
        record['attempts'].append({'transcription': data, 'trace': trace, 'review': review, 'review_trace': rtrace})
        record['questions'] = data['questions']
        uncertainties = [{'number': q['number'], 'field': 'uncertainties', 'problem': s} for q in data['questions'] for s in q['uncertainties']]
        issues = review['issues'] + uncertainties
        record['status'] = 'reviewed' if not issues else 'needs_review'
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(record, ensure_ascii=False, indent=1))
        if not issues: return name, 'reviewed'
    return name, 'needs_review'


def transcribe(exam, args):
    tasks = json.loads(exam.path('page-tasks.json').read_text())
    if args.subjects: tasks = [t for t in tasks if t['subject'] in args.subjects]
    if args.pages: tasks = [t for t in tasks if record_name(t) in args.pages]
    if args.limit: tasks = tasks[:args.limit]
    for task in tasks: render(exam, task)  # sequential: adjacent pages must not race
    print(f'{len(tasks)} pages prepared', flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        pending = {pool.submit(process, exam, t, args.transcriber_model): t for t in tasks}
        for i, future in enumerate(as_completed(pending), 1):
            task = pending[future]
            try: result = future.result()
            except Exception as e: result = (record_name(task), type(e).__name__ + ': ' + str(e)[:200])
            print(i, '/', len(tasks), *result, flush=True)


# ---------------------------------------------------------------- build

def build(exam, require_complete=False):
    """Assemble only source-reviewed text stimuli; never loads gold answers."""
    tasks = json.loads(exam.path('page-tasks.json').read_text())
    expected = sum(len(t['targets']) for t in tasks)
    short = json.loads(exam.path('manifest-summary.json').read_text())['short_answer_excluded']
    items, pending = [], []
    for task in tasks:
        file = exam.path('transcriptions', f'{record_name(task)}.json')
        if not file.exists(): pending.append({'task': task, 'status': 'missing'}); continue
        try: record = json.loads(file.read_text())
        except json.JSONDecodeError: pending.append({'task': task, 'status': 'being_written'}); continue
        if record['status'] not in OK_STATUSES:
            pending.append({'task': task, 'status': record['status']}); continue
        assert sorted(q['number'] for q in record['questions']) == task['targets']
        for q in record['questions']:
            options = [(f'원문에 표시된 {s.strip()}' if s.strip() in '①②③④⑤' and len(s.strip()) == 1
                        else re.sub(r'^\s*[①②③④⑤]\s*', '', s).strip()) for s in q['options']]
            assert len(options) == 5 and all(options)
            state = {'question': q['question'], 'passage': q['context']}
            if q['visual_description']: state['visual_description'] = q['visual_description']
            visible = '\n'.join([*state.values(), *options])
            assert not re.search('[\x08\x0c]|\t(?:heta|imes|ext)|\r(?:ight|ho|angle)', visible), (task, q['number'], 'corrupt math escape')
            items.append({'id': f'{task["section"]}:{q["number"]}', 'subject': task['subject'],
                          'subject_name': NAMES[task['subject']], 'section': task['section'], 'number': q['number'],
                          'state': state, 'options': options, 'has_visual': q['has_visual'],
                          'quality_status': record['status'], 'source_page': task['page'],
                          'source_record_sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                          'source_record': str(file), 'warnings': q['uncertainties']})
    assert len({q['id'] for q in items}) == len(items)
    for q in items:
        if q['subject'] == 'math': assert q['number'] <= 15 or 23 <= q['number'] <= 28
    payload = {'exam_id': exam.id, 'exam_name': exam.cfg['exam_name'],
               'status': 'complete' if len(items) == expected else 'partial', 'expected_objective_questions': expected,
               'short_answer_excluded': len(short),
               'comparison_mode': 'Text-only adapted input, original option order, one independent question call per model.',
               'questions': sorted(items, key=lambda q: (q['section'], q['number'])), 'pending_pages': pending}
    path = exam.path('dataset.json'); tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1)); tmp.replace(path)
    print(f'{len(items)}/{expected} reviewed inputs assembled; {len(pending)} pages pending')
    if require_complete: assert payload['status'] == 'complete'


# ---------------------------------------------------------------- human review

def human_review(exam):
    """Apply manual source-image checks recorded in human-review/<page>.json.

    Each entry: {"page": "subject-NN", "status": "human_reviewed"|"reviewed_with_minor_warnings",
    "finding": str, "scope": str, "edits": [{"number", "field", "old", "new"}],
    "uncertainties": {number: [remaining warnings]}}. Edits are literal source
    corrections made by reading the page image; they never use the answer key.
    """
    reviews = [json.loads(p.read_text()) for p in sorted(exam.path('human-review').glob('*.json'))]
    for entry in reviews:
        path = exam.path('transcriptions', f'{entry["page"]}.json')
        record = json.loads(path.read_text())
        if record.get('human_review', {}).get('finding') == entry['finding'] and record['status'] == entry['status']:
            continue
        questions = {q['number']: q for q in record['questions']}
        for edit in entry.get('edits', []):
            q = questions[edit['number']]
            field = edit['field']
            if field.startswith('options.'):
                target, key = q['options'], int(field.split('.')[1])
            else:
                assert field in ('question', 'context', 'visual_description'); target, key = q, field
            assert edit['old'] in target[key], (entry['page'], edit)
            target[key] = target[key].replace(edit['old'], edit['new'])
        for number, warnings in entry.get('uncertainties', {}).items():
            questions[int(number)]['uncertainties'] = warnings
        if entry['status'] == 'human_reviewed':
            assert all(not q['uncertainties'] for q in record['questions']), entry['page']
        record['human_review'] = {'finding': entry['finding'], 'scope': entry.get('scope', ''),
                                  'source_image': f'images/{record["task"]["subject"]}/page-{record["task"]["page"]:02d}.jpg',
                                  'edits': entry.get('edits', [])}
        record['status'] = entry['status']
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
        print(entry['page'], entry['status'], len(entry.get('edits', [])), 'edits')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('exam', help='directory name under csat/exams, e.g. 2027-09')
    ap.add_argument('step', choices=['fetch', 'manifest', 'transcribe', 'human-review', 'build'])
    ap.add_argument('--subjects', nargs='*'); ap.add_argument('--pages', nargs='*')
    ap.add_argument('--workers', type=int, default=6); ap.add_argument('--limit', type=int)
    ap.add_argument('--transcriber-model', choices=['gpt-5.6-sol', 'gpt-5.6-luna'], default='gpt-5.6-sol')
    ap.add_argument('--require-complete', action='store_true')
    args = ap.parse_args()
    exam = Exam(args.exam)
    if args.step == 'fetch': fetch(exam)
    elif args.step == 'manifest': manifest(exam)
    elif args.step == 'transcribe': transcribe(exam, args)
    elif args.step == 'human-review': human_review(exam)
    else: build(exam, args.require_complete)


if __name__ == '__main__': main()
