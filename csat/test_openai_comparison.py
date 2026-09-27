import json

import pytest

from run_exam import INSTRUCTIONS, make_job
from run_openai_comparison import MODELS, chat_job, parse_choice


def test_identical_problem_and_choices_with_low_and_no_tools():
    q = {'number': 21, 'state': {'question': 'Select', 'passage': 'Text'}, 'options': list('12345')}
    for model in MODELS:
        for rotation in range(5):
            job = chat_job(q, rotation, model)
            req = job['request']
            assert req['reasoning_effort'] == 'low' and req['model'] == model
            assert req['tools'] == [] and req['tool_choice'] == 'none'
            assert req['messages'][0]['content'] == INSTRUCTIONS
            sent = json.loads(req['messages'][1]['content'])
            jev = make_job(q, rotation)
            assert sent['state'] == jev['request']['state']
            assert sent['options'] == jev['request']['questions']['answer']['criteria']
            assert job['choice_to_original'] == jev['choice_to_original']
            assert '21' not in json.dumps(req)


def test_reject_ambiguous_answers_instead_of_guessing():
    assert parse_choice('{"choice":"C"}') == 'C'
    assert parse_choice('```json\n{"choice":"D"}\n```') == 'D'
    for bad in ['A or B', '{"choice":"AB"}', '{"choice":"F"}', '{"choice":"A","alternative":"B"}']:
        with pytest.raises((ValueError, TypeError)):
            parse_choice(bad)
