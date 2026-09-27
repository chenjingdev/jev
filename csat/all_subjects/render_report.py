"""Create an offline, filterable comparison report without reproducing question text."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    result=json.loads((HERE/'summary.json').read_text())
    dataset=json.loads((HERE/'dataset.json').read_text())
    questions={q['id']:q for q in dataset['questions']}
    names={q['section']:q['subject_name'] for q in dataset['questions']}
    names.update({'korean-common':'국어 · 공통','korean-speech':'국어 · 화법과 작문','korean-language':'국어 · 언어와 매체',
                  'math-common':'수학 · 공통 객관식','math-probability':'수학 · 확률과 통계','math-calculus':'수학 · 미적분','math-geometry':'수학 · 기하'})
    models=list(result['totals'])
    data={'models':models,'sections':[], 'answers':[]}
    social={'east-asia-history','economics','ethics-thought','korean-geography','life-ethics','politics-law','social-culture','world-geography','world-history'}
    science={'biology-1','biology-2','chemistry-1','chemistry-2','earth-science-1','earth-science-2','physics-1','physics-2'}
    vocational={'agriculture','commerce-economics','fishery-maritime','human-development','industrial-general','successful-career'}
    for sec,stats in result['sections'].items():
        subject=next(q['subject'] for q in dataset['questions'] if q['section']==sec)
        group='주요 영역' if subject in ['korean','math','english','korean-history'] else '사회탐구' if subject in social else '과학탐구' if subject in science else '직업탐구' if subject in vocational else '제2외국어·한문'
        data['sections'].append({'id':sec,'name':names[sec],'group':group,'stats':stats})
    for a in result['answers']:
        q=questions[a['id']]
        page=q.get('source_page')
        if page is None and q['subject']=='english':page=2 if q['number']<=20 else 3 if q['number']<=24 else 4 if q['number']<=28 else 5 if q['number']<=32 else 6 if q['number']<=36 else 7 if q['number']<=40 else 8
        data['answers'].append({k:a[k] for k in ['id','section','number','model','selected','answer','correct','has_visual']}|
                              {'url':f'https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-{q["subject"]}-exam#page={page}'})
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>수능 전과목 · 모델 비교</title><style>
:root{color-scheme:light;--ink:#182329;--muted:#58666d;--line:#dce2e2;--paper:#f5f6f2;--accent:#245d54}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}main{max-width:1180px;margin:auto;padding:40px 24px 70px}.eyebrow{font-size:12px;font-weight:700;letter-spacing:.15em;color:var(--accent)}h1{font-size:34px;margin:12px 0}p{line-height:1.65}.lead{max-width:900px;color:var(--muted);margin:0 0 24px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{background:white;padding:20px;border:1px solid var(--line);border-radius:10px}.card .model{font-size:13px;color:var(--muted)}.card .score{font-size:32px;font-weight:750;margin:10px 0 5px}.card small{color:var(--muted)}.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:26px 0 12px}select,input{font:inherit;border:1px solid var(--line);background:white;border-radius:6px;padding:10px 12px}input{flex:1;min-width:180px}.hint{font-size:13px;color:var(--muted)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:white}table{width:100%;border-collapse:collapse;font-size:14px;white-space:nowrap}th,td{padding:12px 16px;text-align:left;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);background:#eef1ed;position:sticky;top:0}td:nth-child(n+3){min-width:130px}.cell{border:0;background:none;text-align:left;font:inherit;cursor:pointer;width:100%;padding:0}.cell strong{font-weight:700}.bar{height:4px;background:#edf0eb;border-radius:3px;margin-top:6px}.bar i{display:block;height:4px;border-radius:3px;background:var(--accent)}.detail{background:white;border:1px solid var(--line);border-radius:10px;padding:22px;margin-top:22px}.detail h2{font-size:18px;margin:0 0 8px}.wrong-list{display:flex;gap:10px;flex-wrap:wrap}.wrong{border:1px solid var(--line);border-radius:6px;padding:10px 12px;min-width:180px}.wrong a{font-weight:700;color:var(--accent)}.wrong small{display:block;color:var(--muted);margin-top:6px}.notes{font-size:13px;color:var(--muted);border-top:1px solid var(--line);margin-top:26px;padding-top:18px}.tag{display:inline-block;border:1px solid #c1d4cc;padding:3px 8px;border-radius:20px;font-size:12px;margin-right:8px;color:var(--accent)}a{color:var(--accent)}@media(max-width:760px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:25px 14px}h1{font-size:27px}}
</style><main><div class="eyebrow">2026 CSAT · OBJECTIVE QUESTIONS</div><h1>수능 전과목 모델 비교</h1>
<p class="lead"><span class="tag">객관식 884문항</span><span class="tag">수학 단답형 제외</span><span class="tag">GPT 모델 모두 low</span><br>네 모델에 같은 텍스트 전사본을 제공했습니다. 그림은 설명으로, 듣기는 공식 대본으로 변환한 예비 시험입니다. 공통 문항은 한 번만 집계합니다.</p>
<div id="cards" class="cards"></div><div class="controls"><select id="group" aria-label="영역"><option>전체</option><option>주요 영역</option><option>사회탐구</option><option>과학탐구</option><option>직업탐구</option><option>제2외국어·한문</option></select><input id="search" placeholder="과목 찾기" aria-label="과목 찾기"><span id="count" class="hint"></span></div>
<p class="hint">과목별 모델 점수를 누르면 오답 번호와 원문 링크를 볼 수 있습니다.</p><div class="table-wrap"><table><thead><tr><th>과목·구성</th><th>문항</th><th>Jev 1.13.0</th><th>Luna low</th><th>Terra low</th><th>Sol low</th></tr></thead><tbody id="rows"></tbody></table></div>
<section class="detail" id="detail"><h2>오답 확인</h2><p class="hint">위 표에서 과목과 모델을 선택하세요.</p></section>
<div class="notes"><p>원래 보기 순서의 첫 답변을 채점했습니다. 기존 영어 독해 28문항은 동일 입력의 기존 결과를 재사용했습니다. 국어·수학은 공통과 선택 문항을 분리했으며, 영어에는 대본으로 푼 듣기 17문항이 포함됩니다.</p><p>생성 모델의 전사 및 자동·수동 원문 대조를 거친 자료입니다. 시각 정보의 언어화와 전사 오류가 난이도에 영향을 줄 수 있고, 공개 기출의 학습 데이터 포함 여부는 확인하지 못했습니다. 원본 수능과 동일한 조건이나 수능 등급으로 해석하지 마세요.</p><p><a href="REPORT.md">상세 보고서</a> · <a href="answers.csv">문항별 CSV</a> · <a href="https://www.haksi.kr/exams/2026/11" target="_blank" rel="noreferrer">원문 PDF 사본 모음</a></p></div></main>
<script>const DATA=__DATA__;
const displayNames=['Jev 1.13.0','GPT-5.6 Luna · low','GPT-5.6 Terra · low','GPT-5.6 Sol · low'];
function el(tag,text,cls){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;}
function showDetails(sec,model){const box=document.getElementById('detail');box.replaceChildren(el('h2',sec.name+' · '+displayNames[DATA.models.indexOf(model)]));const wrong=DATA.answers.filter(a=>a.section===sec.id&&a.model===model&&!a.correct);if(!wrong.length){box.append(el('p','오답 없음','hint'));return;}const list=el('div',undefined,'wrong-list');for(const a of wrong){const item=el('div',undefined,'wrong');const link=el('a',a.number+'번 원문');link.href=a.url;link.target='_blank';link.rel='noreferrer';item.append(link,el('small','정답 '+a.answer+' · 모델 답 '+(a.selected??'형식 오류')));if(a.has_visual)item.append(el('small','그림·표 전사 포함'));list.append(item);}box.append(list);box.scrollIntoView({behavior:'smooth',block:'nearest'});}
function render(){const group=document.getElementById('group').value;const search=document.getElementById('search').value.trim().toLowerCase();const selected=DATA.sections.filter(s=>(group==='전체'||s.group===group)&&s.name.toLowerCase().includes(search));const n=selected.reduce((sum,s)=>sum+s.stats[DATA.models[0]].n,0);document.getElementById('count').textContent=selected.length+'개 구성 · '+n+'문항';const cards=document.getElementById('cards');cards.replaceChildren();for(let i=0;i<DATA.models.length;i++){const model=DATA.models[i];const correct=selected.reduce((sum,s)=>sum+s.stats[model].correct,0);const card=el('div',undefined,'card');card.append(el('div',displayNames[i],'model'),el('div',n?(100*correct/n).toFixed(1)+'%':'—','score'),el('small',correct+' / '+n+' 정답'));cards.append(card);}const rows=document.getElementById('rows');rows.replaceChildren();for(const sec of selected){const row=el('tr');row.append(el('td',sec.name),el('td',sec.stats[DATA.models[0]].n));for(const model of DATA.models){const stats=sec.stats[model];const td=el('td');const button=el('button',undefined,'cell');button.title='오답 번호와 원문 보기';button.append(el('strong',stats.correct+' / '+stats.n));const bar=el('div',undefined,'bar');const fill=el('i');fill.style.width=(100*stats.correct/stats.n)+'%';bar.append(fill);button.append(bar);button.onclick=()=>showDetails(sec,model);td.append(button);row.append(td);}rows.append(row);}}
document.getElementById('group').onchange=render;document.getElementById('search').oninput=render;render();</script></html>'''
    html=html.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    (HERE/'report.html').write_text(html)
    print(HERE/'report.html')


if __name__=='__main__':main()
