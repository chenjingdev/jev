import json
from pathlib import Path

from prepare_manifest import section
from transcribe import decode

HERE=Path(__file__).resolve().parent


def test_objective_manifest_excludes_short_answer_and_duplicate_common_questions():
    gold=json.loads((HERE/'gold.json').read_text())
    assert len(gold)==884
    math=[g for g in gold.values() if g['subject']=='math']
    assert len(math)==33
    assert all(g['number']<=15 or 23<=g['number']<=28 for g in math)
    assert sum(g['section']=='korean-common' for g in gold.values())==34
    assert sum(g['section']=='math-common' for g in gold.values())==15
    assert sum(g['subject']=='hanja-1' for g in gold.values())==30


def test_elective_boundaries_have_separate_ids():
    assert section('korean',12)=='korean-common'
    assert section('korean',13)=='korean-speech'
    assert section('korean',17)=='korean-language'
    assert section('math',9)=='math-probability'
    assert section('math',13)=='math-calculus'
    assert section('math',17)=='math-geometry'


def test_lab_step_five_is_not_misclassified_as_question_five():
    tasks=json.loads((HERE/'page-tasks.json').read_text())
    first=next(t for t in tasks if t['subject']=='agriculture' and t['page']==1)
    second=next(t for t in tasks if t['subject']=='agriculture' and t['page']==2)
    assert first['targets']==[1,2,3,4]
    assert 5 in second['targets']


def test_math_json_repair_preserves_literal_formula_and_real_newlines():
    assert decode(r'{"formula":"\frac{1}{2}"}')['formula']==r'\frac{1}{2}'
    assert decode(r'{"formula":"\\frac{1}{2}"}')['formula']==r'\frac{1}{2}'
    assert decode(r'{"text":"first\nThen"}')['text']=='first\nThen'
    assert decode(r'{"formula":"1\times10^{-14}"}')['formula']==r'1\times10^{-14}'
