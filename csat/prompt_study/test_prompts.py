import copy
from prompts import VARIANTS,build_job,task_type


def fixture():
    return {'id':'fixture:1','number':1,'subject':'physics-1','section':'physics-1',
            'state':{'question':'옳지 않은 것만을 고르시오.','passage':'ㄱ. x. ㄴ. y. ㄷ. z.'},
            'options':['ㄱ','ㄴ','ㄷ','ㄱ, ㄴ','ㄴ, ㄷ']}


def test_only_instructions_change_across_variants():
    q=fixture();jobs=[build_job(q,v) for v in VARIANTS]
    base=copy.deepcopy(jobs[0]['request']);base['questions']['answer'].pop('instructions')
    for j in jobs:
        r=copy.deepcopy(j['request']);r['questions']['answer'].pop('instructions')
        assert r==base
        assert len(j['request']['questions'])==1


def test_prompt_generation_never_uses_gold_or_historical_performance():
    q=fixture();changed=copy.deepcopy(q);changed.update(answer=2,correct=False,previous_answer='D')
    assert [build_job(q,v) for v in VARIANTS]==[build_job(changed,v) for v in VARIANTS]


def test_combination_negative_and_stem_are_distinguished():
    q=fixture();assert task_type(q)==('combination',True)
    q['options']=['1','2','3','4','5'];assert task_type(q)==('stem',True)
    q['state']['question']='값은?';assert task_type(q)==('stem',False)
