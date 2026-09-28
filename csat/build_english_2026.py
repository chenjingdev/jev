"""Extract the odd-form 2026 CSAT English reading questions (18-45).

Uses pdfplumber (bundled document runtime) and pdftotext. Original PDFs remain
unchanged. Layout repairs below were checked against rendered source pages.
Answers and points are saved separately and are never part of model input.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

import pdfplumber

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'sources'
DIGITS = '①②③④⑤'


def clean(text):
    text = text.split('* 확인 사항')[0]
    return '\n'.join(line for line in text.splitlines()
                     if not re.fullmatch(r'\d+|홀수형', line.strip())
                     and not line.startswith('이 문제지에 관한 저작권')).strip()


def compact(text):
    return re.sub(r'\s+', ' ', text).strip()


def options(text):
    parts = re.split(r'([①②③④⑤])', text)
    assert parts[1::2] == list(DIGITS), parts
    return [compact(t) for t in parts[2::2]]


def main():
    columns = []
    with pdfplumber.open(SOURCE / '2026-english.pdf') as pdf:
        for i in range(1, 8):
            page = pdf.pages[i]
            for side, box in [('left', (0, 60, page.width / 2, page.height - 40)),
                              ('right', (page.width / 2, 60, page.width, page.height - 40))]:
                text = page.crop(box).extract_text(x_tolerance=1, y_tolerance=3)
                (SOURCE / f'page-{i+1}-{side}.txt').write_text(text)
                if i > 1 or side == 'right':
                    columns.append(clean(text))
    raw = '\n'.join(columns)
    parts = re.split(r'(?m)^(\d{2})\.\s*', raw)
    blocks = {int(n): t.strip() for n, t in zip(parts[1::2], parts[2::2])}
    assert set(blocks) == set(range(18, 46))
    blocks[40], shared41 = re.split(r'\[41～42\] 다음 글을 읽고, 물음에 답하시오\.\s*', blocks[40])
    blocks[42], shared43 = re.split(r'\[43～45\] 다음 글을 읽고, 물음에 답하시오\.\s*', blocks[42])
    for letter, span in zip('abcde', ['inevitable', 'movement', 'lifeless', 'provide', 'unlikely']):
        pattern = rf'\({letter}\)\s+' + re.escape(span)
        shared41, count = re.subn(pattern, f'({letter}) <u>{span}</u>', shared41)
        assert count == 1
    for letter, span in zip('abcde', ['she', 'his daughter', 'her', 'I', 'she']):
        pattern = rf'\({letter}\)\s+' + r'\s+'.join(map(re.escape, span.split()))
        shared43, count = re.subn(pattern, f'({letter}) <u>{span}</u>', shared43)
        assert count == 1
    for n in (30, 35, 37):
        blocks[n] = blocks[n].split('[' + {30: '31', 35: '36', 37: '38'}[n] + '～')[0].strip()
    questions = []
    for n in range(18, 46):
        block = blocks[n]
        if n in (31, 32, 33, 34):
            prompt, body = '다음 빈칸 [BLANK]에 들어갈 말로 가장 적절한 것을 고르시오.', block
        elif n in (36, 37):
            prompt, body = '주어진 첫 문단 다음에 이어질 (A), (B), (C)의 순서로 가장 적절한 것을 고르시오.', block
        elif n in (38, 39):
            prompt, body = '글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 표시 위치를 고르시오.', block
        else:
            head = 2 if n in (21, 27, 28, 30, 40, 42, 43, 44) else 1
            lines = block.splitlines()
            prompt, body = compact(' '.join(lines[:head])), '\n'.join(lines[head:])
        state = {'question': re.sub(r'\s*\[3점\]', '', prompt)}
        modifications = []
        if n in (29, 30):
            marked = {29: ['to solve', 'being', 'in which', 'motivated', 'greatly'],
                      30: ['absolute', 'justifies', 'keep', 'concern', 'abandon']}[n]
            for digit, word in zip(DIGITS, marked):
                assert f'{digit} {word}' in body
                body = body.replace(f'{digit} {word}', f'{digit} <u>{word}</u>')
            choices = [f'{d} 밑줄 부분: {w}' for d, w in zip(DIGITS, marked)]
            state['passage'] = compact(body)
            modifications.append('Underlined spans restored as <u>...</u> and explicit choice text.')
        elif n == 35:
            state['passage'] = compact(body)
            choices = [f'{d} 문장: {s}' for d, s in zip(DIGITS, options(body[body.index('①'):]))]
        elif n in (38, 39):
            start = 'While stories' if n == 38 else 'A video game'
            given, passage = body.split(start, 1)
            state.update(given_sentence=compact(given), passage=compact(start + passage))
            choices = [f'지문에 표시된 위치 {d}' for d in DIGITS]
            modifications.append('Boxed given sentence separated from the main passage; location markers retained.')
        else:
            pre, opts = body.split('①', 1)
            choices = options('①' + opts)
            if n in (41, 42):
                pre = shared41
                modifications.append('Shared passage retained; exact underlined spans restored.')
            elif n in (43, 44, 45):
                pre = shared43
                modifications.append('Shared A/B/C/D passage retained; exact underlined spans restored, including (b) his daughter.')
            if n == 40:
                pre = pre.replace('(A) (B) (A) (B)', '').replace('󰀻', '\n[요약문]\n')
                modifications.append('Summary arrow replaced by a neutral summary label.')
            state['passage'] = compact(pre)
        if n in (31, 32, 33, 34):
            before, after = {
                31: ('key to their ,', 'key to their [BLANK],'),
                32: ('we have to ;', 'we have to [BLANK];'),
                33: ('if they .', 'if they [BLANK].'),
                34: ('be .', 'be [BLANK].'),
            }[n]
            assert state['passage'].count(before) == 1, (n, state['passage'])
            state['passage'] = state['passage'].replace(before, after)
            modifications.append('Printed blank line restored as [BLANK].')
        if n == 25:
            state['chart'] = {
                'title': 'Percentages of U.S. Teenagers Who Spent Time with Friends by Communication Type (2014-2015)',
                'unit': 'percent',
                'columns': ['Communication type', 'Every Day', 'Less Often'],
                'rows': [['Text Messaging', 55, 13], ['Talking on the Phone', 19, 41],
                         ['Emailing', 6, 43], ['Video Chatting', 7, 37]],
                'notes': ['The number of participants is the same for each communication type.',
                          'Data for other frequency response categories and no answer are not shown.'],
            }
            modifications.append('Chart manually transcribed as data; this measures table reading, not image understanding.')
        if n == 28:
            # Restore the row/column associations of the original three-row table.
            a = state['passage'].index('Pass Type')
            b = state['passage'].index('※ All passes')
            state['passage'] = state['passage'][:a] + 'Pass Type: see pass_table. ' + state['passage'][b:]
            state['pass_table'] = [
                {'type': 'Standard', 'price': '$40', 'details': 'Two free games a day (no discounts for shoe rentals)'},
                {'type': 'Silver', 'price': '$60', 'details': 'Three free games a day + 50% off shoe rentals'},
                {'type': 'Gold', 'price': '$80', 'details': 'Four free games a day + free shoe rentals'},
            ]
            modifications.append('Original pass table restored as explicit rows.')
        assert len(choices) == 5 and all(choices)
        assert state['question'] and state['passage']
        assert '다음 글을 읽고' not in state['passage']
        questions.append({'number': n, 'state': state, 'options': choices, 'format_repairs': modifications})
    answer_text = subprocess.check_output(['pdftotext', '-layout', '-f', '1', '-l', '1',
                                         str(SOURCE / '2026-english-answers.pdf'), '-'], text=True)
    assert '( 홀수 ) 형' in answer_text
    answers = {int(n): {'answer': DIGITS.index(a) + 1, 'points': int(w)}
               for n, a, w in re.findall(r'(\d+)\s+([①②③④⑤])\s+([23])', answer_text)}
    assert set(answers) == set(range(1, 46))
    out = HERE / 'data'
    out.mkdir(exist_ok=True)
    dataset = {'exam': '2026학년도 수능 영어 홀수형 독해', 'question_range': [18, 45],
               'model_input_is_text': True, 'copyright': '한국교육과정평가원',
               'sources': {
                   'exam_pdf': 'https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-english-exam',
                   'answer_pdf': 'https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-english-answer',
                   'official_exam_url_unavailable_404': 'https://cdn.kice.re.kr/suneung-26/suneung-26_3.pdf',
               },
               'source_hashes': {f: hashlib.sha256((SOURCE / f).read_bytes()).hexdigest()
                                 for f in ['2026-english.pdf', '2026-english-answers.pdf']},
               'questions': questions}
    (out / '2026-english-reading.json').write_text(json.dumps(dataset, ensure_ascii=False, indent=2))
    (out / '2026-english-gold.json').write_text(json.dumps(answers, ensure_ascii=False, indent=2))
    print(f'Prepared {len(questions)} questions; maximum reading points: {sum(answers[n]["points"] for n in range(18,46))}')
    for q in questions:
        print(q['number'], q['state']['question'], len(q['state']['passage']), q['options'])


if __name__ == '__main__':
    main()
