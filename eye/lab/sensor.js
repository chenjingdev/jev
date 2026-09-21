import {mountWorkspace} from '/workspace.js';

const $ = id => document.getElementById(id);
let mode = 'fixture', input = null, sourceUrl = null, scene = null;
let busy = false, live = false, revision = 0, observedRevision = -1, pendingTimer;

function message(text, error = false) {
  $('stage').textContent = text;
  $('stage').className = error ? 'error' : '';
}
function controls() {
  $('analyze').disabled = busy;
  $('analyze').textContent = busy ? '분석 중…' : mode === 'fixture' ? '현재 화면 분석' : '이미지 분석';
  $('live').hidden = mode !== 'fixture';
  $('live').textContent = live ? '센서 중지' : '센서 시작';
  $('live').setAttribute('aria-pressed', String(live));
  $('fixture').hidden = mode === 'fixture';
}
function clearResult() {
  scene = null;
  $('fixture-boxes').replaceChildren();
  $('image-boxes').replaceChildren();
  $('elements').replaceChildren();
  $('selected').textContent = '분석 후 요소를 선택하세요.';
  $('raw').textContent = '아직 출력이 없습니다.';
  $('download').disabled = true;
}
function schedule() {
  clearTimeout(pendingTimer);
  if (live && mode === 'fixture' && !busy && observedRevision !== revision)
    pendingTimer = setTimeout(analyze, 300);
}
function changed() {
  if (mode !== 'fixture') return;
  revision++;
  clearResult();
  $('summary').textContent = '화면이 바뀌었습니다.';
  if (!busy) message(live ? '새 화면 관찰 대기…' : '현재 화면 분석 또는 센서 시작을 누르세요.');
  schedule();
}
mountWorkspace($('canvas'), $('workspace-controls'), changed);

async function load(blob, name) {
  if (blob.size > 20 * 1024 * 1024) throw Error('20 MB 이하의 이미지를 넣어 주세요.');
  const url = URL.createObjectURL(blob), probe = new Image();
  probe.src = url;
  try { await probe.decode(); }
  catch { URL.revokeObjectURL(url); throw Error('이미지를 읽을 수 없습니다.'); }
  live = false;
  clearTimeout(pendingTimer);
  mode = 'image'; revision++;
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  sourceUrl = url; input = blob;
  $('image').src = url;
  $('workspace').hidden = true; $('image-wrap').hidden = false;
  $('source-title').textContent = name;
  $('source-hint').textContent = '입력한 이미지의 픽셀을 분석합니다.';
  $('dimensions').textContent = `${probe.naturalWidth} × ${probe.naturalHeight}`;
  clearResult(); controls();
  $('summary').textContent = '분석 준비됨'; message('이미지 분석을 누르세요.');
}
function select(id) {
  const item = scene?.elements.find(e => e.id === id);
  if (!item) return;
  $('selected').textContent = JSON.stringify(item, null, 2);
  for (const r of document.querySelectorAll('svg rect')) r.classList.toggle('selected', r.dataset.id === id);
  for (const b of $('elements').children) b.classList.toggle('active', b.dataset.id === id);
}
function render() {
  const boxes = $(mode === 'fixture' ? 'fixture-boxes' : 'image-boxes');
  boxes.replaceChildren(); $('elements').replaceChildren();
  if (!scene) return;
  const query = $('filter').value.toLowerCase();
  boxes.setAttribute('viewBox', `0 0 ${scene.image.width} ${scene.image.height}`);
  for (const e of scene.elements) {
    if (!`${e.id} ${e.type} ${e.text || ''} ${e.description || ''}`.toLowerCase().includes(query)) continue;
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    ['x', 'y', 'width', 'height'].forEach((k, i) => r.setAttribute(k, e.box[i]));
    r.dataset.id = e.id; r.setAttribute('class', e.type === 'text' ? 'text' : ''); boxes.append(r);
    const b = document.createElement('button');
    b.dataset.id = e.id; b.textContent = `${e.id} · ${e.type}`;
    const label = document.createElement('span'); label.textContent = e.text || e.description || '글자·설명 없음';
    b.append(label); b.onclick = () => select(e.id); $('elements').append(b);
  }
}
async function analyze() {
  if (busy) return;
  clearTimeout(pendingTimer);
  const capturedRevision = revision;
  busy = true; controls(); message('현재 픽셀 읽는 중…');
  let timer;
  try {
    // Only the visible canvas bitmap crosses the model boundary; no fixture state or DOM data.
    const blob = mode === 'fixture'
      ? await new Promise(resolve => $('canvas').toBlob(resolve, 'image/png')) : input;
    if (!blob) throw Error('입력 이미지를 읽지 못했습니다.');
    timer = setInterval(async () => {
      try { const r = await fetch('/api/status'); const s = await r.json(); if (busy) message(s.message); } catch {}
    }, 400);
    const response = await fetch('/api/analyze', {
      method: 'POST', headers: {'Content-Type': blob.type || 'image/png', 'X-Jev-Sensor': '1'}, body: blob,
    });
    const body = await response.json();
    if (!response.ok) throw Error(body.error || '분석하지 못했습니다.');
    // Never paint an old frame's detections over a newer screen.
    if (capturedRevision !== revision) {
      message(live ? '바뀐 화면을 다시 관찰합니다…' : '화면이 바뀌었습니다. 다시 분석해 주세요.');
      return;
    }
    scene = body.scene; observedRevision = capturedRevision;
    const m = scene.metadata, t = m.timings;
    const tiling = m.tiling?.enabled ? ` · 타일 ${m.tiling.tile_count}개` : '';
    $('summary').textContent = `${scene.elements.length}개 요소 · ${m.captioned_elements}/${m.caption_candidates}개 아이콘 설명${tiling}\n${m.ocr.backend} · ${m.device}\n탐지 ${t.detect_s.toFixed(2)}초 · OCR ${t.ocr_s.toFixed(2)}초\n설명 ${t.caption_s.toFixed(2)}초 · 전체 ${body.elapsed_s.toFixed(2)}초`;
    $('raw').textContent = JSON.stringify(scene, null, 2); $('download').disabled = false;
    $('selected').textContent = '요소를 선택하면 좌표·글자·모델 근거가 나옵니다.';
    render(); message(live ? '관찰 완료 · 화면이 바뀌면 다시 읽습니다.' : '인식 완료');
  } catch (e) {
    live = false; message(e.message, true);
  } finally {
    clearInterval(timer); busy = false; controls(); schedule();
  }
}
$('live').onclick = () => {
  live = !live; controls();
  if (live) { if (!busy) analyze(); }
  else { clearTimeout(pendingTimer); message(busy ? '현재 분석 완료 후 관찰을 멈춥니다.' : '센서를 멈췄습니다.'); }
};
$('analyze').onclick = analyze;
$('fixture').onclick = () => {
  mode = 'fixture'; revision++; clearResult();
  $('workspace').hidden = false; $('image-wrap').hidden = true;
  $('source-title').textContent = '직접 조작하는 테스트 화면';
  $('source-hint').textContent = '검색, 즐겨찾기, 문서 열기, 설정을 눌러 보세요.';
  $('dimensions').textContent = '800 × 800'; $('summary').textContent = '분석 준비됨';
  controls(); message('센서 시작 또는 현재 화면 분석을 누르세요.');
};
$('upload').onclick = () => $('file').click();
$('file').onchange = () => { const file = $('file').files[0]; if (file) load(file, file.name).catch(e => message(e.message, true)); $('file').value = ''; };
$('sample').onclick = async () => {
  try { const r = await fetch('/sample.png'); if (!r.ok) throw Error('예제 이미지가 없습니다.'); await load(await r.blob(), '한국어 예제'); }
  catch (e) { message(e.message, true); }
};
$('show-boxes').onchange = () => {
  for (const id of ['fixture-boxes', 'image-boxes']) $(id).style.visibility = $('show-boxes').checked ? 'visible' : 'hidden';
};
$('show-boxes').onchange();
$('filter').oninput = render;
$('download').onclick = () => {
  if (!scene) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(scene, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = 'sensor-observations.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
document.addEventListener('paste', e => {
  const image = [...e.clipboardData.items].find(i => i.type.startsWith('image/'));
  if (image) { e.preventDefault(); load(image.getAsFile(), '붙여넣은 이미지').catch(err => message(err.message, true)); }
});
$('drop').ondragover = e => e.preventDefault();
$('drop').ondrop = e => { e.preventDefault(); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0], e.dataTransfer.files[0].name).catch(err => message(err.message, true)); };
controls();
