"""Paired within-year analysis and predeclared development-only selection."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from prompts import VARIANTS,task_type

HERE=Path(__file__).resolve().parent


def compare(delta,keys):
    groups=defaultdict(list)
    for d,k in zip(delta,keys):groups[k].append(d)
    totals=np.array([[sum(ds),len(ds)] for ds in groups.values()])
    ix=np.random.default_rng(20260923).integers(0,len(totals),(50000,len(totals)))
    samples=totals[ix].sum(axis=1);estimates=samples[:,0]/samples[:,1]
    better=sum(d>0 for d in delta);worse=sum(d<0 for d in delta);n=better+worse
    p=min(1,2*sum(math.comb(n,k) for k in range(min(better,worse)+1))/2**n) if n else 1.0
    return {'improved':better,'worsened':worse,'net':better-worse,'difference':float(np.mean(delta)),
            'page_cluster_ci95':np.quantile(estimates,[.025,.975]).tolist(),
            'page_clusters':len(groups),'mcnemar_exact_p_descriptive':p}


def analyze(path,dataset_path,gold_path):
    manifest=json.loads((path/'manifest.json').read_text());assert manifest['status']=='complete'
    raw=dataset_path.read_bytes();assert manifest['dataset_sha256']==hashlib.sha256(raw).hexdigest()
    data=json.loads(raw);questions=data['questions'];gold_raw=gold_path.read_bytes()
    assert manifest['gold_sha256']==hashlib.sha256(gold_raw).hexdigest()
    gold=json.loads(gold_raw)
    records={};out={};keys=[(q['subject'],q.get('source_page',q['id'])) for q in questions]
    for variant in manifest['variants']:
        rows=[json.loads((path/variant/(q['id'].replace(':','-')+'.json')).read_text()) for q in questions]
        assert all(r['status']=='complete' for r in rows)
        records[variant]=rows
        correct=[int(r['job']['response']['original_option']==gold[r['id']]['answer']) for r in rows]
        subjects={}
        for subject in sorted({q['subject'] for q in questions}):
            ids=[i for i,q in enumerate(questions) if q['subject']==subject]
            subjects[subject]={'correct':sum(correct[i] for i in ids),'n':len(ids)}
        out[variant]={'correct':sum(correct),'n':len(rows),'accuracy':sum(correct)/len(rows),
                      'input_tokens':sum(r['job']['response']['usage']['input_tokens'] for r in rows),
                      'subjects':subjects}
        if variant=='baseline':baseline=correct
        else:
            for base,new in zip(records['baseline'],rows):
                a=json.loads(json.dumps(base['job']['request']));b=json.loads(json.dumps(new['job']['request']))
                del a['questions']['answer']['instructions'];del b['questions']['answer']['instructions']
                assert a==b,'A non-prompt input changed'
            out[variant]['vs_baseline']=compare([a-b for a,b in zip(correct,baseline)],keys)
    return manifest,out,records,questions


def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['select','report']);args=ap.parse_args()
    dev_manifest,dev,dev_rows,questions=analyze(HERE/'development',HERE.parent/'all_subjects/dataset.json',HERE.parent/'all_subjects/gold.json')
    if args.phase=='select':
        candidates=[v for v in VARIANTS if v!='baseline']
        selected=min(candidates,key=lambda v:(-dev[v]['correct'],dev[v]['input_tokens'],candidates.index(v)))
        result={'created_at':datetime.now(timezone.utc).isoformat(),'chosen_variant':selected,
                'prompts_sha256':dev_manifest['prompts_sha256'],'development':dev,
                'rule':'Highest development accuracy, then fewer input tokens, then fixed candidate order. Validation outcomes were not used.'}
        with (HERE/'selection.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    selection=json.loads((HERE/'selection.json').read_text());winner=selection['chosen_variant']
    vm,val,_,_=analyze(HERE/'validation_results',HERE/'validation_2025/dataset.json',HERE/'validation_2025/gold.json')
    assert vm['prompts_sha256']==selection['prompts_sha256']==dev_manifest['prompts_sha256']
    assert vm['variants']==['baseline',winner]
    old=json.loads((HERE.parent/'all_subjects/summary.json').read_text())
    old_answers={a['id']:a['selected'] for a in old['answers'] if a['model']=='jev-1.13.0'}
    same=sum(r['job']['response']['original_option']==old_answers[r['id']] for r in dev_rows['baseline'])
    result={'selection':selection,'development':dev,'validation':val,'repeat_control':{'old_correct':619,'fresh_correct':dev['baseline']['correct'],'same_answer':same,'n':884}}
    (HERE/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    labels={'baseline':'기존 범용 문구','direct_ko':'실제 질문 직접 제시','structured_ko':'유형별 한국어 지시','structured_en':'유형별 영어 지시'}
    lines=['# Jev 프롬프트 개선 시험','',
           '이번 세 가지 문구 변형에서는 큰 성능 향상을 확인하지 못했다. 최고 후보는 두 회차에서 각각 4문항 더 맞혔지만, 두 정확도 차이의 보조 신뢰구간 모두 0을 포함한다. 작은 개선 가능성은 남아 있으나 안정적인 개선으로 단정할 근거는 부족하다.','',
           '**개선 전후는 항상 같은 연도·같은 문항으로 비교했다.** 2026년 884문항에서 후보를 선택하고, 2025년 128문항에서 기존 문구와 선택된 후보를 함께 시험했다. 연도가 다른 점수를 서로 빼지 않는다.','',
           '## 2026학년도 동일 884문항 비교','','| 조건 | 정답 | 정확도 | 기존 대비 |','|---|---:|---:|---:|']
    for v,r in dev.items():lines.append(f'| {labels[v]} | {r["correct"]}/884 | {r["accuracy"]:.1%} | {r["correct"]-dev["baseline"]["correct"]:+d}문항 |')
    lines += ['',f'기존 프롬프트의 이전 실행은 619개 정답, 이번 재실행은 {dev["baseline"]["correct"]}개 정답이었다. 답 자체는 {same}/884문항에서 같았다.',
              '',f'개발 결과만으로 선택한 후보는 **{labels[winner]}**다. 선택 후 지시문을 수정하지 않았다.',
              '', '## 2025학년도 동일 128문항 추가 검증','','| 조건 | 정답 | 정확도 |','|---|---:|---:|']
    dc=dev[winner]['vs_baseline'];dlo,dhi=dc['page_cluster_ci95']
    lines[-4:-4]=[f'선택 후보는 기존 오답 {dc["improved"]}개를 맞히고 기존 정답 {dc["worsened"]}개를 틀렸다. 순변화 {dc["net"]:+d}개, 정확도 차이 {dc["difference"]*100:+.2f}%p다. 페이지 단위 bootstrap 95% 구간은 [{dlo*100:+.2f}, {dhi*100:+.2f}]%p로 0을 포함한다.','']
    for v,r in val.items():lines.append(f'| {labels[v]} | {r["correct"]}/128 | {r["accuracy"]:.1%} |')
    c=val[winner]['vs_baseline'];lo,hi=c['page_cluster_ci95']
    lines += ['',f'기존 오답을 맞힌 문항 {c["improved"]}개, 기존 정답을 틀린 문항 {c["worsened"]}개, 순변화 {c["net"]:+d}개다. 정확도 차이는 {c["difference"]*100:+.2f}%p, 원문 페이지 단위 bootstrap 95% 구간은 [{lo*100:+.2f}, {hi*100:+.2f}]%p다.',
              '', '## 검증 과목별','','| 과목 | 문항 | 기존 | 선택 후보 |','|---|---:|---:|---:|']
    subject_names={'chemistry-1':'화학Ⅰ','english':'영어 독해','korean-history':'한국사','life-ethics':'생활과 윤리','physics-1':'물리학Ⅰ','politics-law':'정치와 법'}
    for subject,r in val['baseline']['subjects'].items():lines.append(f'| {subject_names.get(subject,subject)} | {r["n"]} | {r["correct"]} | {val[winner]["subjects"][subject]["correct"]} |')
    ratio=val[winner]['input_tokens']/val['baseline']['input_tokens']
    lines += ['', '## 조건과 한계','',
              '- 모델은 Jev 1.13.0이다. 지문·그림 전사·보기·보기 순서가 모든 조건에서 정확히 같은지 코드로 확인했다. 변경한 것은 Choice의 instructions뿐이다.',
              '- 각 문항·각 조건은 Choice 한 개를 담은 요청 한 번이다. 별도 진술 판정, 상위 2개 재질문, 외부 풀이, 정답 예시는 사용하지 않았다.',
              f'- 호출 수는 같지만 입력 토큰은 다르다. 검증에서 선택 후보의 입력 토큰은 기준선의 {ratio:.3f}배였다.',
              '- 2026년 자료는 이미 결과를 분석한 개발 자료이므로 그 상승분만으로 일반화 개선을 주장하지 않는다. 2025년은 사전에 고정한 6과목이며 전과목을 대표하는 확정치가 아니다.',
              '- 검증용 문제도 텍스트 변환본이다. 전사 오류·시각 정보의 언어화와 공개 기출의 학습 포함 가능성이라는 한계가 남는다.',
              '- Bootstrap은 같은 원문 페이지의 문항을 함께 재표집한 보조 구간이다. 프롬프트 후보 선택에 따른 개발 점수의 낙관성을 없애는 검증은 별도 회차 비교가 담당한다.',
              '', '실행 전 규칙: `PROTOCOL.md`. 고정 지시문: `prompts.py`. 선택 기록: `selection.json`. 모든 원본 요청·응답은 `development/`와 `validation_results/`에 보존했다.','']
    audit=HERE/'input_audit/findings.json'
    if audit.exists():
        lines[2:2]=['**입력 검증 정정:** 2026학년도 물리학Ⅰ 10번·화학Ⅰ 3번·한국지리 1번에서 원본과 다른 그림 설명이 확인됐다. 점수는 해당 오류를 포함한 당시 실행 기록이며, 충실한 수능 입력에서의 성능으로 일반화할 수 없다. [실제 입력과 대조 근거](input_audit/README.md).','']
    (HERE/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps({'development':{v:r['correct'] for v,r in dev.items()},'winner':winner,'validation':{v:r['correct'] for v,r in val.items()},'paired_validation':c},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
