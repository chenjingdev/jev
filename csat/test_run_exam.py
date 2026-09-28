import copy
import json
from pathlib import Path

from run_exam import grade, make_job

HERE = Path(__file__).resolve().parent


def test_all_options_visit_every_display_slot_and_are_graded_by_content():
    q = {'number': 18, 'state': {'question': 'Select'}, 'options': ['one', 'two', 'three', 'four', 'five']}
    jobs = [make_job(q, r) for r in range(5)]
    for n in range(1, 6):
        assert {k for j in jobs for k, v in j['choice_to_original'].items() if v == n} == set('ABCDE')
    for j in jobs:
        chosen = next(k for k, n in j['choice_to_original'].items() if n == 2)
        j['response'] = {'choice': chosen, 'original_option': 2, 'confidence': .9, 'latency_ms': 100,
                         'usage': {'input_tokens': 10, 'output_tokens': 10}}
    s = grade(jobs, {'18': {'answer': 2, 'points': 3}})
    assert (s['questions'], s['primary_correct'], s['primary_points'], s['order_correct']) == (1, 1, 3, 5)
    assert s['stable_across_five_orders'] == 1


def test_gold_and_exam_metadata_never_affect_request():
    q = {'number': 18, 'state': {'question': 'Select'}, 'options': ['a', 'b', 'c', 'd', 'e']}
    a = make_job(q, 0)['request']
    changed = copy.deepcopy(q)
    changed.update(answer=5, points=3, explanation='hidden', number=99, exam_year=2026)
    assert a == make_job(changed, 0)['request']


def test_dataset_has_complete_shared_passages_underlines_blanks_and_chart():
    dataset = json.loads((HERE / 'data/2026-english-reading.json').read_text())
    qs = {q['number']: q for q in dataset['questions']}
    assert set(qs) == set(range(18, 46))
    assert all(len(q['options']) == 5 and all(q['options']) for q in qs.values())
    for n in range(31, 35):
        assert qs[n]['state']['passage'].count('[BLANK]') == 1
    assert qs[41]['state']['passage'] == qs[42]['state']['passage']
    assert qs[43]['state']['passage'] == qs[44]['state']['passage'] == qs[45]['state']['passage']
    assert '(b) <u>his daughter</u>' in qs[44]['state']['passage']
    assert all(f'({k})' in qs[43]['state']['passage'] for k in 'ABCD')
    assert qs[25]['state']['chart']['rows'] == [['Text Messaging',55,13],['Talking on the Phone',19,41],['Emailing',6,43],['Video Chatting',7,37]]
    assert [r['type'] for r in qs[28]['state']['pass_table']] == ['Standard', 'Silver', 'Gold']
    assert all(qs[n]['state']['given_sentence'] for n in (38, 39))
