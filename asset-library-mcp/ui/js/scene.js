// ── scene.js ──────────────────────────────────────────────────────
// Sahne tab: scene loading, rendering, selection, deletion, rotation, apply changes.

// ── Scene LLM selectors ────────────────────────────────────────
function selectSceneLLM(llm) {
  _sceneLLM = llm;
  ['gemini', 'claude'].forEach(id => {
    const btn = document.getElementById(`scene-llm-${id}`);
    const active = id === llm;
    btn.classList.toggle('border-sky-500',  active);
    btn.classList.toggle('text-sky-700',    active);
    btn.classList.toggle('border-gray-300', !active);
    btn.classList.toggle('text-gray-500',   !active);
  });
}

function selectGenLLM(llm) {
  _genLLM = llm;
  ['gemini', 'claude'].forEach(id => {
    const btn = document.getElementById(`gen-llm-${id}`);
    const active = id === llm;
    btn.classList.toggle('border-emerald-500', active);
    btn.classList.toggle('text-emerald-700',   active);
    btn.classList.toggle('border-gray-300',    !active);
    btn.classList.toggle('text-gray-500',      !active);
  });
}

// ── Scene Select / Delete modes ────────────────────────────────
function updateSceneModeUI() {
  const selBtn  = document.getElementById('btn-scene-select');
  const delBtn  = document.getElementById('btn-scene-delete');
  const selHint = document.getElementById('scene-select-hint');
  const delHint = document.getElementById('scene-delete-hint');
  const canvas  = document.getElementById('scene-canvas');

  const isSelect = _sceneMode === 'select';
  const isDelete = _sceneMode === 'delete';

  selBtn.textContent = isSelect ? '✕ İptal' : '🖱 Seç';
  selBtn.className = `flex items-center gap-2 ${isSelect
    ? 'bg-amber-500 hover:bg-amber-600'
    : 'bg-sky-600 hover:bg-sky-700'} text-white px-3 py-2 rounded-xl text-sm font-medium transition-colors`;

  delBtn.textContent = isDelete ? '✕ İptal' : '🗑 Sil';
  delBtn.className = `flex items-center gap-2 ${isDelete
    ? 'bg-amber-500 hover:bg-amber-600'
    : 'bg-red-600 hover:bg-red-700'} text-white px-3 py-2 rounded-xl text-sm font-medium transition-colors`;

  selHint.classList.toggle('hidden', !isSelect);
  delHint.classList.toggle('hidden', !isDelete);
  canvas.classList.toggle('scene-interactive', isSelect);
  canvas.classList.toggle('scene-delete', isDelete);
}

function toggleSceneSelectMode() {
  if (_sceneMode === 'select') {
    _sceneMode = 'none';
  } else {
    if (_sceneSelMode) toggleSceneSelMode();
    _sceneMode = 'select';
    clearSceneSelectPanel();
  }
  updateSceneModeUI();
}

function toggleSceneDeleteMode() {
  if (_sceneMode === 'delete') {
    _sceneMode = 'none';
  } else {
    if (_sceneSelMode) toggleSceneSelMode();
    _sceneMode = 'delete';
    clearSceneSelectPanel();
  }
  updateSceneModeUI();
}

function onSceneGroupClick(idx) {
  if (_sceneSelMode) return;
  if (_sceneMode === 'select') selectSceneGroup(idx);
  else if (_sceneMode === 'delete') deleteSceneGroup(idx);
}

function selectSceneGroup(idx) {
  _selectedGroupIdx = idx;
  const group = _sceneGroups[idx];
  document.getElementById('scene-obj-name').textContent = group.display_name;
  document.getElementById('scene-select-panel').classList.remove('hidden');
  document.getElementById('apply-result').textContent = '';
  document.getElementById('scene-obj-prompt').value = '';
  document.getElementById('scene-obj-prompt').focus();
  highlightSceneGroup(idx);
}

function clearSceneSelectPanel() {
  _selectedGroupIdx = null;
  document.getElementById('scene-select-panel').classList.add('hidden');
  const existing = document.getElementById('scene-grp-highlight');
  if (existing) existing.remove();
  document.querySelectorAll('[data-wall-name]').forEach(el => {
    el.classList.remove('ring-2','ring-sky-400','border-sky-400');
  });
}

function selectRoomItemByName(objName) {
  const idx = _sceneGroups.findIndex(g => g.is_room && g.items[0]?.name === objName);
  if (idx !== -1) {
    if (_sceneMode !== 'select') { _sceneMode = 'select'; }
    selectSceneGroup(idx);
  }
  document.querySelectorAll('[data-wall-name]').forEach(el => {
    el.classList.remove('ring-2','ring-sky-400','border-sky-400');
  });
  const card = document.querySelector(`[data-wall-name="${objName}"]`);
  if (card) card.classList.add('ring-2','ring-sky-400','border-sky-400');
}

function highlightSceneGroup(idx) {
  const existing = document.getElementById('scene-grp-highlight');
  if (existing) existing.remove();
  const svgEl = document.getElementById('scene-canvas');
  const el = document.querySelector(`[data-scene-group="${idx}"]`);
  if (!el) return;

  const innerPoly = el.querySelector('polygon');
  const innerRect = el.querySelector('rect');

  if (innerPoly) {
    const hl = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    hl.id = 'scene-grp-highlight';
    hl.setAttribute('points', innerPoly.getAttribute('points'));
    hl.setAttribute('fill', 'rgba(14,165,233,0.12)');
    hl.setAttribute('stroke', '#0ea5e9');
    hl.setAttribute('stroke-width', '3');
    hl.setAttribute('stroke-dasharray', '8,4');
    hl.setAttribute('pointer-events', 'none');
    svgEl.appendChild(hl);
  } else if (innerRect) {
    const hl = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    hl.id = 'scene-grp-highlight';
    hl.setAttribute('x', innerRect.getAttribute('x'));
    hl.setAttribute('y', innerRect.getAttribute('y'));
    hl.setAttribute('width', innerRect.getAttribute('width'));
    hl.setAttribute('height', innerRect.getAttribute('height'));
    hl.setAttribute('fill', 'rgba(14,165,233,0.25)');
    hl.setAttribute('stroke', '#0ea5e9');
    hl.setAttribute('stroke-width', '3');
    hl.setAttribute('stroke-dasharray', '6,3');
    hl.setAttribute('rx', innerRect.getAttribute('rx') || '3');
    hl.setAttribute('pointer-events', 'none');
    el.appendChild(hl);
  }
}

async function rotateSceneGroup(deltaDeg) {
  if (_selectedGroupIdx === null) return;
  const group = _sceneGroups[_selectedGroupIdx];
  const names = group.items.map(i => i.name);
  const statusEl = document.getElementById('scene-rot-status');
  statusEl.textContent = '↻ döndürülüyor...';
  try {
    const res = await fetch(`${API_BASE}/blender/rotate-objects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names, delta_z: deltaDeg }),
      signal: AbortSignal.timeout(8000),
    });
    const data = await res.json();
    if (data.error) {
      statusEl.textContent = `❌ ${data.error}`;
    } else {
      statusEl.textContent = `✓ ${deltaDeg > 0 ? '+' : ''}${deltaDeg}°`;
      setTimeout(() => { statusEl.textContent = ''; loadBlenderScene(); }, 600);
    }
  } catch (e) {
    statusEl.textContent = `❌ ${e.message}`;
  }
}

function rotateSceneGroupCustom() {
  const deg = parseFloat(document.getElementById('scene-rot-deg').value);
  if (!isNaN(deg) && deg !== 0) rotateSceneGroup(deg);
}

async function deleteSceneGroup(idx) {
  const group = _sceneGroups[idx];
  if (!group) return;
  const names = group.items.map(i => i.name);
  const status = document.getElementById('scene-status');
  status.textContent = `🗑 "${group.display_name}" siliniyor...`;

  try {
    const res = await fetch(`${API_BASE}/blender/delete-objects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json();
    if (data.error) {
      status.textContent = `❌ Sil hatası: ${data.error}`;
    } else {
      status.textContent = `✓ Silindi: ${group.display_name} (${data.count} nesne)`;
      clearSceneSelectPanel();
      setTimeout(() => loadBlenderScene(), 600);
    }
  } catch (e) {
    status.textContent = `❌ ${e.message}`;
  }
}

async function deleteSelectedGroup() {
  if (_selectedGroupIdx === null) return;
  await deleteSceneGroup(_selectedGroupIdx);
}

async function applyObjectChange() {
  if (_selectedGroupIdx === null) return;
  const prompt = document.getElementById('scene-obj-prompt').value.trim();
  if (!prompt) { alert('Lütfen ne yapmak istediğinizi yazın.'); return; }

  const group   = _sceneGroups[_selectedGroupIdx];
  const objectNames = group.items.map(i => i.name);
  const icon    = document.getElementById('apply-icon');
  const label   = document.getElementById('apply-label');
  const result  = document.getElementById('apply-result');
  const btn     = document.getElementById('btn-apply-change');

  const isPencere = /pencere|window|cam\s*bo[sş]lu/i.test(prompt);
  const isKapi    = /kap[iı]\s*(?:bo[sş]lu|aç)/i.test(prompt);
  const isWall    = group.is_room && /Wall/i.test(group.display_name);

  if ((isPencere || isKapi) && isWall) {
    function parseMetre(text, keywords) {
      const kw = keywords.join('|');
      let m;
      m = text.match(new RegExp(`([\\d][\\d.,]*)\\s*m?\\s*(?:${kw})`, 'i'));
      if (m) return parseFloat(m[1].replace(',', '.'));
      m = text.match(new RegExp(`(?:${kw})\\s*:?\\s*([\\d][\\d.,]*)`, 'i'));
      if (m) return parseFloat(m[1].replace(',', '.'));
      return null;
    }

    const wParsed = parseMetre(prompt, ['genişlik','wide','width','en']);
    const hParsed = parseMetre(prompt, ['yükseklik','yüksek','high','height','boy']);
    const sParsed = parseMetre(prompt, ['parapet','sill','döşeme','alt']);

    const isDoor = isKapi;
    const width  = wParsed ?? 1.0;
    const height = hParsed ?? (isDoor ? 2.1 : 1.2);
    const sill   = sParsed ?? (isDoor ? 0.0 : 0.9);

    const trNums = { bir:1, iki:2, üç:3, uc:3, dört:4, dort:4, beş:5, bes:5, altı:6, alti:6 };
    let count = 1;
    const countMatch = prompt.match(/(\d+)\s*(?:tane\s*)?(?:pencere|window|cam|kapı|kapi)/i)
                    || prompt.match(/(?:pencere|window|cam|kapı|kapi)\s*sayısı\s*[:=]?\s*(\d+)/i);
    if (countMatch) {
      count = Math.max(1, parseInt(countMatch[1]));
    } else {
      const trMatch = prompt.match(/\b(bir|iki|üç|uc|dört|dort|beş|bes|altı|alti)\b/i);
      if (trMatch) count = trNums[trMatch[1].toLowerCase()] || 1;
    }

    const full_width = /full\s*(?:cam|pencere|window|glass)|tam\s*cam|tüm\s*duvar/i.test(prompt);

    btn.disabled = true; icon.textContent = '⏳'; label.textContent = 'Açılıyor...'; result.textContent = '';
    try {
      const res = await fetch(`${API_BASE}/blender/add-window`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wall_name:    group.items[0]?.name,
          width, height, sill_height: sill, offset_x: 0, count, full_width,
        }),
        signal: AbortSignal.timeout(25000),
      });
      const data = await res.json();
      if (data.error) {
        result.className = 'text-xs text-red-600'; result.textContent = `❌ ${data.error}`;
      } else {
        result.className = 'text-xs text-green-700 font-medium';
        result.textContent = `✓ ${data.message}`;
        const autoApply = document.getElementById('hdri-auto-apply')?.checked;
        const hdriPath  = document.getElementById('hdri-path-input')?.value?.trim();
        if (autoApply && hdriPath) applyHdri(false);
        setTimeout(() => loadBlenderScene(), 1400);
      }
    } catch (e) {
      result.className = 'text-xs text-red-600'; result.textContent = `❌ ${e.message}`;
    } finally {
      btn.disabled = false; icon.textContent = '✨'; label.textContent = 'Uygula';
    }
    return;
  }

  btn.disabled = true;
  icon.textContent  = '⏳';
  label.textContent = 'Uygulanıyor...';
  result.textContent = '';

  try {
    const objectData = group.items.map(i => ({
      name: i.name,
      location: i.location,
      dims_m: i.dims_m,
      rotation_euler: i.rotation_euler,
    }));
    const res = await fetch(`${API_BASE}/blender/modify-object`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        object_names: objectNames,
        group_name: group.display_name,
        prompt,
        llm: _sceneLLM,
        object_data: objectData,
      }),
      signal: AbortSignal.timeout(40000),
    });
    const data = await res.json();
    if (data.error) {
      result.className = 'text-xs text-red-600';
      result.textContent = `❌ ${data.error}`;
    } else {
      result.className = 'text-xs text-green-700 font-medium';
      result.textContent = `✓ ${data.message}`;
      setTimeout(() => loadBlenderScene(), 1500);
    }
  } catch (e) {
    result.className = 'text-xs text-red-600';
    result.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled      = false;
    icon.textContent  = '✨';
    label.textContent = 'Uygula';
  }
}

async function applyHdri(showMsg = true) {
  const path     = document.getElementById('hdri-path-input').value.trim();
  const rotation = parseFloat(document.getElementById('hdri-rotation').value) || 0;
  const strength = parseFloat(document.getElementById('hdri-strength').value) || 1.0;
  const result   = document.getElementById('hdri-result');
  if (!path) { if (showMsg) { result.className='text-xs text-red-400'; result.textContent='HDRI dosya yolu girin.'; } return false; }
  if (showMsg) { result.className='text-xs text-slate-300'; result.textContent='⏳ Yükleniyor...'; }
  try {
    const res  = await fetch(`${API_BASE}/blender/set-world-hdri`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ hdri_path: path, rotation, strength }),
      signal: AbortSignal.timeout(15000),
    });
    const data = await res.json();
    if (data.error) {
      if (showMsg) { result.className='text-xs text-red-400'; result.textContent=`❌ ${data.error}`; }
      return false;
    }
    if (showMsg) { result.className='text-xs text-green-400'; result.textContent='✓ HDRI uygulandı — Blender: Z → Material Preview'; }
    return true;
  } catch (e) {
    if (showMsg) { result.className='text-xs text-red-400'; result.textContent=`❌ ${e.message}`; }
    return false;
  }
}

async function loadBlenderScene() {
  const icon   = document.getElementById("scene-refresh-icon");
  const label  = document.getElementById("scene-refresh-label");
  const status = document.getElementById("scene-status");
  icon.textContent  = "⏳";
  label.textContent = "Analiz ediliyor...";
  status.textContent = "";
  document.getElementById("scene-groups").innerHTML = "";
  document.getElementById("scene-analysis").classList.add("hidden");
  try {
    const res  = await fetch(`${API_BASE}/blender/scene/analyze`, { signal: AbortSignal.timeout(20000) });
    const data = await res.json();
    if (data.error) {
      status.textContent = `❌ ${data.error}`;
      return;
    }
    _sceneData = data;
    renderSceneCanvas(data.objects || [], data.groups || []);
    renderSceneGroups(data.groups || [], data.analysis || "");
    refreshWindowWalls();
    status.textContent = `${data.count || 0} nesne · ${(data.groups || []).length} grup · ${new Date().toLocaleTimeString("tr-TR")}`;
  } catch (e) {
    status.textContent = `❌ Bağlantı hatası: ${e.message}`;
  } finally {
    icon.textContent  = "↺";
    label.textContent = "Sahneyi Tazele";
  }
}

function renderSceneGroups(groups, analysis) {
  const container  = document.getElementById("scene-groups");
  const analysisEl = document.getElementById("scene-analysis");
  container.innerHTML = "";

  if (analysis) {
    analysisEl.classList.remove("hidden");
    analysisEl.innerHTML =
      `<p class="font-semibold text-indigo-800 mb-1">💡 Tasarım Analizi (Gemini)</p>
       <p class="text-indigo-900">${analysis}</p>`;
  }

  if (!groups.length) return;

  const roomGroup = groups.find(g => g.display_name === "Oda Yapısı");
  if (roomGroup) {
    const floors = roomGroup.items.filter(o => o.name === 'Room_Floor');
    const walls  = roomGroup.items.filter(o => o.name !== 'Room_Floor');
    const totalArea = floors.length
      ? ((floors[0].dims_m[0]||0) * (floors[0].dims_m[1]||0)).toFixed(1)
      : null;

    container.insertAdjacentHTML("beforeend", `
      <div class="mb-2">
        <div class="flex items-center gap-2 px-1 pb-1.5 border-b border-slate-200">
          <span class="text-base leading-none">🏠</span>
          <span class="text-sm font-bold text-slate-800">Oda Yapısı</span>
          <span class="text-xs text-slate-500 ml-1">${walls.length} duvar${totalArea ? ' · ' + totalArea + 'm²' : ''}</span>
        </div>
      </div>`);

    for (const fl of floors) {
      const w = (fl.dims_m[0]||0).toFixed(2), d = (fl.dims_m[1]||0).toFixed(2);
      const area = ((fl.dims_m[0]||0)*(fl.dims_m[1]||0)).toFixed(1);
      container.insertAdjacentHTML("beforeend", `
        <div class="flex items-center gap-2 mb-1.5 px-3 py-2 bg-amber-50 border border-amber-200 rounded-xl cursor-pointer hover:border-amber-400 hover:bg-amber-100 transition-colors"
          data-wall-name="${fl.name}" onclick="selectRoomItemByName('${fl.name}')">
          <span style="width:10px;height:10px;background:#ca8a04;border-radius:3px;flex-shrink:0;display:inline-block"></span>
          <div class="flex-1 min-w-0">
            <p class="text-xs font-bold text-amber-900">Zemin</p>
            <p class="text-[10px] text-amber-700 font-mono">${w}×${d}m · ${area}m²</p>
          </div>
          <span class="text-[10px] text-amber-600 bg-amber-100 border border-amber-300 rounded px-1.5 py-0.5">seç</span>
        </div>`);
    }

    const cardinalMap = { North:'Kuzey ↑', South:'Güney ↓', East:'Doğu →', West:'Batı ←' };
    for (const wall of walls) {
      const len = (wall.dims_m[0]||0).toFixed(2);
      const h   = (wall.dims_m[2]||0).toFixed(2);
      const rotDeg = (wall.rotation_euler&&wall.rotation_euler[2]) ? wall.rotation_euler[2].toFixed(0)+'°' : '0°';
      const suffix = wall.name.replace('Room_Wall_','');
      const friendlyName = cardinalMap[suffix] ? cardinalMap[suffix] + ' Duvarı' : 'Duvar ' + suffix;
      container.insertAdjacentHTML("beforeend", `
        <div class="flex items-center gap-2 mb-1.5 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl cursor-pointer hover:border-slate-500 hover:bg-slate-100 transition-colors"
          data-wall-name="${wall.name}" onclick="selectRoomItemByName('${wall.name}')">
          <span style="width:10px;height:26px;background:#1e293b;border-radius:2px;flex-shrink:0;display:inline-block"></span>
          <div class="flex-1 min-w-0">
            <p class="text-xs font-bold text-slate-800">${friendlyName}</p>
            <p class="text-[10px] text-slate-500 font-mono">${len}m uzun · ${h}m yüksek · ${rotDeg}</p>
          </div>
          <span class="text-[10px] text-slate-600 bg-slate-200 border border-slate-300 rounded px-1.5 py-0.5">seç</span>
        </div>`);
    }

    if (groups.some(g => g.display_name !== "Oda Yapısı")) {
      container.insertAdjacentHTML("beforeend", `<div class="my-3 border-t border-gray-200"></div>`);
    }
  }

  groups.forEach((group, gi) => {
    if (group.display_name === "Oda Yapısı") return;

    const badge = group.count > 1
      ? `<span class="ml-2 bg-indigo-100 text-indigo-700 text-xs px-2 py-0.5 rounded-full font-medium">${group.count}×</span>`
      : "";

    const primaryItem = group.items.reduce((best, it) =>
      (it.dims_m[0]||0)*(it.dims_m[1]||0) > (best.dims_m[0]||0)*(best.dims_m[1]||0) ? it : best
    , group.items[0]);

    const itemsHtml = group.items.map(item => {
      const dim = item.dims_m.slice(0,2).map(v=>v.toFixed(2)).join("×");
      const isPrimary = item.is_primary || item.name === primaryItem.name;
      let label, dot;
      if (isPrimary) {
        dot   = `<span class="text-indigo-400 shrink-0">●</span>`;
        label = `<span class="text-indigo-600 font-medium">ana gövde</span>`;
      } else {
        dot   = `<span class="text-gray-300 shrink-0">└</span>`;
        const pn = primaryItem.name;
        const raw = item.name.startsWith(pn+"_") ? item.name.slice(pn.length+1) : item.name;
        label = `<span class="text-gray-500">${raw.replace(/_/g," ").replace(/\b\w/g,c=>c.toUpperCase())}</span>`;
      }
      return `
        <li class="flex items-center gap-2 py-1.5 pl-2 text-xs border-t border-gray-100 first:border-t-0">
          ${dot}${label}
          <span class="text-gray-400 shrink-0 ml-auto font-mono">${dim}m</span>
        </li>`;
    }).join("");

    container.insertAdjacentHTML("beforeend", `
      <div class="border bg-white border-gray-200 hover:border-indigo-300 rounded-xl overflow-hidden">
        <button onclick="toggleSceneGroup(${gi})"
          class="w-full flex items-center gap-2 px-4 py-2.5 text-left select-none">
          <span class="text-sm font-semibold text-gray-800">${group.display_name}${badge}</span>
          <span id="scene-grp-arrow-${gi}" class="ml-auto text-gray-400 text-xs transition-transform duration-150">▼</span>
        </button>
        <ul id="scene-grp-${gi}" class="hidden px-4 pb-2">${itemsHtml}</ul>
      </div>`);
  });
}

function toggleSceneGroup(gi) {
  const body  = document.getElementById(`scene-grp-${gi}`);
  const arrow = document.getElementById(`scene-grp-arrow-${gi}`);
  const open  = !body.classList.contains("hidden");
  body.classList.toggle("hidden", open);
  arrow.style.transform = open ? "" : "rotate(180deg)";
}

function renderSceneCanvas(objects, groups) {
  const svg    = document.getElementById("scene-canvas");
  const legend = document.getElementById("scene-legend");
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  legend.innerHTML = "";

  const visible = objects.filter(o => o.visible !== false);
  if (!visible.length) {
    const defScale = Math.min(SCENE_SVG_W, SCENE_SVG_H) * 0.85 / 10;
    _sceneTransform = {
      scale: defScale, midX: 0, midY: 0,
      svgCX: SCENE_SVG_W / 2, svgCY: SCENE_SVG_H / 2,
      w2sx: wx =>  SCENE_SVG_W / 2 + wx * defScale,
      w2sy: wy =>  SCENE_SVG_H / 2 - wy * defScale,
      s2wx: sx => (sx - SCENE_SVG_W / 2) / defScale,
      s2wy: sy => -((sy - SCENE_SVG_H / 2) / defScale),
    };
    svg.insertAdjacentHTML("beforeend",
      `<text x="${SCENE_SVG_W/2}" y="${SCENE_SVG_H/2}" text-anchor="middle"
        fill="#94a3b8" font-size="14">Sahne boş — Blender'da hiç mesh yok</text>`);
    return;
  }

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const o of visible) {
    const ang = ((o.rotation_euler && o.rotation_euler[2]) || 0) * Math.PI / 180;
    const l = (o.dims_m[0] || 0.1) / 2;
    const t = (o.dims_m[1] || 0.1) / 2;
    const hwx = Math.abs(Math.cos(ang)) * l + Math.abs(Math.sin(ang)) * t;
    const hwy = Math.abs(Math.sin(ang)) * l + Math.abs(Math.cos(ang)) * t;
    minX = Math.min(minX, o.location[0] - hwx); maxX = Math.max(maxX, o.location[0] + hwx);
    minY = Math.min(minY, o.location[1] - hwy); maxY = Math.max(maxY, o.location[1] + hwy);
  }
  const padX = Math.max((maxX - minX) * 0.1, 0.3);
  const padY = Math.max((maxY - minY) * 0.1, 0.3);
  minX -= padX; maxX += padX; minY -= padY; maxY += padY;

  const scale = Math.min(
    (SCENE_SVG_W * 0.9) / (maxX - minX),
    (SCENE_SVG_H * 0.9) / (maxY - minY)
  );
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const svgCX = SCENE_SVG_W / 2, svgCY = SCENE_SVG_H / 2;
  const w2sx = wx => svgCX + (wx - midX) * scale;
  const w2sy = wy => svgCY - (wy - midY) * scale;

  _sceneTransform = {
    scale, midX, midY, svgCX, svgCY,
    w2sx, w2sy,
    s2wx: sx => (sx - svgCX) / scale + midX,
    s2wy: sy => -((sy - svgCY) / scale) + midY,
  };

  svg.insertAdjacentHTML("beforeend",
    `<text x="${svgCX}" y="14" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="bold">N</text>
     <text x="${svgCX}" y="${SCENE_SVG_H-4}" text-anchor="middle" fill="#94a3b8" font-size="10" font-weight="bold">S</text>
     <text x="${SCENE_SVG_W-4}" y="${svgCY+4}" text-anchor="end" fill="#94a3b8" font-size="10" font-weight="bold">E</text>
     <text x="4" y="${svgCY+4}" text-anchor="start" fill="#94a3b8" font-size="10" font-weight="bold">W</text>`);

  const paletteHue = [210, 280, 40, 150, 0, 320, 180, 60, 100, 240];
  const useGroups = groups && groups.length > 0;

  if (useGroups) {
    _sceneGroups = [];

    const roomGroup = groups.find(g => g.display_name === "Oda Yapısı");
    if (roomGroup) {
      const floors = roomGroup.items.filter(o => o.name === 'Room_Floor');
      const walls  = roomGroup.items.filter(o => o.name !== 'Room_Floor');

      for (const obj of [...floors, ...walls]) {
        _sceneGroups.push({ display_name: obj.name, items: [obj], count: 1, is_room: true });
      }

      const wallThickSvg = Math.max(0.15 * scale, 6);
      const floorGIdx = _sceneGroups.findIndex(g => g.display_name === 'Room_Floor');

      const numberedWalls = walls
        .filter(w => /^Room_Wall_\d+$/.test(w.name))
        .sort((a, b) => {
          return parseInt(a.name.match(/\d+/)[0]) - parseInt(b.name.match(/\d+/)[0]);
        });
      const isPolygon = numberedWalls.length > 0;

      if (isPolygon) {
        const reconPts = numberedWalls.map(w => {
          const cx = w.location[0], cy = w.location[1];
          const len = w.dims_m[0] || 0.5;
          const ang = ((w.rotation_euler && w.rotation_euler[2]) || 0) * Math.PI / 180;
          return [cx - Math.cos(ang) * len / 2, cy - Math.sin(ang) * len / 2];
        });

        const rpys = reconPts.map(p => p[1]);
        const reconValid = (Math.max(...rpys) - Math.min(...rpys)) > 0.05;

        const usePts = (_drawnRoom && _drawnRoom.points && _drawnRoom.points.length >= 3)
          ? _drawnRoom.points
          : (reconValid ? reconPts : null);

        if (!usePts) {
          svg.insertAdjacentHTML("beforeend",
            `<text x="${svgCX}" y="${svgCY - 14}" text-anchor="middle"
               fill="#b45309" font-size="12" font-weight="600">Oda şekli algılanamadı</text>
             <text x="${svgCX}" y="${svgCY + 6}" text-anchor="middle"
               fill="#94a3b8" font-size="11">Oda Çiz → "Kullan" ile odayı yeniden gönderin</text>`);
        } else {
          const pxs = usePts.map(p => p[0]), pys = usePts.map(p => p[1]);
          const rW = (Math.max(...pxs) - Math.min(...pxs)).toFixed(1);
          const rD = (Math.max(...pys) - Math.min(...pys)).toFixed(1);
          const cxC = (Math.max(...pxs) + Math.min(...pxs)) / 2;
          const cyC = (Math.max(...pys) + Math.min(...pys)) / 2;

          const floorPtsSvg = usePts
            .map(p => `${w2sx(p[0]).toFixed(1)},${w2sy(p[1]).toFixed(1)}`).join(' ');
          svg.insertAdjacentHTML("beforeend",
            `<polygon points="${floorPtsSvg}"
               fill="#fef9c3" fill-opacity="0.6" stroke="#d4a017" stroke-width="1"
               stroke-dasharray="6,3" pointer-events="none" />`);

          svg.insertAdjacentHTML("beforeend",
            `<text x="${w2sx(cxC).toFixed(1)}" y="${(w2sy(cyC) - 8).toFixed(1)}"
               text-anchor="middle" fill="#b45309" font-size="11" font-weight="700"
               pointer-events="none">${rW}m × ${rD}m</text>`);

          if (floorGIdx >= 0) {
            const flG = document.createElementNS("http://www.w3.org/2000/svg", "g");
            flG.dataset.sceneGroup = floorGIdx;
            flG.innerHTML = `<polygon points="${floorPtsSvg}" fill="transparent" cursor="pointer" />`;
            flG.addEventListener('click', (e) => {
              if (_sceneSelMode) return; e.stopPropagation(); onSceneGroupClick(floorGIdx);
            });
            svg.appendChild(flG);
          }

          const n = usePts.length;
          const wallThick = Math.max(wallThickSvg, 7);
          for (let i = 0; i < n; i++) {
            const a = usePts[i], b = usePts[(i + 1) % n];
            const ax = w2sx(a[0]), ay = w2sy(a[1]);
            const bx = w2sx(b[0]), by = w2sy(b[1]);
            const mx = (ax + bx) / 2, my = (ay + by) / 2;
            const slen = Math.sqrt((bx - ax) ** 2 + (by - ay) ** 2);
            if (slen < 2) continue;
            const rotSvg = Math.atan2(by - ay, bx - ax) * 180 / Math.PI;
            const wallNum = i + 1;
            const wallName = `Room_Wall_${String(wallNum).padStart(2, '0')}`;
            const wGIdx = _sceneGroups.findIndex(g => g.display_name === wallName);
            if (wGIdx < 0) continue;
            const lbl = `D${String(wallNum).padStart(2, '0')}`;
            const lblRot = (rotSvg > 90 || rotSvg < -90) ? 180 : 0;
            const wG = document.createElementNS("http://www.w3.org/2000/svg", "g");
            wG.dataset.sceneGroup = wGIdx;
            wG.setAttribute("transform",
              `translate(${mx.toFixed(1)},${my.toFixed(1)}) rotate(${rotSvg.toFixed(1)})`);
            wG.innerHTML = `
              <rect x="${(-slen / 2).toFixed(1)}" y="${(-wallThick / 2).toFixed(1)}"
                 width="${slen.toFixed(1)}" height="${wallThick.toFixed(1)}"
                 fill="#1e293b" fill-opacity="0.92" cursor="pointer" rx="1" />
              <text x="0" y="0" text-anchor="middle" dominant-baseline="middle"
                 fill="#94a3b8" font-size="9" pointer-events="none"
                 transform="rotate(${lblRot})">${lbl}</text>`;
            wG.addEventListener('click', (e) => {
              if (_sceneSelMode) return; e.stopPropagation(); onSceneGroupClick(wGIdx);
            });
            svg.appendChild(wG);
          }
        }

      } else if (floors.length > 0) {
        const fl  = floors[0];
        const flx = w2sx(fl.location[0]), fly = w2sy(fl.location[1]);
        const flW = (fl.dims_m[0] || 5) * scale;
        const flD = (fl.dims_m[1] || 4) * scale;

        svg.insertAdjacentHTML("beforeend",
          `<rect x="${(flx - flW / 2).toFixed(1)}" y="${(fly - flD / 2).toFixed(1)}"
             width="${flW.toFixed(1)}" height="${flD.toFixed(1)}"
             fill="#fef9c3" fill-opacity="0.6" pointer-events="none" />`);
        svg.insertAdjacentHTML("beforeend",
          `<text x="${flx.toFixed(1)}" y="${(fly - flD / 2 - 7).toFixed(1)}"
             text-anchor="middle" fill="#b45309" font-size="11" font-weight="700"
             pointer-events="none">
             ${(fl.dims_m[0] || 0).toFixed(1)}m × ${(fl.dims_m[1] || 0).toFixed(1)}m
           </text>`);

        if (floorGIdx >= 0) {
          const flG = document.createElementNS("http://www.w3.org/2000/svg", "g");
          flG.dataset.sceneGroup = floorGIdx;
          flG.innerHTML = `<rect x="${(flx - flW / 2).toFixed(1)}" y="${(fly - flD / 2).toFixed(1)}"
             width="${flW.toFixed(1)}" height="${flD.toFixed(1)}" fill="transparent" cursor="pointer" />`;
          flG.addEventListener('click', (e) => {
            if (_sceneSelMode) return; e.stopPropagation(); onSceneGroupClick(floorGIdx);
          });
          svg.appendChild(flG);
        }

        for (const wall of walls) {
          const wGIdx = _sceneGroups.findIndex(g => g.display_name === wall.name);
          if (wGIdx < 0) continue;
          const wx     = w2sx(wall.location[0]);
          const wy     = w2sy(wall.location[1]);
          const pw     = (wall.dims_m[0] || 0.2) * scale;
          const pd     = Math.max((wall.dims_m[1] || 0.15) * scale, 6);
          const rotDeg = (wall.rotation_euler && wall.rotation_euler[2]) || 0;
          const wG = document.createElementNS("http://www.w3.org/2000/svg", "g");
          wG.dataset.sceneGroup = wGIdx;
          wG.setAttribute("transform", `translate(${wx.toFixed(1)},${wy.toFixed(1)}) rotate(${-rotDeg})`);
          wG.innerHTML = `<rect x="${(-pw / 2).toFixed(1)}" y="${(-pd / 2).toFixed(1)}"
             width="${pw.toFixed(1)}" height="${pd.toFixed(1)}"
             fill="#1e293b" fill-opacity="0.9" stroke="#334155" stroke-width="1" cursor="pointer" />`;
          wG.addEventListener('click', (e) => {
            if (_sceneSelMode) return; e.stopPropagation(); onSceneGroupClick(wGIdx);
          });
          svg.appendChild(wG);
        }
      }
    }

    const furniturePaletteIdx = { v: 0 };
    for (const group of groups) {
      if (group.display_name === "Oda Yapısı") continue;

      _sceneGroups.push(group);
      const groupIdx = _sceneGroups.length - 1;

      const primary = group.items.reduce((best, item) => {
        const a = (item.dims_m[0] || 0) * (item.dims_m[1] || 0);
        const b = (best.dims_m[0] || 0) * (best.dims_m[1] || 0);
        return a > b ? item : best;
      }, group.items[0]);

      const color = `hsl(${paletteHue[furniturePaletteIdx.v % paletteHue.length]},62%,62%)`;
      furniturePaletteIdx.v++;

      const pw = (primary.dims_m[0] || 0.2) * scale;
      const pd = (primary.dims_m[1] || 0.2) * scale;
      const sx = w2sx(primary.location[0]);
      const sy = w2sy(primary.location[1]);
      const rotDeg = (primary.rotation_euler && primary.rotation_euler[2]) || 0;
      const lbl = group.display_name.length > 16 ? group.display_name.slice(0,15)+"…" : group.display_name;
      const fs  = Math.min(Math.max(Math.min(pw, pd) * 0.28, 8), 12);

      const grpG = document.createElementNS("http://www.w3.org/2000/svg", "g");
      grpG.dataset.sceneGroup = groupIdx;
      grpG.setAttribute("transform", `translate(${sx},${sy}) rotate(${-rotDeg})`);
      grpG.innerHTML = `
        <rect x="${-pw/2}" y="${-pd/2}" width="${pw}" height="${pd}"
           fill="${color}" fill-opacity="0.88" stroke="#1e293b" stroke-width="1.5" rx="3" />
        <line x1="${-pw/2}" y1="${pd/2}" x2="${pw/2}" y2="${pd/2}"
           stroke="#dc2626" stroke-width="2.5" pointer-events="none" />
        <text x="0" y="0" text-anchor="middle" dominant-baseline="middle"
           fill="#1e293b" font-size="${fs}" font-weight="bold" pointer-events="none"
           style="text-shadow:0 0 3px rgba(255,255,255,0.8)">${lbl}</text>`;
      grpG.addEventListener('click', (e) => {
        if (_sceneSelMode) return;
        e.stopPropagation();
        onSceneGroupClick(groupIdx);
      });
      svg.appendChild(grpG);

      const dimStr = primary.dims_m.slice(0,2).map(v=>v.toFixed(2)).join("×");
      legend.insertAdjacentHTML("beforeend",
        `<span class="flex items-center gap-1 bg-gray-50 border border-gray-200 rounded-md px-2 py-0.5">
           <span style="width:9px;height:9px;background:${color};display:inline-block;border-radius:2px;flex-shrink:0"></span>
           <span class="font-medium">${group.display_name}</span>
           <span class="text-gray-400">${dimStr}m</span>
         </span>`);
    }
  } else {
    const sorted = [...visible].sort((a,b) => {
      return (/^Room_|wall|floor|ceiling/i.test(a.name) ? 0 : 1) -
             (/^Room_|wall|floor|ceiling/i.test(b.name) ? 0 : 1);
    });
    const colorMap = {}; let pi = 0;
    for (const obj of sorted) {
      const isStruct = /^Room_|wall|floor|ceiling/i.test(obj.name);
      const pw = (obj.dims_m[0] || 0.2) * scale;
      const pd = (obj.dims_m[1] || 0.2) * scale;
      const sx = w2sx(obj.location[0]), sy = w2sy(obj.location[1]);
      const rotDeg = (obj.rotation_euler && obj.rotation_euler[2]) || 0;
      if (!colorMap[obj.name]) colorMap[obj.name] = isStruct ? "#cbd5e1"
        : `hsl(${paletteHue[pi++ % paletteHue.length]},60%,65%)`;
      const fill = colorMap[obj.name];
      const fs = Math.min(Math.max(Math.min(pw,pd)*0.28,7),11);
      const lbl = obj.name.length > 18 ? obj.name.slice(0,16)+"…" : obj.name;
      const flatG = document.createElementNS("http://www.w3.org/2000/svg", "g");
      flatG.setAttribute("transform", `translate(${sx},${sy}) rotate(${-rotDeg})`);
      flatG.innerHTML = `
        <rect x="${-pw/2}" y="${-pd/2}" width="${pw}" height="${pd}"
           fill="${fill}" fill-opacity="${isStruct?'0.4':'0.85'}"
           stroke="${isStruct?'#94a3b8':'#334155'}" stroke-width="1" rx="2" />
        ${isStruct ? '' : `<line x1="${-pw/2}" y1="${pd/2}" x2="${pw/2}" y2="${pd/2}"
           stroke="#dc2626" stroke-width="2" pointer-events="none" />`}
        <text x="0" y="0" text-anchor="middle" dominant-baseline="middle"
           fill="${isStruct?'#64748b':'#1e293b'}" font-size="${fs}"
           font-weight="${isStruct?'normal':'bold'}" pointer-events="none">${lbl}</text>`;
      svg.appendChild(flatG);
    }
  }
}

// ── Scene Area Selection ────────────────────────────────────────
function toggleSceneSelMode() {
  _sceneSelMode = !_sceneSelMode;
  const btn    = document.getElementById("btn-scene-sel");
  const hint   = document.getElementById("scene-sel-hint");
  const canvas = document.getElementById("scene-canvas");

  if (_sceneSelMode) {
    btn.textContent = "✕ İptal";
    btn.className = btn.className.replace("bg-emerald-600","bg-amber-500").replace("hover:bg-emerald-700","hover:bg-amber-600");
    canvas.style.cursor = "crosshair";
    hint.classList.remove("hidden");
    clearSceneSelection();
    if (_sceneMode !== 'none') { _sceneMode = 'none'; updateSceneModeUI(); }
  } else {
    btn.textContent = "📐 Alan Çiz";
    btn.className = btn.className.replace("bg-amber-500","bg-emerald-600").replace("hover:bg-amber-600","hover:bg-emerald-700");
    canvas.style.cursor = "default";
    hint.classList.add("hidden");
    clearSceneSelection();
  }
}

function clearSceneSelection() {
  _sceneSelection = null;
  _sceneSelStart  = null;
  document.getElementById("scene-gen-panel").classList.add("hidden");
  const existing = document.getElementById("scene-canvas").querySelector("#scene-sel-rect");
  if (existing) existing.remove();
}

function sceneMouseDown(e) {
  if (!_sceneSelMode) return;
  if (!_sceneTransform) {
    const defScale = Math.min(SCENE_SVG_W, SCENE_SVG_H) * 0.85 / 10;
    _sceneTransform = {
      scale: defScale, midX: 0, midY: 0,
      svgCX: SCENE_SVG_W / 2, svgCY: SCENE_SVG_H / 2,
      w2sx: wx =>  SCENE_SVG_W / 2 + wx * defScale,
      w2sy: wy =>  SCENE_SVG_H / 2 - wy * defScale,
      s2wx: sx => (sx - SCENE_SVG_W / 2) / defScale,
      s2wy: sy => -((sy - SCENE_SVG_H / 2) / defScale),
    };
  }
  const svg = document.getElementById("scene-canvas");
  const pt  = svgPoint(svg, e);
  _sceneSelStart = { svgX: pt.x, svgY: pt.y };
  e.preventDefault();
}

function sceneMouseMove(e) {
  if (!_sceneSelMode || !_sceneSelStart) return;
  const svg = document.getElementById("scene-canvas");
  const pt  = svgPoint(svg, e);

  const x1 = Math.min(_sceneSelStart.svgX, pt.x);
  const y1 = Math.min(_sceneSelStart.svgY, pt.y);
  const x2 = Math.max(_sceneSelStart.svgX, pt.x);
  const y2 = Math.max(_sceneSelStart.svgY, pt.y);

  let rect = svg.querySelector("#scene-sel-rect");
  if (!rect) {
    rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.id = "scene-sel-rect";
    rect.setAttribute("fill",             "rgba(16,185,129,0.10)");
    rect.setAttribute("stroke",           "#10b981");
    rect.setAttribute("stroke-width",     "2");
    rect.setAttribute("stroke-dasharray", "7,3");
    rect.setAttribute("pointer-events",   "none");
    svg.appendChild(rect);
  }
  rect.setAttribute("x", x1);
  rect.setAttribute("y", y1);
  rect.setAttribute("width",  x2 - x1);
  rect.setAttribute("height", y2 - y1);
}

function sceneMouseUp(e) {
  if (!_sceneSelMode || !_sceneSelStart || !_sceneTransform) return;
  const svg = document.getElementById("scene-canvas");
  const pt  = svgPoint(svg, e);
  const t   = _sceneTransform;

  const wx1 = Math.min(t.s2wx(_sceneSelStart.svgX), t.s2wx(pt.x));
  const wx2 = Math.max(t.s2wx(_sceneSelStart.svgX), t.s2wx(pt.x));
  const wy1 = Math.min(t.s2wy(_sceneSelStart.svgY), t.s2wy(pt.y));
  const wy2 = Math.max(t.s2wy(_sceneSelStart.svgY), t.s2wy(pt.y));

  const worldW = wx2 - wx1;
  const worldD = wy2 - wy1;

  if (worldW < 0.05 || worldD < 0.05) { clearSceneSelection(); return; }

  _sceneSelection = {
    x:     round3((wx1 + wx2) / 2),
    y:     round3((wy1 + wy2) / 2),
    width: round3(worldW),
    depth: round3(worldD),
  };
  _sceneSelStart = null;

  _sceneSelMode = false;
  const selBtn = document.getElementById("btn-scene-sel");
  if (selBtn) {
    selBtn.textContent = "📐 Alan Çiz";
    selBtn.className = selBtn.className
      .replace("bg-amber-500",      "bg-emerald-600")
      .replace("hover:bg-amber-600","hover:bg-emerald-700");
  }
  document.getElementById("scene-canvas").style.cursor = "default";
  document.getElementById("scene-sel-hint").classList.add("hidden");

  document.getElementById("scene-gen-panel").classList.remove("hidden");
  document.getElementById("scene-sel-info").textContent =
    `${worldW.toFixed(2)} m × ${worldD.toFixed(2)} m · merkez (${_sceneSelection.x.toFixed(2)}, ${_sceneSelection.y.toFixed(2)}) · nesne daha küçük olabilir`;
  document.getElementById("scene-gen-prompt").value = "";
  document.getElementById("scene-gen-prompt").focus();
  document.getElementById("gen-result").textContent = "";
}

async function generateInArea() {
  const prompt = document.getElementById("scene-gen-prompt").value.trim();
  if (!prompt)          { alert("Lütfen ne üretmek istediğinizi yazın."); return; }
  if (!_sceneSelection) { alert("Önce canvas üzerinde bir alan seçin.");  return; }

  const icon    = document.getElementById("gen-icon");
  const label   = document.getElementById("gen-label");
  const result  = document.getElementById("gen-result");
  const btn     = document.getElementById("btn-gen");
  btn.disabled  = true;
  icon.textContent  = "⏳";
  label.textContent = "Üretiliyor...";
  result.textContent = "";

  try {
    const res  = await fetch(`${API_BASE}/blender/generate-in-area`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ prompt, area: _sceneSelection, llm: _genLLM }),
      signal:  AbortSignal.timeout(40000),
    });
    const data = await res.json();

    if (data.error) {
      result.className   = "text-xs text-red-600";
      result.textContent = `❌ ${data.error}`;
    } else {
      result.className   = "text-xs text-green-700 font-medium";
      result.textContent = `✓ ${data.message}`;
      clearSceneSelection();
      setTimeout(() => loadBlenderScene(), 1800);
    }
  } catch (e) {
    result.className   = "text-xs text-red-600";
    result.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled      = false;
    icon.textContent  = "✨";
    label.textContent = "Üret";
  }
}

