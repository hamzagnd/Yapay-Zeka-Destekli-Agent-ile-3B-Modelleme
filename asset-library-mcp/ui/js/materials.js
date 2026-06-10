// ── materials.js ─────────────────────────────────────────────────
// Material tab: texture loading, saving, AI generation, applying to targets.

// ── Material presets — backend JSON ───────────────────────────
async function getSavedSets() {
  try {
    const res = await fetch(`${API_BASE}/materials/presets`, { signal: AbortSignal.timeout(5000) });
    return await res.json();
  } catch { return []; }
}

async function persistMaterialSet(name, mat) {
  try {
    await fetch(`${API_BASE}/materials/presets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, mat }),
      signal: AbortSignal.timeout(5000),
    });
  } catch { /* silent — will retry on next save */ }
}

async function deleteSavedSet(idx) {
  const name = _matSetsList[idx]?.name;
  if (!name) return;
  try {
    await fetch(`${API_BASE}/materials/presets/${encodeURIComponent(name)}`, {
      method: 'DELETE', signal: AbortSignal.timeout(5000),
    });
  } catch { /* silent */ }
  renderSavedSets();
}

async function loadSavedSet(nameOrIdx) {
  const entry = typeof nameOrIdx === 'number'
    ? _matSetsList[nameOrIdx]
    : (_matSetsList.find(s => s.name === nameOrIdx) || (await getSavedSets()).find(s => s.name === nameOrIdx));
  if (!entry) return;
  _lastMaterial = entry.mat;
  _showMatCurrent(entry.name + ': ' + _matDesc(entry.mat));

  // Highlight selected card
  const idx = typeof nameOrIdx === 'number' ? nameOrIdx : _matSetsList.findIndex(s => s.name === nameOrIdx);
  document.querySelectorAll('#mat-saved-list > div').forEach((el, i) => {
    el.classList.toggle('border-indigo-400', i === idx);
    el.classList.toggle('bg-indigo-50',      i === idx);
    el.classList.toggle('border-gray-200',   i !== idx);
  });
}

async function loadSavedSetForScene() {
  const sel = document.getElementById('scene-saved-set-sel');
  if (!sel.value) return;
  await loadSavedSet(sel.value);
  const result = document.getElementById('scene-mat-result');
  result.className = 'text-xs text-green-700 flex-1';
  result.textContent = '✓ ' + sel.value + ' yüklendi';
  setTimeout(() => { result.textContent = ''; }, 2000);
}

function _matDesc(mat) {
  if (!mat) return '?';
  if (mat.mode === 'pbr') {
    const base = (mat.diff_path || '').split(/[\\/]/).pop().replace(/\.[^.]+$/, '');
    return 'PBR · ' + base.replace(/_diff.*$/i, '').replace(/_albedo.*$/i, '');
  }
  if (mat.mode === 'file') return (mat.texture_path || '').split(/[\\/]/).pop();
  if (mat.mode === 'ai')   return 'AI · ' + (mat.prompt || '').slice(0, 28);
  return mat.mode || '?';
}

function _autoName(mat) {
  if (!mat) return 'Set';
  if (mat.mode === 'pbr') {
    const base = (mat.diff_path || '').split(/[\\/]/).pop().replace(/\.[^.]+$/, '');
    return 'PBR - ' + base.replace(/_diff.*$/i, '').replace(/_albedo.*$/i, '');
  }
  if (mat.mode === 'file') return (mat.texture_path || '').split(/[\\/]/).pop().replace(/\.[^.]+$/, '');
  if (mat.mode === 'ai')   return 'AI - ' + (mat.prompt || '').slice(0, 24);
  return 'Set';
}

function _presetThumbHTML(mat) {
  if (!mat) return `<div class="w-10 h-10 rounded-lg bg-gray-200 flex items-center justify-center text-gray-400 text-sm shrink-0">?</div>`;

  // Stored base64 thumbnail takes priority (guaranteed to display)
  if (mat.thumbnail) {
    const badge = mat.mode === 'pbr'
      ? `<span class="absolute bottom-0 right-0 bg-indigo-600 text-white text-[8px] px-0.5 rounded leading-tight font-bold">PBR</span>`
      : '';
    return `<div class="relative w-10 h-10 shrink-0">
      <img src="${mat.thumbnail}" class="w-10 h-10 rounded-lg object-cover border border-gray-200" />
      ${badge}
    </div>`;
  }

  // Fallback for older presets (no thumbnail stored yet)
  if (mat.mode === 'file' && mat.texture_path) {
    const fname = mat.texture_path.split(/[\\/]/).pop().slice(0, 4).toUpperCase();
    return `<div class="w-10 h-10 rounded-lg bg-gray-100 border border-gray-200 flex items-center justify-center text-gray-500 text-[10px] font-bold shrink-0">${fname}</div>`;
  }
  if (mat.mode === 'pbr') {
    return `<div class="w-10 h-10 rounded-lg bg-indigo-100 border border-indigo-200 flex items-center justify-center text-indigo-600 text-[9px] font-bold shrink-0">PBR</div>`;
  }
  if (mat.mode === 'ai') {
    const hue = Math.abs((mat.prompt || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)) % 360;
    return `<div class="w-10 h-10 rounded-lg shrink-0 flex items-center justify-center text-white text-xs font-bold"
      style="background:linear-gradient(135deg,hsl(${hue},55%,50%),hsl(${(hue+60)%360},55%,40%))">AI</div>`;
  }
  return `<div class="w-10 h-10 rounded-lg bg-gray-200 shrink-0"></div>`;
}

async function renderSavedSets() {
  const container = document.getElementById('mat-saved-list');
  if (!container) return;
  const sets = await getSavedSets();
  _matSetsList = sets;
  if (!sets.length) {
    container.innerHTML = '<p class="text-xs text-gray-400 italic">Henüz kayıtlı preset yok</p>';
    _renderSceneSavedSetsFromList([]);
    return;
  }
  container.innerHTML = sets.map((s, i) => `
    <div class="flex items-center gap-2.5 bg-white border border-gray-200 rounded-xl px-2.5 py-2 hover:border-indigo-300 transition-colors cursor-pointer"
      onclick="loadSavedSet(${i})" title="Tıkla: seç" id="preset-card-${i}">
      ${_presetThumbHTML(s.mat)}
      <div class="flex-1 min-w-0" id="mat-set-name-${i}">
        <p class="text-xs font-semibold text-gray-800 truncate">${s.name}</p>
        <p class="text-[10px] text-gray-400 truncate">${_matDesc(s.mat)}</p>
      </div>
      <button onclick="event.stopPropagation();startRename(${i})"
        class="text-xs px-1.5 py-1 bg-gray-100 hover:bg-gray-200 text-gray-500 rounded-lg transition-colors" title="Yeniden adlandır">✎</button>
      <button onclick="event.stopPropagation();deleteSavedSet(${i})"
        class="text-xs px-1.5 py-1 bg-red-50 hover:bg-red-100 text-red-500 rounded-lg transition-colors">✕</button>
    </div>`).join('');
  _renderSceneSavedSetsFromList(sets);

  // Retrofit thumbnails for old presets that don't have one yet (async, non-blocking)
  _retrofitThumbnails(sets);
}

async function _retrofitThumbnails(sets) {
  for (let i = 0; i < sets.length; i++) {
    const s = sets[i];
    if (s.mat?.thumbnail) continue;

    let thumbUrl = null;
    if (s.mat?.mode === 'file' && s.mat?.texture_path)
      thumbUrl = `${API_BASE}/files/texture-image?path=${encodeURIComponent(s.mat.texture_path)}`;
    else if (s.mat?.mode === 'pbr' && s.mat?.diff_path)
      thumbUrl = `${API_BASE}/files/texture-image?path=${encodeURIComponent(s.mat.diff_path)}`;

    if (!thumbUrl) continue;

    const thumb = await _createThumb(thumbUrl);
    if (!thumb) continue;

    // Save thumbnail back into preset
    const newMat = { ...s.mat, thumbnail: thumb };
    await persistMaterialSet(s.name, newMat);
    s.mat = newMat;

    // Update the card's thumbnail area in-place
    const card = document.getElementById(`preset-card-${i}`);
    if (card) {
      const oldThumb = card.querySelector('div.relative, img, div.w-10');
      if (oldThumb) oldThumb.outerHTML = _presetThumbHTML(newMat);
    }
  }
}

function _renderSceneSavedSetsFromList(sets) {
  const sel = document.getElementById('scene-saved-set-sel');
  if (!sel) return;
  sel.innerHTML = '<option value="">— Son kayıt —</option>' +
    sets.map(s => `<option value="${s.name}">${s.name}</option>`).join('');
}

function startRename(idx) {
  const entry = _matSetsList[idx];
  if (!entry) return;
  const nameDiv = document.getElementById(`mat-set-name-${idx}`);
  if (!nameDiv) return;
  const safeVal = entry.name.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
  nameDiv.innerHTML = `
    <div class="flex items-center gap-1">
      <input id="mat-rename-${idx}" type="text" value="${safeVal}"
        class="flex-1 min-w-0 border border-indigo-300 rounded px-2 py-0.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400"
        onkeydown="if(event.key==='Enter'){event.preventDefault();confirmRename(${idx});}if(event.key==='Escape')renderSavedSets();" />
      <button onclick="confirmRename(${idx})"
        class="text-xs px-1.5 py-0.5 bg-green-500 hover:bg-green-600 text-white rounded-md whitespace-nowrap">✓</button>
      <button onclick="renderSavedSets()"
        class="text-xs px-1 py-0.5 bg-gray-200 hover:bg-gray-300 text-gray-600 rounded-md">✕</button>
    </div>`;
  const input = document.getElementById(`mat-rename-${idx}`);
  if (input) { input.focus(); input.select(); }
}

async function confirmRename(idx) {
  const oldName = _matSetsList[idx]?.name;
  if (!oldName) return;
  const input = document.getElementById(`mat-rename-${idx}`);
  if (!input) return;
  const newName = input.value.trim();
  if (!newName || newName === oldName) { renderSavedSets(); return; }
  try {
    await fetch(`${API_BASE}/materials/presets/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_name: oldName, new_name: newName }),
      signal: AbortSignal.timeout(5000),
    });
  } catch { /* silent */ }
  renderSavedSets();
}

// ── Coach material picker ──────────────────────────────────────
function switchCoachMatMode(mode) {
  _coachMatMode = mode;
  const pBtn = document.getElementById('coach-mat-mode-preset');
  const fBtn = document.getElementById('coach-mat-mode-file');
  if (!pBtn || !fBtn) return;
  [pBtn, fBtn].forEach(b => {
    b.classList.remove('bg-white', 'shadow-sm', 'text-amber-800', 'font-semibold', 'text-amber-600');
  });
  const active = mode === 'preset' ? pBtn : fBtn;
  const inactive = mode === 'preset' ? fBtn : pBtn;
  active.classList.add('bg-white', 'shadow-sm', 'text-amber-800', 'font-semibold');
  inactive.classList.add('text-amber-600');
  if (mode === 'preset') _fillCoachWithPresets();
  else _fillCoachWithFiles();
}

function _fillCoachWithPresets() {
  const none = '<option value="">Yok</option>';
  const opts = _matSetsList.map((s, i) => `<option value="${i}">${s.name}</option>`).join('');
  document.getElementById('coach-floor-tex').innerHTML = none + opts;
  document.getElementById('coach-wall-tex').innerHTML  = none + opts;
}

async function _fillCoachWithFiles() {
  const floorSel = document.getElementById('coach-floor-tex');
  const wallSel  = document.getElementById('coach-wall-tex');
  floorSel.innerHTML = '<option value="">⏳</option>';
  wallSel.innerHTML  = '<option value="">⏳</option>';
  try {
    const res  = await fetch(`${API_BASE}/files/textures`, { signal: AbortSignal.timeout(8000) });
    const data = await res.json();
    const list = data.textures || [];
    const none = '<option value="">Yok</option>';
    const opts = list.map(t => `<option value="${t.path}">${t.rel}</option>`).join('');
    floorSel.innerHTML = none + opts;
    wallSel.innerHTML  = none + opts;
    list.forEach(t => {
      const n = t.name.toLowerCase();
      if ((n.includes('_diff') || n.includes('_albedo')) && !floorSel.value) floorSel.value = t.path;
    });
  } catch {
    floorSel.innerHTML = '<option value="">Yok</option>';
    wallSel.innerHTML  = '<option value="">Yok</option>';
  }
}

async function _populateCoachMatDropdowns() {
  const floorSel = document.getElementById('coach-floor-tex');
  if (!floorSel) return;
  if (_matSetsList.length === 0) await renderSavedSets();
  _coachMatMode = 'preset';
  switchCoachMatMode('preset');
}

async function applyCoachMaterials() {
  const floorVal = document.getElementById('coach-floor-tex').value;
  const wallVal  = document.getElementById('coach-wall-tex').value;
  if (!floorVal && !wallVal) { alert('En az bir materyal seçin.'); return; }

  const iconEl   = document.getElementById('coach-mat-icon');
  const labelEl  = document.getElementById('coach-mat-label');
  const resultEl = document.getElementById('coach-mat-result');
  const btn      = document.getElementById('btn-coach-mat');
  btn.disabled = true; iconEl.textContent = '⏳'; labelEl.textContent = 'Uygulanıyor...'; resultEl.textContent = '';

  const wallNames = wallVal ? await _getRoomWallNames() : [];
  const targets = [];
  if (floorVal) targets.push({ names: ['Room_Floor'], val: floorVal, label: 'Zemin' });
  if (wallVal)  targets.push({ names: wallNames, val: wallVal, label: `Duvar (${wallNames.length})` });

  const done = [];
  for (const t of targets) {
    let matBody;
    if (_coachMatMode === 'preset') {
      const preset = _matSetsList[+t.val];
      if (!preset) continue;
      matBody = { object_names: t.names, ...preset.mat };
    } else {
      matBody = { object_names: t.names, mode: 'file', texture_path: t.val };
    }
    try {
      const r = await fetch(`${API_BASE}/blender/apply-material`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(matBody), signal: AbortSignal.timeout(30000),
      });
      const d = await r.json();
      if (!d.error) done.push(t.label);
    } catch { /* ignore */ }
  }
  btn.disabled = false; iconEl.textContent = '🎨'; labelEl.textContent = 'Uygula';
  resultEl.className = done.length
    ? 'text-xs text-green-700 font-medium flex-1'
    : 'text-xs text-red-600 flex-1';
  resultEl.textContent = done.length ? '✓ ' + done.join(' + ') + ' uygulandı' : '❌ Uygulama başarısız';
}

// ── Materyal Tab ───────────────────────────────────────────────
function selectMatLLM(llm) {
  _matLLM = llm;
  ['gemini', 'claude'].forEach(id => {
    const btn = document.getElementById(`mat-llm-${id}`);
    const active = id === llm;
    btn.classList.toggle('border-purple-500', active);
    btn.classList.toggle('text-purple-700', active);
    btn.classList.toggle('border-gray-300', !active);
    btn.classList.toggle('text-gray-500', !active);
  });
}

function setMatFileMode(mode) {
  _matFileMode = mode;
  document.getElementById('mat-quick-section').classList.toggle('hidden', mode !== 'quick');
  document.getElementById('mat-pbr-section').classList.toggle('hidden', mode !== 'pbr');
  const qBtn = document.getElementById('mat-mode-quick');
  const pBtn = document.getElementById('mat-mode-pbr');
  qBtn.classList.toggle('bg-white', mode === 'quick');
  qBtn.classList.toggle('shadow-sm', mode === 'quick');
  qBtn.classList.toggle('text-gray-800', mode === 'quick');
  qBtn.classList.toggle('text-gray-500', mode !== 'quick');
  pBtn.classList.toggle('bg-white', mode === 'pbr');
  pBtn.classList.toggle('shadow-sm', mode === 'pbr');
  pBtn.classList.toggle('text-gray-800', mode === 'pbr');
  pBtn.classList.toggle('text-gray-500', mode !== 'pbr');
}

async function loadTextureList() {
  const selIds = ['mat-texture-select', 'mat-pbr-diff', 'mat-pbr-rough', 'mat-pbr-normal'];
  selIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<option value="">⏳ Yükleniyor...</option>';
  });
  try {
    const res  = await fetch(`${API_BASE}/files/textures`, { signal: AbortSignal.timeout(8000) });
    const data = await res.json();
    if (data.error) {
      selIds.forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = `<option value="">❌ ${data.error}</option>`; });
      return;
    }
    const list = data.textures || [];
    if (!list.length) {
      selIds.forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = '<option value="">Texture bulunamadı</option>'; });
      return;
    }
    const opts = list.map(t => `<option value="${t.path}">${t.rel}</option>`).join('');
    document.getElementById('mat-texture-select').innerHTML = '<option value="">-- Seç --</option>' + opts;
    document.getElementById('mat-pbr-diff').innerHTML   = '<option value="">-- diff/albedo --</option>' + opts;
    document.getElementById('mat-pbr-rough').innerHTML  = '<option value="">-- rough (opsiyonel) --</option>' + opts;
    document.getElementById('mat-pbr-normal').innerHTML = '<option value="">-- nor_gl (opsiyonel) --</option>' + opts;
    list.forEach(t => {
      const n = t.name.toLowerCase();
      if (n.includes('_diff') || n.includes('_albedo') || n.includes('_color') || n.includes('_basecolor')) {
        document.getElementById('mat-pbr-diff').value = t.path;
        document.getElementById('mat-texture-select').value = t.path;
      } else if (n.includes('_rough')) {
        document.getElementById('mat-pbr-rough').value = t.path;
      } else if (n.includes('_nor_gl') || n.includes('_normal') || n.includes('_nor')) {
        document.getElementById('mat-pbr-normal').value = t.path;
      }
    });
  } catch (e) {
    selIds.forEach(id => { const el = document.getElementById(id); if (el) el.innerHTML = `<option value="">❌ ${e.message}</option>`; });
  }
}

function selectTextureMaterial(path) { /* preview handled by auto-select */ }

// ── Thumbnail helper: canvas→base64 from an image URL ─────────
async function _createThumb(url) {
  return new Promise(resolve => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      try {
        const c = document.createElement('canvas');
        c.width = c.height = 64;
        const ctx = c.getContext('2d');
        // crop center-square
        const side = Math.min(img.naturalWidth, img.naturalHeight);
        const sx   = (img.naturalWidth  - side) / 2;
        const sy   = (img.naturalHeight - side) / 2;
        ctx.drawImage(img, sx, sy, side, side, 0, 0, 64, 64);
        resolve(c.toDataURL('image/jpeg', 0.7));
      } catch { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

async function saveFileMaterial() {
  const path = document.getElementById('mat-texture-select').value;
  if (!path) { alert('Önce bir texture seçin.'); return; }
  const thumb = await _createThumb(`${API_BASE}/files/texture-image?path=${encodeURIComponent(path)}`);
  _lastMaterial = { mode: 'file', texture_path: path, thumbnail: thumb };
  const name = _autoName(_lastMaterial);
  await persistMaterialSet(name, _lastMaterial);
  _showMatCurrent('Hızlı: ' + path.split(/[\\/]/).pop());
  renderSavedSets();
}

async function savePBRMaterial() {
  const diff   = document.getElementById('mat-pbr-diff').value;
  const rough  = document.getElementById('mat-pbr-rough').value;
  const normal = document.getElementById('mat-pbr-normal').value;
  if (!diff) { alert('En az Base Color (diff) dosyası seçin.'); return; }
  const thumb = await _createThumb(`${API_BASE}/files/texture-image?path=${encodeURIComponent(diff)}`);
  _lastMaterial = { mode: 'pbr', diff_path: diff, rough_path: rough || null, normal_path: normal || null, thumbnail: thumb };
  const name = _autoName(_lastMaterial);
  await persistMaterialSet(name, _lastMaterial);
  const parts = ['Diff: ' + diff.split(/[\\/]/).pop()];
  if (rough)  parts.push('Rough: ' + rough.split(/[\\/]/).pop());
  if (normal) parts.push('Normal: ' + normal.split(/[\\/]/).pop());
  _showMatCurrent('PBR — ' + parts.join(' · '));
  renderSavedSets();
}

async function generateAIMaterial() {
  const prompt  = document.getElementById('mat-ai-prompt').value.trim();
  const btn     = document.getElementById('btn-mat-gen');
  const icon    = document.getElementById('mat-gen-icon');
  const label   = document.getElementById('mat-gen-label');
  const result  = document.getElementById('mat-gen-result');
  if (!prompt) { alert('Materyal tarifini yazın.'); return; }

  btn.disabled = true;
  icon.textContent  = '⏳';
  label.textContent = 'Üretiliyor...';
  result.className  = 'text-xs text-gray-400';
  result.textContent = 'gemini-2.5-flash-image ile resim üretiliyor...';

  try {
    // Start background image generation job
    const startRes = await fetch(`${API_BASE}/materials/generate-texture-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, llm: _matLLM }),
      signal: AbortSignal.timeout(10000),
    });
    const { job_id, error: startErr } = await startRes.json();
    if (startErr) throw new Error(startErr);

    // Poll for completion (up to 120 seconds)
    let done = false;
    for (let i = 0; i < 60 && !done; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const pollRes = await fetch(`${API_BASE}/materials/generate-texture-image/${job_id}`,
        { signal: AbortSignal.timeout(5000) });
      const job = await pollRes.json();
      result.textContent = job.output || '...';

      if (job.status === 'done') {
        // Create file-based material with embedded thumbnail
        const mat = { mode: 'file', texture_path: job.path, thumbnail: job.thumbnail };
        const name = prompt.slice(0, 32).replace(/[^a-zA-ZğüşöçığüşöçıĞÜŞÖÇİ0-9 ]/g, '').trim() || 'AI Texture';
        _lastMaterial = mat;
        await persistMaterialSet(name, mat);
        _showMatCurrent('AI Texture: ' + name);
        result.className  = 'text-xs text-green-700 font-medium';
        result.textContent = '✓ Texture üretildi ve kaydedildi!';
        renderSavedSets();
        done = true;
      } else if (job.status === 'error') {
        throw new Error(job.error || 'Bilinmeyen hata');
      }
    }
    if (!done) throw new Error('Zaman aşımı — 120sn içinde tamamlanamadı');

  } catch (e) {
    result.className  = 'text-xs text-red-600';
    result.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled = false;
    icon.textContent  = '✨';
    label.textContent = 'Üret';
  }
}

// ── Kendi resminizden materyal ─────────────────────────────────
function openImageUpload() {
  document.getElementById('mat-image-upload-input').click();
}

async function handleImageUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const statusEl = document.getElementById('mat-upload-status');
  if (statusEl) { statusEl.className = 'text-xs text-gray-400'; statusEl.textContent = '⏳ Yükleniyor...'; }

  try {
    // 1) Upload file to server
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${API_BASE}/files/upload-texture`, {
      method: 'POST', body: fd, signal: AbortSignal.timeout(20000),
    });
    const d = await res.json();
    if (d.error) throw new Error(d.error);

    const savedPath = d.path;

    // 2) Read file locally for thumbnail (no CORS issue with local FileReader)
    const thumb = await new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = e => {
        const img = new Image();
        img.onload = () => {
          try {
            const c = document.createElement('canvas');
            c.width = c.height = 64;
            const ctx = c.getContext('2d');
            const side = Math.min(img.naturalWidth, img.naturalHeight);
            ctx.drawImage(img, (img.naturalWidth-side)/2, (img.naturalHeight-side)/2, side, side, 0, 0, 64, 64);
            resolve(c.toDataURL('image/jpeg', 0.7));
          } catch { resolve(null); }
        };
        img.onerror = () => resolve(null);
        img.src = e.target.result;
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(file);
    });

    // 3) Save as preset
    const name = file.name.replace(/\.[^.]+$/, '').replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).slice(0, 32);
    const mat = { mode: 'file', texture_path: savedPath, thumbnail: thumb };
    _lastMaterial = mat;
    await persistMaterialSet(name, mat);
    _showMatCurrent('Resim: ' + name);
    renderSavedSets();

    if (statusEl) { statusEl.className = 'text-xs text-green-700 font-medium'; statusEl.textContent = `✓ "${name}" eklendi`; }
    setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 3000);
  } catch (e) {
    if (statusEl) { statusEl.className = 'text-xs text-red-500'; statusEl.textContent = `❌ ${e.message}`; }
  } finally {
    input.value = '';
  }
}

function _showMatCurrent(desc) {
  document.getElementById('mat-current-desc').textContent = desc;
  document.getElementById('mat-current').classList.remove('hidden');
}

async function refreshMatTargets() {
  const sel = document.getElementById('mat-target-select');
  try {
    const res  = await fetch(`${API_BASE}/blender/scene/analyze`, { signal: AbortSignal.timeout(10000) });
    const data = await res.json();
    if (data.error || !data.objects) return;
    const meshes = (data.objects || []).filter(o => o.visible !== false);
    if (!meshes.length) return;
    sel.innerHTML = meshes.map(o =>
      `<option value="${o.name}"${o.name === 'Room_Floor' ? ' selected' : ''}>${o.name}</option>`
    ).join('');
  } catch (e) { /* keep defaults */ }
}

async function applyMaterialToTarget() {
  if (!_lastMaterial) { alert('Önce bir materyal kaydedin veya üretin.'); return; }
  const target = document.getElementById('mat-target-select').value;
  if (!target) { alert('Hedef obje seçin.'); return; }
  const iconEl   = document.getElementById('mat-apply-icon');
  const labelEl  = document.getElementById('mat-apply-label');
  const resultEl = document.getElementById('mat-apply-result');
  const btn      = document.getElementById('btn-mat-apply');
  await _doApplyMaterial([target], iconEl, labelEl, resultEl, btn);
}

async function applyLastMaterialToGroup() {
  if (!_lastMaterial) { alert('Önce Materyal sekmesinden bir materyal kaydedin.'); return; }
  if (_selectedGroupIdx === null) return;
  const group = _sceneGroups[_selectedGroupIdx];
  const names = group.items.map(i => i.name);
  const resultEl = document.getElementById('scene-mat-result');
  await _doApplyMaterial(names, null, null, resultEl, null);
}

// ── Texture Gallery (visual picker) ───────────────────────────
let _texGalleryList = [];
let _texGalleryOpen = true;

async function loadTextureGallery() {
  const grid   = document.getElementById('tex-gallery-grid');
  const badge  = document.getElementById('tex-gallery-count');
  if (!grid) return;

  grid.innerHTML = `<div class="col-span-full flex items-center gap-2 text-gray-400 text-xs py-4 justify-center">
    <div class="spinner-xs"></div> Textureler taranıyor...
  </div>`;

  try {
    const res  = await fetch(`${API_BASE}/files/textures`, { signal: AbortSignal.timeout(8000) });
    const data = await res.json();
    const list = (data.textures || []).filter(t =>
      /\.(jpg|jpeg|png|webp)$/i.test(t.name)
    );
    _texGalleryList = list;
    if (badge) badge.textContent = list.length;
    if (!list.length) {
      grid.innerHTML = '<p class="col-span-full text-xs text-gray-400 text-center py-4">models/ altında JPG/PNG texture bulunamadı.</p>';
      return;
    }
    _renderTextureGallery(list);
  } catch (e) {
    grid.innerHTML = `<p class="col-span-full text-xs text-red-400 text-center py-4">Yüklenemedi: ${e.message}</p>`;
  }
}

function _renderTextureGallery(list, filter = '') {
  const grid = document.getElementById('tex-gallery-grid');
  if (!grid) return;
  const lo = filter.toLowerCase();
  const visible = filter ? list.filter(t => t.rel.toLowerCase().includes(lo)) : list;

  if (!visible.length) {
    grid.innerHTML = '<p class="col-span-full text-xs text-gray-400 text-center py-4">Eşleşen texture yok.</p>';
    return;
  }

  grid.innerHTML = visible.map(t => {
    const imgSrc = `${API_BASE}/files/texture-image?path=${encodeURIComponent(t.path)}`;
    const shortName = t.name.replace(/\.[^.]+$/, '').replace(/_/g, ' ').slice(0, 28);
    return `<div class="tex-card group relative cursor-pointer rounded-xl overflow-hidden border-2 border-transparent hover:border-indigo-400 transition-all select-none"
        id="texcard-${encodeURIComponent(t.path).slice(0,20)}"
        onclick="selectTextureCard(${JSON.stringify(t.path)}, this)"
        title="${t.rel}">
      <img src="${imgSrc}"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"
        class="w-full aspect-square object-cover" />
      <div class="w-full aspect-square bg-gradient-to-br from-gray-200 to-gray-400 items-center justify-center" style="display:none">
        <span class="text-[10px] text-gray-600 text-center px-1 leading-tight">${shortName}</span>
      </div>
      <div class="absolute bottom-0 inset-x-0 bg-black/60 px-1.5 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <p class="text-[9px] text-white truncate">${shortName}</p>
      </div>
      <div class="tex-check absolute top-1 right-1 w-5 h-5 bg-indigo-600 rounded-full items-center justify-center text-white text-xs hidden">✓</div>
    </div>`;
  }).join('');
}

function filterTextureGallery(val) {
  _renderTextureGallery(_texGalleryList, val);
}

function selectTextureCard(path, el) {
  // Deselect all
  document.querySelectorAll('.tex-card').forEach(c => {
    c.classList.remove('border-indigo-500', 'ring-2', 'ring-indigo-300');
    c.querySelector('.tex-check')?.classList.add('hidden');
    c.querySelector('.tex-check')?.classList.remove('flex');
  });
  // Select this
  el.classList.add('border-indigo-500', 'ring-2', 'ring-indigo-300');
  el.querySelector('.tex-check')?.classList.remove('hidden');
  el.querySelector('.tex-check')?.classList.add('flex');

  // Grab thumbnail from already-loaded <img> in the card (no extra fetch)
  const imgEl = el.querySelector('img');
  let thumb = null;
  if (imgEl && imgEl.complete && imgEl.naturalWidth > 0) {
    try {
      const c = document.createElement('canvas');
      c.width = c.height = 64;
      c.getContext('2d').drawImage(imgEl, 0, 0, 64, 64);
      thumb = c.toDataURL('image/jpeg', 0.7);
    } catch { /* cross-origin guard — thumb stays null */ }
  }

  // Set material with embedded thumbnail
  _lastMaterial = { mode: 'file', texture_path: path, thumbnail: thumb };
  const name = path.split(/[\\/]/).pop().replace(/\.[^.]+$/, '').replace(/_/g,' ').slice(0,32);
  _showMatCurrent('Texture: ' + name);

  // Flash the status
  const statusEl = document.getElementById('tex-gallery-status');
  if (statusEl) {
    statusEl.className = 'text-xs text-indigo-600 font-medium';
    statusEl.textContent = '✓ ' + name + ' seçildi — aşağıdan uygulayın';
    setTimeout(() => { statusEl.textContent = ''; }, 3000);
  }
}

function toggleTexGallery() {
  _texGalleryOpen = !_texGalleryOpen;
  document.getElementById('tex-gallery-body').classList.toggle('hidden', !_texGalleryOpen);
  document.getElementById('tex-gallery-arrow').style.transform = _texGalleryOpen ? '' : 'rotate(-90deg)';
}

// ── Room Structure quick-apply ─────────────────────────────────
// Fetches floor + walls from Blender and renders them as one-click material targets.

async function loadRoomStructureForMat() {
  const panel = document.getElementById('mat-room-panel');
  const body  = document.getElementById('mat-room-body');
  if (!panel || !body) return;

  body.innerHTML = `<div class="flex items-center gap-2 text-gray-400 text-xs py-2">
    <div class="spinner-xs"></div> Sahne taranıyor...
  </div>`;
  panel.classList.remove('hidden');

  try {
    const res  = await fetch(`${API_BASE}/blender/scene/analyze`, { signal: AbortSignal.timeout(8000) });
    const data = await res.json();
    if (data.error) { panel.classList.add('hidden'); return; }

    const roomGroup = (data.groups || []).find(g => g.display_name === 'Oda Yapısı');
    if (!roomGroup || !roomGroup.items.length) { panel.classList.add('hidden'); return; }

    const floors = roomGroup.items.filter(o => o.name === 'Room_Floor');
    const walls  = roomGroup.items.filter(o => o.name !== 'Room_Floor');

    if (!floors.length && !walls.length) { panel.classList.add('hidden'); return; }

    const cardinalMap = { North:'↑ Kuzey', South:'↓ Güney', East:'→ Doğu', West:'← Batı' };

    const rows = [];

    // ── Zemin ────────────────────────────────────────────────────
    if (floors.length) {
      const fl = floors[0];
      const area = ((fl.dims_m[0]||0)*(fl.dims_m[1]||0)).toFixed(1);
      rows.push(`
        <div class="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-xl">
          <span style="width:10px;height:10px;background:#d97706;border-radius:3px;flex-shrink:0;display:inline-block"></span>
          <div class="flex-1 min-w-0">
            <p class="text-xs font-semibold text-amber-900">Zemin</p>
            <p class="text-[10px] text-amber-700 font-mono">${(fl.dims_m[0]||0).toFixed(2)}×${(fl.dims_m[1]||0).toFixed(2)}m · ${area}m²</p>
          </div>
          <button onclick="matApplyToNames(['Room_Floor'],'Zemin')"
            class="text-xs px-3 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-medium transition-colors whitespace-nowrap">
            🎨 Uygula
          </button>
        </div>`);
    }

    // ── Duvarlar ─────────────────────────────────────────────────
    const wallNames = walls.map(w => w.name);
    walls.forEach(wall => {
      const suffix = wall.name.replace('Room_Wall_', '');
      const label  = cardinalMap[suffix] || suffix;
      const len = (wall.dims_m[0]||0).toFixed(2);
      const h   = (wall.dims_m[2]||0).toFixed(2);
      rows.push(`
        <div class="flex items-center gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl">
          <span style="width:8px;height:22px;background:#475569;border-radius:2px;flex-shrink:0;display:inline-block"></span>
          <div class="flex-1 min-w-0">
            <p class="text-xs font-semibold text-slate-800">${label} Duvarı</p>
            <p class="text-[10px] text-slate-500 font-mono">${len}m × ${h}m</p>
          </div>
          <button onclick="matApplyToNames(['${wall.name}'],'${label} Duvarı')"
            class="text-xs px-3 py-1 bg-slate-500 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors whitespace-nowrap">
            🎨 Uygula
          </button>
        </div>`);
    });

    // ── Toplu butonlar ───────────────────────────────────────────
    const allNames = [...floors.map(f=>f.name), ...wallNames];
    const bulkBtns = [];
    if (walls.length > 1) {
      bulkBtns.push(`<button onclick="matApplyToNames(${JSON.stringify(wallNames)},'Tüm Duvarlar')"
        class="flex-1 py-1.5 rounded-lg text-xs font-semibold bg-slate-200 hover:bg-slate-300 text-slate-800 transition-colors">
        🧱 Tüm Duvarlar (${walls.length})
      </button>`);
    }
    if (floors.length && walls.length) {
      bulkBtns.push(`<button onclick="matApplyToNames(${JSON.stringify(allNames)},'Zemin + Duvarlar')"
        class="flex-1 py-1.5 rounded-lg text-xs font-semibold bg-indigo-100 hover:bg-indigo-200 text-indigo-800 transition-colors">
        🏠 Zemin + Duvarlar
      </button>`);
    }
    if (bulkBtns.length) {
      rows.push(`<div class="flex gap-2 mt-1">${bulkBtns.join('')}</div>`);
    }

    body.innerHTML = rows.join('');
  } catch (e) {
    panel.classList.add('hidden');
  }
}

async function matApplyToNames(names, label) {
  if (!_lastMaterial) {
    alert('Önce bir materyal kaydedin veya üretin (Dosyadan / AI bölümü).');
    return;
  }
  const statusEl = document.getElementById('mat-room-status');
  if (statusEl) { statusEl.className = 'text-xs text-gray-400'; statusEl.textContent = `⏳ ${label} uygulanıyor...`; }
  try {
    const res = await fetch(`${API_BASE}/blender/apply-material`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ object_names: names, ..._lastMaterial }),
      signal: AbortSignal.timeout(30000),
    });
    const d = await res.json();
    if (statusEl) {
      if (d.error) {
        statusEl.className = 'text-xs text-red-600'; statusEl.textContent = `❌ ${d.error}`;
      } else {
        statusEl.className = 'text-xs text-green-700 font-medium'; statusEl.textContent = `✓ ${label} uygulandı`;
        setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 3000);
      }
    }
  } catch (e) {
    if (statusEl) { statusEl.className = 'text-xs text-red-600'; statusEl.textContent = `❌ ${e.message}`; }
  }
}

async function _doApplyMaterial(objectNames, iconEl, labelEl, resultEl, btn) {
  if (btn) btn.disabled = true;
  if (iconEl)  iconEl.textContent  = '⏳';
  if (labelEl) labelEl.textContent = 'Uygulanıyor...';
  if (resultEl) resultEl.textContent = '';
  try {
    const res = await fetch(`${API_BASE}/blender/apply-material`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ object_names: objectNames, ..._lastMaterial }),
      signal: AbortSignal.timeout(50000),
    });
    const data = await res.json();
    if (data.error) {
      if (resultEl) { resultEl.className = 'text-xs text-red-600 flex-1'; resultEl.textContent = `❌ ${data.error}`; }
    } else {
      if (resultEl) { resultEl.className = 'text-xs text-green-700 font-medium flex-1'; resultEl.textContent = `✓ Uygulandı: ${objectNames.join(', ')}`; }
    }
  } catch (e) {
    if (resultEl) { resultEl.className = 'text-xs text-red-600 flex-1'; resultEl.textContent = `❌ ${e.message}`; }
  } finally {
    if (btn) btn.disabled = false;
    if (iconEl)  iconEl.textContent  = '🎨';
    if (labelEl) labelEl.textContent = 'Uygula';
  }
}
