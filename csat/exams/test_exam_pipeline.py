import json
from pathlib import Path
import re

import pytest

import exam_pipeline as ep

EXAM = ep.Exam('2027-09')


def _load(name):
    return json.loads(EXAM.path(name).read_text())


def test_sections_are_read_from_the_exam_headers():
    korean = ep.page_sections(EXAM, 'korean')
    assert korean[11] == 'korean-common' and korean[12] == 'korean-speech'
    assert korean[15] == 'korean-speech' and korean[16] == 'korean-language'
    math = ep.page_sections(EXAM, 'math')
    assert math[7] == 'math-common' and math[8] == 'math-probability'
    assert math[12] == 'math-calculus' and math[16] == 'math-geometry'


def test_gold_counts_and_short_answer_exclusion():
    gold = _load('gold.json')
    summary = _load('manifest-summary.json')
    tasks = _load('page-tasks.json')
    assert summary['objective_questions'] == len(gold) == sum(len(t['targets']) for t in tasks)
    assert sorted(summary['short_answer_excluded']) == [16, 17, 18, 19, 20, 21, 22, 29, 29, 29, 30, 30, 30]
    math = [g for g in gold.values() if g['subject'] == 'math']
    assert all(g['number'] <= 15 or 23 <= g['number'] <= 28 for g in math)
    assert sum(g['section'] == 'korean-common' for g in gold.values()) == 34
    assert sum(g['section'] == 'english' for g in gold.values()) == 45
    assert all(1 <= g['answer'] <= 5 for g in gold.values())


def test_agriculture_lab_steps_do_not_steal_question_numbers():
    tasks = _load('page-tasks.json')
    first = next(t for t in tasks if t['subject'] == 'agriculture' and t['page'] == 1)
    second = next(t for t in tasks if t['subject'] == 'agriculture' and t['page'] == 2)
    assert first['targets'] == [1, 2, 3, 4] and second['targets'][0] == 5


def test_every_english_question_including_reading_is_transcribed_here():
    tasks = _load('page-tasks.json')
    numbers = sorted(n for t in tasks if t['subject'] == 'english' for n in t['targets'])
    assert numbers == list(range(1, 46))


def test_listening_script_page_mapping():
    script = EXAM.path('sources/exam/english-listening-script.txt').read_text().split('\f')
    assert ep.script_pages(1, script) == [0] and ep.script_pages(15, script) == [14]
    assert ep.script_pages(16, script) == [15] and ep.script_pages(17, script) == [15, 16]
    assert '16' in script[15] and '17.' in script[16]


def test_dataset_matches_gold_ids_without_answers():
    path = EXAM.path('dataset.json')
    if not path.exists(): pytest.skip('dataset not built yet')
    data = json.loads(path.read_text())
    gold = _load('gold.json')
    ids = [q['id'] for q in data['questions']]
    assert len(ids) == len(set(ids)) and set(ids) <= set(gold)
    assert data['expected_objective_questions'] == len(gold)
    assert (data['status'] == 'complete') == (set(ids) == set(gold))
    for q in data['questions']:
        assert not {'answer', 'correct_answer', 'solution', 'points'} & set(q)
        assert q['quality_status'] in ep.OK_STATUSES and len(q['options']) == 5


def test_transcription_requests_never_mention_answer_keys():
    for path in EXAM.path('transcriptions').glob('*.json') if EXAM.path('transcriptions').exists() else []:
        record = json.loads(path.read_text())
        assert 'answer' not in json.dumps(record['task'])
        for attempt in record.get('attempts', []):
            for q in attempt['transcription']['questions']:
                assert not {'answer', 'correct_answer', 'solution'} & set(q)


def test_transcription_request_material_contains_no_answer_key_text():
    tasks = _load('page-tasks.json')
    for task in tasks:
        pages = ep.context_pages(EXAM, task)
        if not all(ep.image_path(EXAM, task['subject'], p).exists() for p in pages): pytest.skip('images not rendered')
        text = '\n'.join(c['text'] for c in ep.material(EXAM, task, pages) if c['type'] == 'text')
        assert '정답표' not in text and not re.search(r'정답\s+배점', text)


def test_human_review_entries_are_applied_to_transcriptions():
    folder = EXAM.path('human-review')
    if not folder.exists(): pytest.skip('no human review')
    for path in folder.glob('*.json'):
        entry = json.loads(path.read_text())
        record = json.loads(EXAM.path('transcriptions', f'{entry["page"]}.json').read_text())
        assert record['status'] == entry['status'], entry['page']
        assert record['human_review']['finding'] == entry['finding'], entry['page']
