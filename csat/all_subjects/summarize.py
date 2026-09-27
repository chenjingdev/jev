"""Verify finished runs against frozen input and grade objective questions only."""
import csv
import hashlib
import json
from pathlib import Path
import sys
from collections import defaultdict

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_exam import make_job
from run_openai_comparison import chat_job
from run_benchmark import ALL_MODELS,request_hash
from fetch_sources import HERE,NAMES


def main():
    data=json.loads((HERE/'dataset.json').read_text())
    assert data['status']=='complete' and len(data['questions'])==884
    gold=json.loads((HERE/'gold.json').read_text())
    answers=[]
    retries=[]
    for q in data['questions']:
        assert q['id'] in gold
        for model in ALL_MODELS:
            job=make_job(q,0) if model=='jev-1.13.0' else chat_job(q,0,model)
            digest=request_hash(job)
            path=HERE/'results'/model/f'{q["id"].replace(":","-")}-{digest[:12]}.json'
            assert path.exists(),(q['id'],model,'not run')
            result=json.loads(path.read_text())
            if len(result.get('attempts',[]))>1 or result.get('previous_attempts'):
                retries.append({'model':model,'id':q['id'],'attempts':len(result.get('attempts',[])),
                                'previous_attempts':len(result.get('previous_attempts',[])),
                                'errors':[a.get('error_type') for a in result.get('attempts',[]) if a.get('error_type')]})
            assert result['request_sha256']==digest
            assert result['job']['request']==job['request']
            assert result['status'] in ['complete','invalid_answer'],(q['id'],model,result['status'])
            if model!='jev-1.13.0':assert result['job']['request']['reasoning_effort']=='low'
            response=result['job'].get('response')
            selected=response['original_option'] if response else None
            g=gold[q['id']]
            answers.append({'id':q['id'],'subject':q['subject'],'section':q['section'],
                            'number':q['number'],'model':model,'selected':selected,'answer':g['answer'],
                            'correct':selected==g['answer'],'points':g['points'],
                            'has_visual':q['has_visual'],'quality_status':q['quality_status'],
                            'result_path':str(path)})
    sections=defaultdict(lambda:defaultdict(list))
    for a in answers:sections[a['section']][a['model']].append(a)
    def summarize(rows):
        return {'n':len(rows),'correct':sum(r['correct'] for r in rows),
                'points':sum(r['points'] for r in rows if r['correct']),
                'max_points':sum(r['points'] for r in rows),
                'wrong':[r['number'] for r in rows if not r['correct']]}
    totals={m:summarize([a for a in answers if a['model']==m]) for m in ALL_MODELS}
    visual_subsets={label:{m:summarize([a for a in answers if a['model']==m and a['has_visual']==flag])
                           for m in ALL_MODELS} for label,flag in [('without_visual_description',False),('with_visual_description',True)]}
    per_section={s:{m:summarize(rows) for m,rows in ms.items()} for s,ms in sections.items()}
    record={'dataset_sha256':hashlib.sha256((HERE/'dataset.json').read_bytes()).hexdigest(),
            'gold_sha256':hashlib.sha256((HERE/'gold.json').read_bytes()).hexdigest(),
            'totals':totals,'sections':per_section,'visual_subsets':visual_subsets,'transport_retries':retries,'answers':answers}
    (HERE/'summary.json').write_text(json.dumps(record,ensure_ascii=False,indent=1))
    with (HERE/'answers.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(answers[0]));writer.writeheader();writer.writerows(answers)
    names={**NAMES,'korean-common':'국어 공통','korean-speech':'화법과 작문 선택','korean-language':'언어와 매체 선택',
           'math-common':'수학 공통 객관식','math-probability':'확률과 통계 선택 객관식',
           'math-calculus':'미적분 선택 객관식','math-geometry':'기하 선택 객관식'}
    lines=['# 2026 수능 전과목 객관식 — 텍스트 변환 비교','',
           '수학 단답형 13개와 공통 문항 중복을 제외한 884문항을 비교했다. 네 모델 모두 동일한 텍스트 입력을 받았고 Luna·Terra·Sol은 low다. 그림은 전사·설명으로, 듣기는 대본으로 변환했다. 원본 시각·청각 능력을 측정한 시험이 아니다.','',
           '| 모델 | 정답 / 884 | 정답률 |','|---|---:|---:|']
    for m,s in totals.items():lines.append(f'| {m} | {s["correct"]}/884 | {s["correct"]/884:.1%} |')
    lines+=['','## 그림 전사 여부별 결과','','`has_visual`은 전사 단계에서 그림이 있다고 표시한 문항을 뜻하며, 그림이 정답에 필수인지까지 구분한 표시는 아니다.','',
            '| 입력 구분 | 문항 수 | Jev | Luna low | Terra low | Sol low |','|---|---:|---:|---:|---:|---:|']
    for label,ms in visual_subsets.items():
        name='그림 전사 표시 없음' if label=='without_visual_description' else '그림 전사 표시 있음'
        lines.append(f'| {name} | {ms[ALL_MODELS[0]]["n"]} | '+' | '.join(str(ms[m]['correct']) for m in ALL_MODELS)+' |')
    lines+=['','## 과목별 객관식 정답 수','','공통과 선택 문항을 분리하여 중복 없이 집계했다. 영어 45문항에는 대본으로 푼 듣기 17문항이 포함된다.','',
            '| 구분 | 문항 수 | Jev | Luna low | Terra low | Sol low |','|---|---:|---:|---:|---:|---:|']
    for section,ms in per_section.items():
        lines.append(f'| {names[section]} | {ms[ALL_MODELS[0]]["n"]} | '+' | '.join(str(ms[m]['correct']) for m in ALL_MODELS)+' |')
    lines+=['','## 해석과 검증','','- 원래 보기 순서의 최초 정상 수신 답을 사용했다. 기존 영어 독해 28문항은 동일한 요청의 기존 결과를 재사용했다.',
            '- Sol의 생명과학Ⅱ 20번에서 150초 수신 시간 초과가 한 번 발생해 동일 요청으로 재시도했다. 정답률을 보고 재풀이한 것은 아니다. 최종 응답 누락과 답안 형식 오류는 0건이다.',
            '- 정답·배점은 별도 정답표에서 채점했다. 전사·검수·풀이 API 요청에 정답표나 이전 모델 답을 주지 않았다.',
            '- Sol low 중심의 전사와 Terra low의 원문 대조를 거친 입력이다. 일부 전사 시범은 Luna low를 사용했다. 전처리 모델의 오류와 그림의 언어화가 난이도에 영향을 줄 수 있으므로 원래 수능과 동일한 조건으로 간주하면 안 된다.',
            '- 작은 그림 내부 문자 등 사소한 미판독은 경고로 보존했다. 중요 전사 문제는 수정 후 입력했다. 자동 검수 통과가 원문과 완벽히 동일함을 보장하지는 않는다.',
            '- 공개 기출의 학습 데이터 포함 여부는 알 수 없다. 한 회차 결과를 일반 능력이나 실제 수능 등급으로 일반화하지 않는다.',
            '- 정확한 원문·전사·검수·각 요청과 응답·해시는 이 폴더에 보존했다. 원본 문제의 저작권은 한국교육과정평가원에 있다.',
            '', '원문 배포: [2026학년도 문제·정답 PDF 사본 모음](https://www.haksi.kr/exams/2026/11).',
            '', '세부 답안: `answers.csv`, 기계 판독 결과: `summary.json`, 실행 규칙: `PROTOCOL.md`.','']
    (HERE/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(totals,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
