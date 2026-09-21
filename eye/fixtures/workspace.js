/* Interactive synthetic UI. Exposes rendered pixels, never labels/boxes/state to the sensor. */
export function mountWorkspace(canvas, controls, onChange) {
  const ctx = canvas.getContext('2d');
  const docs = [
    {title: '망막 모델 실험 노트', category: '연구', favorite: true, archived: false, text: 'UI 위치와 한국어 인식 결과를 기록합니다.'},
    {title: '프로젝트 일정표', category: '기획', favorite: false, archived: false, text: '다음 주에는 아이콘 인식을 평가합니다.'},
    {title: '팀 회의록', category: '회의', favorite: false, archived: false, text: '검색과 설정 화면의 변화를 관찰합니다.'},
    {title: '이전 망막 초안', category: '보관', favorite: false, archived: true, text: '지난 시각 센서 실험의 샘플 문서입니다.'},
  ];
  let query = '', applied = '', favorites = false, archive = false, modal = null, notifications = false;
  let hits = [], focused = null;
  const ink = '#193b2c', muted = '#597363', green = '#276d4b';

  function rect(x, y, w, h, fill = '#fff', border = '#ccdad0', radius = 10) {
    ctx.beginPath(); ctx.roundRect(x, y, w, h, radius); ctx.fillStyle = fill; ctx.fill();
    if (border) { ctx.strokeStyle = border; ctx.lineWidth = 2; ctx.stroke(); }
  }
  function text(value, x, y, size = 27, color = ink, weight = 400) {
    ctx.font = `${weight} ${size}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.fillStyle = color; ctx.textBaseline = 'top'; ctx.fillText(value, x, y);
  }
  function hit(id, label, box, action, kind = 'button', checked = false) {
    hits.push({id, label, box, action, kind, checked});
    if (focused === id) {
      const [x, y, w, h] = box; ctx.strokeStyle = '#d4a132'; ctx.lineWidth = 3; ctx.strokeRect(x - 3, y - 3, w + 6, h + 6);
    }
  }
  function button(id, label, x, y, w, action, primary = false) {
    rect(x, y, w, 54, primary ? green : '#fff', primary ? green : '#bfd2c5');
    ctx.font = '500 26px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    const tw = ctx.measureText(label).width;
    text(label, x + (w - tw) / 2, y + 12, 26, primary ? '#fff' : ink, 500);
    hit(id, label, [x, y, w, 54], action);
  }
  function checkbox(id, label, x, y, checked, action) {
    rect(x, y, 28, 28, checked ? green : '#fff', checked ? green : '#97ad9e', 4);
    if (checked) { ctx.beginPath(); ctx.moveTo(x + 6, y + 14); ctx.lineTo(x + 12, y + 21); ctx.lineTo(x + 23, y + 7); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.stroke(); }
    text(label, x + 42, y, 26);
    hit(id, label, [x, y - 8, 280, 44], action, 'checkbox', checked);
  }
  function update() { draw(); onChange(); }
  function syncControls() {
    const ids = new Set(hits.map(h => h.id));
    for (const el of [...controls.children]) {
      if (ids.has(el.dataset.key)) continue;
      // Removing the focused control fires blur synchronously; don't redraw during reconciliation.
      if (focused === el.dataset.key) focused = null;
      el.onblur = null;
      el.remove();
    }
    for (const h of hits) {
      let el = [...controls.children].find(e => e.dataset.key === h.id);
      if (!el) {
        el = document.createElement(h.kind === 'input' ? 'input' : 'button');
        el.dataset.key = h.id;
        if (h.kind === 'input') {
          el.type = 'text'; el.maxLength = 24; el.autocomplete = 'off';
          el.oninput = () => { query = el.value; update(); };
          el.onkeydown = e => { if (e.key === 'Enter' && !e.isComposing) { applied = query; update(); } };
        } else el.type = 'button';
        el.onfocus = () => { focused = h.id; draw(); };
        el.onblur = () => { focused = null; draw(); };
        controls.append(el);
      }
      el.setAttribute('aria-label', h.label);
      if (h.kind === 'checkbox') { el.setAttribute('role', 'checkbox'); el.setAttribute('aria-checked', String(h.checked)); }
      el.onclick = h.action;
      const [x, y, w, height] = h.box;
      Object.assign(el.style, {left: `${x / 8}%`, top: `${y / 8}%`, width: `${w / 8}%`, height: `${height / 8}%`});
      if (h.kind === 'input' && el.value !== query) el.value = query;
    }
  }
  function draw() {
    hits = []; ctx.clearRect(0, 0, 800, 800); ctx.fillStyle = '#f0f4f1'; ctx.fillRect(0, 0, 800, 800);
    rect(0, 0, 800, 106, '#193f2f', null, 0); text('문서 작업실', 28, 32, 34, '#fff', 700);
    button('settings', '설정', 652, 26, 120, () => { modal = 'settings'; update(); });
    text('문서 찾기', 28, 132, 32, ink, 700);
    rect(28, 186, 594, 58); text(query || '문서 제목을 검색하세요', 44, 201, 27, query ? ink : muted);
    hit('query', '문서 검색어', [28, 186, 594, 58], () => {}, 'input');
    button('search', '검색', 642, 188, 130, () => { applied = query; update(); }, true);
    checkbox('favorites', '즐겨찾기만', 30, 278, favorites, () => { favorites = !favorites; update(); });
    checkbox('archive', '보관 문서 포함', 382, 278, archive, () => { archive = !archive; update(); });
    const visible = docs.filter(d => (!d.archived || archive) && (!favorites || d.favorite) && (!applied || `${d.title} ${d.text}`.includes(applied)));
    text(`검색 결과 ${visible.length}개`, 28, 333, 27, ink, 600);
    visible.forEach((d, i) => {
      const y = 379 + i * 86;
      rect(28, y, 744, 74); text(d.title, 46, y + 21, 28, ink, 600);
      text(d.favorite ? '★' : '☆', 717, y + 20, 30, '#b78927');
      hit(`doc-${docs.indexOf(d)}`, `${d.title} 열기`, [28, y, 744, 74], () => { modal = d; update(); });
    });
    if (!visible.length) text('검색 결과가 없습니다.', 210, 447, 30, muted);
    button('reset', '처음으로', 28, 735, 158, () => {
      query = applied = ''; favorites = archive = notifications = false; modal = null;
      docs.forEach((d, i) => { d.favorite = i === 0; }); update();
    });
    text(notifications ? '알림 켜짐' : '알림 꺼짐', 622, 750, 24, muted);
    if (modal) {
      hits = []; ctx.fillStyle = '#142c2599'; ctx.fillRect(0, 0, 800, 800);
      rect(60, 190, 680, 430);
      if (modal === 'settings') {
        text('작업실 설정', 96, 230, 34, ink, 700);
        text('문서를 열었을 때 알림을 표시합니다.', 96, 296, 26, muted);
        checkbox('notifications', '알림 받기', 100, 379, notifications, () => { notifications = !notifications; update(); });
      } else {
        text(modal.category, 96, 227, 25, green);
        text(modal.title, 96, 274, 32, ink, 700);
        text(modal.text, 96, 351, 26, muted);
        button('favorite', modal.favorite ? '즐겨찾기 해제' : '즐겨찾기 추가', 96, 455, 244, () => { modal.favorite = !modal.favorite; update(); });
      }
      button('close', '닫기', 578, 528, 122, () => { modal = null; update(); }, true);
    }
    syncControls();
  }
  controls.addEventListener('keydown', e => { if (e.key === 'Escape' && modal) { modal = null; update(); } });
  draw();
  document.fonts.ready.then(update);
}
