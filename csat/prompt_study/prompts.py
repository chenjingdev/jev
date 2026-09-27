"""Frozen one-Choice prompt variants. State and answer options are unchanged."""
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_exam import INSTRUCTIONS as BASELINE, make_job

VARIANTS=['baseline','direct_ko','structured_ko','structured_en']
STEM_PREFIXES=('math','physics','chemistry','biology','earth-science')
LANGUAGES={'korean','english','arabic-1','chinese-1','french-1','german-1','hanja-1','japanese-1','russian-1','spanish-1','vietnamese-1'}


def task_type(q):
    prompt=re.sub('<[^>]*>','',q['state']['question'])
    combination=all(re.fullmatch(r'[ㄱㄴㄷㄹㅁ\s,·ㆍ()]+',o) for o in q['options'])
    negative=bool(re.search(r'옳지|적절하지|일치하지|않은|아닌|틀린|관계 없는',prompt))
    if combination:kind='combination'
    elif q['subject'].startswith(STEM_PREFIXES):kind='stem'
    elif q['subject'] in LANGUAGES:kind='language'
    else:kind='knowledge'
    return kind,negative


KO_RULES={
 'combination':'ㄱ·ㄴ·ㄷ·ㄹ 등 각 진술이 주어진 조건에서 성립하는지 구분한다. 질문이 요구하는 참 또는 거짓 진술을 모두 포함하고, 해당하지 않는 진술은 포함하지 않는 조합을 고른다.',
 'stem':'수식, 수치, 단위, 부호, 지수와 분모·분자를 정확히 해석하고 필요한 교과 법칙을 적용한다. 조건 전체를 만족하는 계산 결과 또는 설명을 고른다.',
 'language':'지문·대화·문장 간 관계와 해당 언어의 어휘·문법을 근거로 판단한다. 부분적으로 관련 있는 보기보다 질문의 범위와 지문 전체에 가장 잘 맞는 보기를 고른다.',
 'knowledge':'주어진 자료와 해당 과목의 배경지식을 함께 적용한다. 인물·시대·개념·조건을 구분하고 보기의 주장 전체가 맞는지 판단한다.',
}
EN_RULES={
 'combination':'Evaluate each labelled statement (ㄱ, ㄴ, ㄷ, ㄹ, etc.) under the given conditions. Select the combination that includes all and only the true or false statements requested by the actual question.',
 'stem':'Read formulas, values, units, signs, powers, numerators and denominators accurately. Apply the relevant subject laws and select the result or explanation satisfying all stated conditions.',
 'language':'Use the passage, dialogue, relationships between sentences, and the language\'s vocabulary and grammar. Prefer the option that best matches the whole relevant context and the scope of the question, rather than one that is only partly related.',
 'knowledge':'Apply the supplied material together with relevant subject knowledge. Distinguish people, periods, concepts and conditions, and evaluate the entire claim made by each option.',
}


def instructions(q,variant):
    if variant=='baseline':return BASELINE
    actual=q['state']['question']
    if variant=='direct_ko':
        return actual+'\n\n제시된 지문·자료와 필요한 교과 지식을 바탕으로 이 질문의 정답인 선택지 하나를 고르세요.'
    kind,negative=task_type(q)
    if variant=='structured_ko':
        return {'실제_질문':actual,'판단_대상':['passage','visual_description','그 밖의 제공 자료','선택지'],
                '선택_조건':('질문이 요구하는 틀리거나 맞지 않는 항목을 고른다.' if negative else '실제 질문이 요구하는 가장 적절한 항목을 고른다.'),
                '판단_기준':KO_RULES[kind],
                '참조_표시':'지문 안의 ①~⑤와 (a)~(e)는 원문 위치·밑줄 표시이며, 답은 현재 선택지 키 A~E로 고른다.'}
    if variant=='structured_en':
        return {'actual_question':actual,'evidence_fields':['passage','visual_description','other supplied material','answer options'],
                'selection_rule':('Select the incorrect or nonmatching item requested by the question.' if negative else 'Select the item best satisfying the actual question.'),
                'decision_criteria':EN_RULES[kind],
                'reference_markers':'Markers ①-⑤ or (a)-(e) inside the passage refer to source positions or underlined spans. Choose the corresponding current option key A-E.'}
    raise ValueError(variant)


def build_job(q,variant):
    job=make_job(q,0)
    job['id']=q['id'];job['variant']=variant
    job['request']['questions']['answer']['instructions']=instructions(q,variant)
    return job
