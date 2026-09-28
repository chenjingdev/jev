"""Verify and report Jev versus the three requested low-effort models."""
import argparse
import hashlib
import json
from pathlib import Path

from run_exam import HERE, grade


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    paths = [HERE / 'results/2026-english-reading-jev-1.13.0.json'] + [
        args.run_dir / f'gpt-5.6-{name}-low.json' for name in ['luna', 'terra', 'sol']]
    results = [json.loads(p.read_text()) for p in paths]
    gold = json.loads((HERE / 'data/2026-english-gold.json').read_text())
    dataset = json.loads((HERE / 'data/2026-english-reading.json').read_text())
    questions = {q['number']: q for q in dataset['questions']}
    expected_hash = hashlib.sha256((HERE / 'data/2026-english-reading.json').read_bytes()).hexdigest()
    reference = {(j['number'], j['rotation']): j for j in results[0]['jobs']}
    for result in results:
        assert result['status'] == 'complete', result['model']
        assert result['dataset_sha256'] == expected_hash
        assert result['summary'] == grade(result['jobs'], gold)
        assert len(result['jobs']) == 140
        assert len({(j['number'], j['rotation']) for j in result['jobs']}) == 140
        for j in result['jobs']:
            assert j['response']['original_option'] == j['choice_to_original'][j['response']['choice']]
            if result.get('reasoning_effort'):
                req = j['request']
                assert req['model'] == result['model'] and req['reasoning_effort'] == 'low'
                assert req['tools'] == [] and req['tool_choice'] == 'none'
                assert len(req['messages']) == 2
                sent = json.loads(req['messages'][1]['content'])
                ref = reference[j['number'], j['rotation']]['request']
                assert sent['state'] == ref['state']
                assert sent['options'] == ref['questions']['answer']['criteria']
                assert req['messages'][0]['content'] == ref['questions']['answer']['instructions']
                assert 'gold' not in sent and 'answer' not in sent['state']

    lines = ['# 수능 영어: Jev · Luna low · Terra low · Sol low', '',
             '동일한 2026학년도 수능 영어 홀수형 독해 18~45번, 28문항을 비교했다. 원래 보기 순서의 첫 답변을 주 점수로 사용했다.', '',
             '| 모델 | 추론 수준 | 정답 | 정답률 | 독해 점수 | 오답 번호 |',
             '|---|---|---:|---:|---:|---|']
    for r in results:
        s = r['summary']
        wrong = ', '.join(map(str, s['primary_wrong_numbers'])) or '없음'
        lines.append(f'| {r["model"]} | {r.get("reasoning_effort", "해당 설정 없음")} | {s["primary_correct"]}/28 | {s["primary_correct"]/28:.1%} | {s["primary_points"]}/63 | {wrong} |')
    lines += ['', '## 보기 배치에 대한 일관성', '',
              '추가로 보기 내용을 네 번 순환 이동하고 A~E를 다시 배정했다. 모든 보기가 모든 위치에 한 번씩 등장한다. 지문 내의 위치·밑줄 참조 표시는 원래 의미를 유지했다. 140회는 28문항의 반복 검사이며 독립된 140문항이 아니다.', '',
              '| 모델 | 5배치에서 같은 답 | 전체 정답/호출 | 모든 배치에서 오답인 문항 |',
              '|---|---:|---:|---|']
    for r in results:
        s = r['summary']
        wrong = ', '.join(map(str, s['all_orders_wrong_questions'])) or '없음'
        lines.append(f'| {r["model"]} | {s["stable_across_five_orders"]}/28 | {s["order_correct"]}/140 | {wrong} |')
    lines += ['', '## 문항별 첫 답', '', '괄호 X는 오답이며 숫자는 원래 문제지의 보기 번호다.', '',
              '| 번호 | 유형 | 정답 | Jev | Luna low | Terra low | Sol low |',
              '|---:|---|---:|---:|---:|---:|---:|']
    per_model = [{d['number']: d for d in r['summary']['details']} for r in results]
    for n in sorted(questions):
        cells = [str(d[n]['primary_pick']) + ('' if d[n]['primary_correct'] else ' (X)') for d in per_model]
        lines.append(f'| {n} | {per_model[0][n]["type"]} | {gold[str(n)]["answer"]} | ' + ' | '.join(cells) + ' |')
    lines += ['', '## 관측 지연 시간', '',
              '한 모델 안에서는 최초 28문항을 순차 호출했다. OpenAI 세 모델은 서로 병렬 실행했다. Jev는 별도 실행의 TypeSafe API, 나머지는 로컬 Codex 프록시 경유이므로 시간에는 네트워크·서비스·추론·클라이언트 차이가 섞여 있다. 모델 자체의 연산 속도만 비교한 표가 아니다.', '',
              '| 모델 | 최초 28문항 경과 시간 | 최초 요청 지연 중앙값 |',
              '|---|---:|---:|']
    for r in results:
        lines.append(f'| {r["model"]} | {r["primary_wall_seconds"]:.2f}초 | {r["summary"]["primary_median_latency_ms"]/1000:.2f}초 |')
    lines += ['', '## 공정성·재현 조건', '',
              '- 네 모델에 동일한 지문·질문·보기 및 공통 문제풀이 지시를 전달했다. 모든 요청의 입력과 보기 매핑을 Jev 실행 기록에 대조했다.',
              '- Luna·Terra·Sol은 정확히 `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`을 요청했고 모두 `reasoning_effort: low`를 보냈다. 다른 모델로 대체하지 않았다.',
              '- 로컬 프록시와 전송 라이브러리 코드를 확인했다. 요청 모델 ID와 low 설정이 상위 API에 전달되며, 이 세 ID에서 low가 다른 수준으로 변환되지 않는다. 최소 실호출도 세 모델 모두 성공했다.',
              '- 모든 문제는 새 메시지 이력으로 전달했다. 도구 목록은 비어 있고 파일·웹 검색·이전 대화·정답 파일은 모델 입력에 없다.',
              '- Jev는 Choice 출력, OpenAI 모델은 같은 후보를 가진 JSON 답 출력이다. 프록시는 JSON schema를 지시문으로 추가하므로 TypeSafe와 동일한 constrained decoding이라고 주장하지 않는다. 형식 오류는 추측해 보정하지 않고 실패로 기록한다.',
              '- 공식 정답표 사본은 응답 수집 후 채점 코드에서만 읽었다. 모델별 정답률을 보고 프롬프트를 변경하거나 재풀이하지 않았다.',
              '- 보기 순환 검사는 선택의 일관성을 보여준다. 같은 배치를 여러 번 반복한 별도 조건은 없으므로, 답이 달라진 경우 순서 영향과 모델 자체의 응답 변동을 완전히 분리하지는 못한다.',
              '- 25번 도표는 텍스트 표로 전사했고, 28번 표·밑줄·빈칸·공통 지문은 원문에 맞게 복원했다. 네 모델에 동일하게 적용했다.',
              '- 듣기 1~17번은 제외했으므로 수능 전체 영어 점수나 등급으로 환산하지 않는다. 공개 기출의 학습 데이터 포함 여부는 알 수 없다. 한 회차의 결과를 모델의 전체 능력 차이로 일반화하지 않는다.',
              '- 프록시 usage의 prompt_tokens는 캐시 토큰을 제외할 수 있다. 원본 응답을 보존했지만 이 수치로 모델 간 요금을 추산하지 않는다.',
              '', '## 출처와 실행 자료', '',
              '- [평가원 출제 문제 PDF 사본](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-english-exam)',
              '- [평가원 정답표 PDF 사본](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-english-answer)',
              '- `csat/run_openai_comparison.py`: 세 모델 실행, low 고정, 독립 요청, 원문 응답 보존.',
              '- `csat/summarize_comparison.py`: 전 모델 입력 대조·재채점·보고서 생성.',
              '- `csat/results/openai-low-preflight.json`: 요청 모델별 최소 호출 확인.',
              f'- `{args.run_dir}`: 각 모델 140회 요청·응답·채점·지연 시간.',
              f'- 입력 문제 파일 SHA-256: `{expected_hash}`.', '']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(lines))
    print('Verified all 560 requests and generated', args.output)
    for r in results:
        s = r['summary']
        print(r['model'],s['primary_correct'],'/28',s['primary_points'],'/63','wrong',s['primary_wrong_numbers'],
              'stable',s['stable_across_five_orders'],'/28','primary_seconds',r['primary_wall_seconds'])


if __name__ == '__main__':
    main()
