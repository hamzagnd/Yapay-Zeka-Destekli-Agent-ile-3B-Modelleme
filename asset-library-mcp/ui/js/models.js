// ── models.js ─────────────────────────────────────────────────────
// Modeller tab: loading, grid rendering, filtering, selection, inserting to prompt.
// Also handles "Model Üret" (AI 3D model generation) panel.

// ── Model Üret ────────────────────────────────────────────────────
function toggleGenPanel() {
  _gmPanelOpen = !_gmPanelOpen;
  document.getElementById('gen-panel-body').classList.toggle('hidden', !_gmPanelOpen);
  document.getElementById('gen-panel-arrow').style.transform = _gmPanelOpen ? '' : 'rotate(-90deg)';
}

function selectGenModelLLM(llm) {
  _gmLLM = llm;
  ['gemini', 'claude'].forEach(id => {
    const btn = document.getElementById(`gm-llm-${id}`);
    const active = id === llm;
    btn.classList.toggle('border-indigo-500', active);
    btn.classList.toggle('text-indigo-700',   active);
    btn.classList.toggle('border-gray-300',   !active);
    btn.classList.toggle('text-gray-500',     !active);
  });
}

async function readCursorForGen() {
  const codeEl = document.getElementById('gm-cursor-pos');
  try {
    const r    = await fetch(`${API_BASE}/blender/cursor`, { signal: AbortSignal.timeout(5000) });
    const data = await r.json();
    const text = data.result || '';
    const m    = text.match(/\[([^\]]+)\]/);
    if (m) {
      _gmCursorPos = m[1].split(',').map(Number);
      codeEl.textContent = `[${_gmCursorPos.map(v => v.toFixed(2)).join(', ')}]`;
      codeEl.className = 'font-mono text-emerald-600';
    }
  } catch {
    codeEl.textContent = 'Blender bağlı değil';
    codeEl.className = 'font-mono text-red-500';
  }
}

async function generateModel() {
  const prompt  = (document.getElementById('gm-prompt')?.value || '').trim();
  const btn     = document.getElementById('btn-generate-model');
  const icon    = document.getElementById('gm-icon');
  const label   = document.getElementById('gm-label');
  const status  = document.getElementById('gm-status');

  if (!prompt) {
    status.className = 'text-sm text-red-500';
    status.textContent = 'Bir model açıklaması yazın.';
    return;
  }

  btn.disabled = true;
  icon.textContent  = '⏳';
  label.textContent = 'Üretiliyor...';
  status.className  = 'text-sm text-gray-400';
  status.textContent = `${_gmLLM === 'claude' ? 'Claude' : 'Gemini'} Blender scripti yazıyor...`;
  document.getElementById('gm-result-panel').classList.add('hidden');
  // Reset save info box for new generation
  const pendingEl = document.getElementById('gm-save-pending');
  const pathRowEl = document.getElementById('gm-save-path-row');
  const badgeEl   = document.getElementById('gm-save-badge');
  const addBtn    = document.getElementById('btn-add-to-scene');
  if (pendingEl) { pendingEl.textContent = '⏳ Dosya kaydediliyor...'; pendingEl.className = 'mt-1 text-blue-500'; pendingEl.classList.remove('hidden'); }
  if (pathRowEl) pathRowEl.classList.add('hidden');
  if (badgeEl)   badgeEl.classList.add('hidden');
  if (addBtn)    delete addBtn.dataset.assetId;
  document.getElementById('gm-add-scene-status')?.classList.add('hidden');

  try {
    const res  = await fetch(`${API_BASE}/blender/generate-model`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ prompt, llm: _gmLLM, position: _gmCursorPos }),
      signal:  AbortSignal.timeout(60000),
    });
    const data = await res.json();

    if (data.error) {
      status.className  = 'text-sm text-red-500';
      status.textContent = `❌ ${data.error}`;
      if (data.script) _showGenScript(data.script);
    } else {
      _gmLastObjName = data.obj_name;
      status.className  = 'text-sm text-emerald-600 font-medium';
      status.textContent = `✓ Blender'a eklendi → ${data.obj_name}`;

      document.getElementById('gm-result-name').textContent = data.obj_name;
      const posStr = `[${_gmCursorPos.map(v => v.toFixed(2)).join(', ')}]`;
      const posEl = document.getElementById('gm-result-pos');
      if (posEl) posEl.textContent = posStr;
      _showGenScript(data.script || '');
      document.getElementById('gm-result-panel').classList.remove('hidden');
      document.getElementById('gm-refine-prompt').value = '';
      document.getElementById('gm-refine-status').textContent = '';

      // Add to history
      _gmHistory.unshift({ obj_name: data.obj_name, prompt, ts: new Date().toLocaleTimeString('tr-TR') });
      if (_gmHistory.length > 8) _gmHistory.pop();
      _renderGenHistory();

      // Auto-save to catalog in background
      _autoSaveGeneratedModel(data.obj_name, prompt);
    }
  } catch (e) {
    const isTimeout = e.name === 'TimeoutError' || e.name === 'AbortError';
    status.className  = 'text-sm text-red-500';
    status.textContent = isTimeout ? '⚠ Zaman aşımı — LLM çok uzun sürdü, tekrar dene.' : `❌ ${e.message}`;
  } finally {
    btn.disabled = false;
    icon.textContent  = '✨';
    label.textContent = 'Üret';
  }
}

async function refineGeneratedModel() {
  const refinePrompt = (document.getElementById('gm-refine-prompt')?.value || '').trim();
  const btn          = document.getElementById('btn-refine-model');
  const icon         = document.getElementById('gm-refine-icon');
  const label        = document.getElementById('gm-refine-label');
  const status       = document.getElementById('gm-refine-status');

  if (!refinePrompt) {
    status.className = 'text-xs text-red-500';
    status.textContent = 'Düzeltme açıklaması yazın.';
    return;
  }
  if (!_gmLastObjName) {
    status.className = 'text-xs text-red-500';
    status.textContent = 'Önce bir model üret.';
    return;
  }

  btn.disabled = true;
  icon.textContent  = '⏳';
  label.textContent = 'Uygulanıyor...';
  status.className  = 'text-xs text-gray-400';
  status.textContent = 'LLM düzeltme scripti yazıyor...';

  try {
    const res  = await fetch(`${API_BASE}/blender/modify-object`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        object_names: [_gmLastObjName],
        group_name:   _gmLastObjName,
        prompt:       refinePrompt,
        llm:          _gmLLM,
      }),
      signal: AbortSignal.timeout(60000),
    });
    const data = await res.json();

    if (data.error) {
      status.className  = 'text-xs text-red-500';
      status.textContent = `❌ ${data.error}`;
    } else {
      status.className  = 'text-xs text-emerald-600 font-medium';
      status.textContent = '✓ Uygulandı';
      if (data.script) _showGenScript(data.script);
      document.getElementById('gm-refine-prompt').value = '';
    }
  } catch (e) {
    status.className  = 'text-xs text-red-500';
    status.textContent = `❌ ${e.message}`;
  } finally {
    btn.disabled = false;
    icon.textContent  = '🔧';
    label.textContent = 'Uygula';
  }
}

async function _autoSaveGeneratedModel(objName, prompt) {
  const statusEl  = document.getElementById('gm-status');
  const pendingEl = document.getElementById('gm-save-pending');
  const pathRowEl = document.getElementById('gm-save-path-row');
  const pathEl    = document.getElementById('gm-save-path');
  const badgeEl   = document.getElementById('gm-save-badge');

  if (statusEl) { statusEl.className = 'text-sm text-gray-400'; statusEl.textContent = '💾 Kaydediliyor...'; }

  try {
    const r = await fetch(`${API_BASE}/blender/save-generated-model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ obj_name: objName, prompt }),
      signal: AbortSignal.timeout(25000),
    });
    const d = await r.json();

    if (d.ok) {
      // Store asset_id for "Sahneye Ekle" button
      const addBtn = document.getElementById('btn-add-to-scene');
      if (addBtn) addBtn.dataset.assetId = d.asset_id;

      // Update save info box
      if (pendingEl) pendingEl.classList.add('hidden');
      if (pathEl && d.file) {
        const fullPath = `asset_library\\${d.file.replace(/\//g, '\\')}`;
        pathEl.textContent = fullPath;
        if (pathRowEl) pathRowEl.classList.remove('hidden');
      }
      if (badgeEl) badgeEl.classList.remove('hidden');

      // Update header name
      const nameEl = document.getElementById('gm-result-name');
      if (nameEl) nameEl.textContent = `${objName}  ·  katalog: ${d.asset_id}`;

      if (statusEl) { statusEl.className = 'text-sm text-emerald-600 font-medium'; statusEl.textContent = `✓ Kaydedildi → ${d.asset_id}`; }

      // Refresh catalogs
      if (typeof loadYapbozCatalog === 'function') loadYapbozCatalog();
      if (typeof loadModelsTab === 'function') loadModelsTab(true);
    } else {
      if (pendingEl) { pendingEl.textContent = `⚠ Kayıt başarısız: ${d.error}`; pendingEl.className = 'mt-1 text-amber-600'; }
      if (statusEl) { statusEl.className = 'text-sm text-amber-500'; statusEl.textContent = `⚠ ${d.error}`; }
    }
  } catch (e) {
    if (pendingEl) { pendingEl.textContent = `⚠ Kayıt hatası: ${e.message}`; pendingEl.className = 'mt-1 text-amber-600'; }
    if (statusEl) { statusEl.className = 'text-sm text-amber-500'; statusEl.textContent = `⚠ Kayıt hatası`; }
  }
}

// "📥 Sahneye Ekle" — kaydedilmiş blend dosyasını Blender'a import eder
async function addSavedModelToScene() {
  const btn     = document.getElementById('btn-add-to-scene');
  const statusEl = document.getElementById('gm-add-scene-status');
  const assetId = btn?.dataset.assetId || _gmLastObjName;

  if (!assetId) {
    if (statusEl) { statusEl.className = 'text-[11px] text-red-500'; statusEl.textContent = '❌ Önce bir model üret ve kaydet.'; statusEl.classList.remove('hidden'); }
    return;
  }

  if (btn) btn.disabled = true;
  if (statusEl) { statusEl.className = 'text-[11px] text-gray-400'; statusEl.textContent = 'Blender\'a ekleniyor...'; statusEl.classList.remove('hidden'); }

  try {
    const r = await fetch(`${API_BASE}/blender/import-model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: assetId, location: _gmCursorPos }),
      signal: AbortSignal.timeout(30000),
    });
    const d = await r.json();

    if (d.ok) {
      if (statusEl) { statusEl.className = 'text-[11px] text-emerald-600 font-semibold'; statusEl.textContent = `✓ Sahneye eklendi → ${d.obj_name}`; }
      _gmLastObjName = d.obj_name;
    } else {
      if (statusEl) { statusEl.className = 'text-[11px] text-red-500'; statusEl.textContent = `❌ ${d.error}`; }
    }
  } catch (e) {
    if (statusEl) { statusEl.className = 'text-[11px] text-red-500'; statusEl.textContent = `❌ ${e.message}`; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _showGenScript(script) {
  document.getElementById('gm-script-code').textContent = script;
}

// Switch to Sahne tab and refresh to show the generated model
async function findGeneratedModelInScene() {
  if (typeof switchTab === 'function') switchTab('sahne');
  if (typeof loadBlenderScene === 'function') {
    setTimeout(loadBlenderScene, 300);
  }
}

// Tell Blender to select and frame the generated object in the viewport
async function focusGeneratedModel() {
  if (!_gmLastObjName) return;
  const script = `
import bpy
obj = bpy.data.objects.get(${JSON.stringify(_gmLastObjName)})
if not obj:
    # Try prefix match
    for o in bpy.data.objects:
        if o.name.startswith('GM_'):
            obj = o
            break
if obj:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # Frame it in all 3D viewports
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            with bpy.context.temp_override(area=area, region=area.regions[-1]):
                bpy.ops.view3d.view_selected()
            break
`;
  try {
    const r = await fetch(`${API_BASE}/blender/run-script`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
      signal: AbortSignal.timeout(8000),
    });
    const d = await r.json();
    if (d.error) {
      document.getElementById('gm-status').textContent = `❌ ${d.error}`;
    } else {
      document.getElementById('gm-status').textContent = `✓ Blender'da "${_gmLastObjName}" seçildi`;
    }
  } catch (e) {
    // Fallback: just switch to scene tab
    findGeneratedModelInScene();
  }
}

function _renderGenHistory() {
  const wrap = document.getElementById('gm-history');
  const list = document.getElementById('gm-history-list');
  if (!_gmHistory.length) { wrap.classList.add('hidden'); return; }
  wrap.classList.remove('hidden');
  list.innerHTML = _gmHistory.map(h =>
    `<button onclick="selectHistoryModel('${h.obj_name}')"
      class="px-3 py-1.5 bg-gray-100 hover:bg-indigo-50 hover:text-indigo-700 border border-gray-200 hover:border-indigo-300 rounded-lg text-xs transition-all text-left">
      <span class="font-mono text-gray-500 block text-[10px]">${h.obj_name}</span>
      <span class="text-gray-700 truncate block max-w-32">${h.prompt}</span>
      <span class="text-gray-400 text-[10px]">${h.ts}</span>
    </button>`
  ).join('');
}

function selectHistoryModel(objName) {
  _gmLastObjName = objName;
  document.getElementById('gm-result-name').textContent = objName;
  document.getElementById('gm-result-panel').classList.remove('hidden');
  document.getElementById('gm-refine-status').textContent = '';
  document.getElementById('gm-status').textContent = `Aktif model: ${objName}`;
  document.getElementById('gm-status').className = 'text-sm text-indigo-600';
}

// ── Source Switch (Local / Sketchfab) ──────────────────────────────

function setModelSource(source) {
  _modelSource = source;
  
  // Update buttons
  const localBtn = document.getElementById('btn-src-local');
  const sfBtn    = document.getElementById('btn-src-sf');
  
  const activeClass = 'border-indigo-500 bg-indigo-50 text-indigo-700 shadow-sm';
  const inactiveClass = 'border-gray-100 bg-white text-gray-400';
  
  if (source === 'local') {
    localBtn.className = `flex-1 py-2.5 rounded-2xl text-sm font-bold border-2 ${activeClass} transition-all`;
    sfBtn.className    = `flex-1 py-2.5 rounded-2xl text-sm font-bold border-2 ${inactiveClass} transition-all`;
    renderModelsGrid();
  } else {
    localBtn.className = `flex-1 py-2.5 rounded-2xl text-sm font-bold border-2 ${inactiveClass} transition-all`;
    sfBtn.className    = `flex-1 py-2.5 rounded-2xl text-sm font-bold border-2 ${activeClass} transition-all`;
    // Switch to Sketchfab tab automatically
    switchTab('sketchfab');
    if (!_sfResults.length) {
      document.getElementById('sf-search-input')?.focus();
    }
  }
}

async function loadModelsTab(force = false) {
  if (_modelsLoaded && !force) return;
  const grid = document.getElementById('models-grid');
  grid.innerHTML = `<div class="col-span-full text-center py-16 text-gray-400">
    <div class="spinner mx-auto mb-3"></div>
    <p class="text-sm mt-2">Katalog yükleniyor...</p>
  </div>`;

  try {
    // Use JSON endpoint (includes file_exists field)
    const res  = await fetch(`${API_BASE}/asset-manager/catalog`, { signal: AbortSignal.timeout(8000) });
    const data = await res.json();

    _allModels = (data.assets || []).map(a => ({
      id:          a.id          || '',
      name:        a.name        || a.id || '',
      category:    a.category    || '',
      subcategory: a.subcategory || '',
      style:       Array.isArray(a.style) ? a.style.join(', ') : (a.style || ''),
      dims:        a.dimensions
                     ? `${a.dimensions.width ?? '?'}w × ${a.dimensions.depth ?? '?'}d × ${a.dimensions.height ?? '?'}h m`
                     : '',
      file_exists: a.file_exists !== false,
      proportion_warning: a.proportion_warning === true,
      room_types:  Array.isArray(a.room_types) ? a.room_types : [],
    })).filter(m => m.id);

    _modelsLoaded = true;
    _populateModelStyleFilters();
    renderModelsGrid();
  } catch (e) {
    grid.innerHTML = `<div class="col-span-full text-center py-16 text-red-500">
      <div class="text-3xl mb-2">❌</div>
      <p class="text-sm">Katalog yüklenemedi: ${e.message}</p>
      <p class="text-xs text-gray-400 mt-1">API çalışıyor mu? python run_team.py --serve</p>
    </div>`;
  }
}

function _populateModelStyleFilters() {
  const styles = [...new Set(_allModels.flatMap(m =>
    m.style ? m.style.split(',').map(s => s.trim()).filter(Boolean) : []
  ))].sort();

  const container = document.getElementById('mf-style-btns');
  container.innerHTML = '';
  if (!styles.length) return;

  const allBtn = document.createElement('button');
  allBtn.dataset.mfStyle = '';
  allBtn.className = 'mf-style-btn px-3 py-1.5 rounded-full text-xs font-semibold bg-amber-500 text-white shadow-sm transition-all';
  allBtn.textContent = 'Stil: Tümü';
  allBtn.onclick = () => filterModelsStyle('');
  container.appendChild(allBtn);

  styles.forEach(s => {
    const btn = document.createElement('button');
    btn.dataset.mfStyle = s;
    btn.className = 'mf-style-btn px-3 py-1.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600 hover:bg-gray-200 transition-all';
    btn.textContent = s;
    btn.onclick = () => filterModelsStyle(s);
    container.appendChild(btn);
  });
}

function renderModelsGrid() {
  const grid  = document.getElementById('models-grid');
  const empty = document.getElementById('models-empty');
  const lo = _mfSearch.toLowerCase();

  const visible = _allModels.filter(m => {
    if (_mfCat   && m.category   !== _mfCat)   return false;
    if (_mfStyle && !m.style.toLowerCase().includes(_mfStyle.toLowerCase())) return false;
    if (lo && !m.name.toLowerCase().includes(lo) &&
              !m.id.toLowerCase().includes(lo)   &&
              !m.subcategory.toLowerCase().includes(lo)) return false;
    return true;
  });

  if (!visible.length) {
    grid.innerHTML  = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  grid.innerHTML = visible.map(m => {
    // ── Eksik dosya kartı ─────────────────────────────────────────
    if (!m.file_exists) {
      return `<div class="model-card bg-gray-50 rounded-2xl border-2 border-dashed border-red-200 overflow-hidden flex flex-col opacity-70">
        <div class="flex flex-col items-center justify-center gap-1.5 bg-red-50" style="height:140px">
          <span class="text-3xl">⚠️</span>
          <p class="text-xs text-red-500 font-semibold">Dosya bulunamadı</p>
        </div>
        <div class="p-3 flex-1">
          <p class="font-semibold text-sm text-gray-500 line-clamp-2">${m.name}</p>
          <p class="text-[10px] text-gray-400 font-mono mt-0.5 truncate">${m.id}</p>
          <p class="text-[10px] text-red-400 mt-1">Bu model kaydedilmemiş veya dosya silinmiş.</p>
        </div>
        <div class="px-3 pb-3 flex gap-1.5">
          <button onclick="deleteCatalogEntry('${m.id}')"
            class="flex-1 py-1.5 rounded-lg text-xs font-semibold bg-red-100 hover:bg-red-200 text-red-700 transition-colors">
            🗑 Katalogdan Kaldır
          </button>
          <button onclick="toggleEditPanel('${m.id}')" title="İsim/ID düzenle"
            class="w-7 h-7 flex items-center justify-center rounded-lg border border-gray-200 text-gray-400 hover:border-violet-300 hover:text-violet-500 text-sm transition-all">
            ✏
          </button>
        </div>
        ${_editPanelId === m.id ? _editPanelHTML(m) : ''}
      </div>`;
    }

    const grad     = _CAT_GRAD[m.category] || 'from-slate-400 to-slate-600';
    const letter   = m.name.charAt(0).toUpperCase();
    const selected = !!_modelSelections[m.id];
    const qty      = selected ? _modelSelections[m.id].qty : 1;
    const styleTag = m.style ? m.style.split(',').slice(0, 2).map(s =>
      `<span class="inline-block bg-gray-100 text-gray-500 text-[10px] px-1.5 py-0.5 rounded-full">${s.trim()}</span>`
    ).join('') : '';

    return `<div id="mcard-${m.id}"
      class="model-card bg-white rounded-2xl shadow-sm border-2 ${selected ? 'border-indigo-500 shadow-indigo-100' : 'border-gray-100'} overflow-hidden flex flex-col transition-all hover:shadow-md hover:-translate-y-0.5">

      <div class="relative overflow-hidden" style="height:140px">
        <img src="${API_BASE}/thumbnails/${m.id}.jpg"
          onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"
          class="w-full h-full object-cover" style="height:140px" />
        <div class="w-full h-full bg-gradient-to-br ${grad} items-center justify-center text-white" style="display:none;height:140px">
          <div class="text-center">
            <div class="text-4xl font-bold opacity-90">${letter}</div>
            <div class="text-xs opacity-70 mt-1">${_CAT_LABEL[m.category] || m.category}</div>
          </div>
        </div>
        ${selected ? `<div class="absolute top-2 right-2 bg-indigo-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold shadow">✓</div>` : ''}
        ${m.proportion_warning ? `<div class="absolute top-2 left-2 bg-amber-500 text-white text-[10px] px-2 py-0.5 rounded-full shadow font-semibold" title="Bu modelin iç parçaları orantısız — AI ile Düzelt ile onarabilirsiniz">⚠ orantı</div>` : ''}
        ${m.subcategory ? `<div class="absolute bottom-2 left-2 bg-black/50 text-white text-[10px] px-2 py-0.5 rounded-full backdrop-blur-sm">${m.subcategory}</div>` : ''}
      </div>

      <div class="p-3 flex flex-col gap-1.5 flex-1">
        <p class="font-semibold text-sm text-gray-800 leading-tight line-clamp-2">${m.name}</p>
        <p class="text-[10px] text-gray-400 font-mono truncate">${m.id}</p>
        ${styleTag ? `<div class="flex gap-1 flex-wrap">${styleTag}</div>` : ''}
        ${m.dims ? `<p class="text-[10px] text-gray-400">${m.dims}</p>` : ''}
      </div>

      <div class="px-3 pb-3 flex items-center gap-2">
        <div class="flex items-center gap-1 bg-gray-100 rounded-lg px-1 py-1 text-sm font-semibold text-gray-700">
          <button onclick="changeModelQty('${m.id}', -1)"
            class="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-200 transition-colors text-base leading-none">−</button>
          <span id="mqty-${m.id}" class="w-5 text-center text-sm">${qty}</span>
          <button onclick="changeModelQty('${m.id}', 1)"
            class="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-200 transition-colors text-base leading-none">+</button>
        </div>
        <button onclick="toggleModelCard('${m.id}')"
          class="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all ${selected
            ? 'bg-indigo-600 text-white hover:bg-indigo-700'
            : 'bg-gray-100 text-gray-600 hover:bg-indigo-50 hover:text-indigo-700'}">
          ${selected ? '✓ Seçildi' : 'Seç'}
        </button>
        <button onclick="toggleRotPanel('${m.id}')" title="Rotasyon / Eksen Düzelt"
          class="w-7 h-7 flex items-center justify-center rounded-lg text-sm border ${_rotPanelId === m.id
            ? 'bg-orange-100 border-orange-400 text-orange-600'
            : 'border-gray-200 text-gray-400 hover:border-orange-300 hover:text-orange-500'} transition-all">
          ↻
        </button>
        <button onclick="toggleEditPanel('${m.id}')" title="İsim / ID Düzenle"
          class="w-7 h-7 flex items-center justify-center rounded-lg text-sm border ${_editPanelId === m.id
            ? 'bg-violet-100 border-violet-400 text-violet-600'
            : 'border-gray-200 text-gray-400 hover:border-violet-300 hover:text-violet-500'} transition-all">
          ✏
        </button>
        <button onclick="toggleAiFixPanel('${m.id}')" title="AI ile Düzelt"
          class="w-7 h-7 flex items-center justify-center rounded-lg text-sm border ${_aiFixPanelId === m.id
            ? 'bg-indigo-100 border-indigo-400 text-indigo-600'
            : 'border-gray-200 text-gray-400 hover:border-indigo-300 hover:text-indigo-500'} transition-all font-bold">
          ✦
        </button>
        <button onclick="deleteCatalogEntry('${m.id}')" title="Katalogdan Sil"
          class="w-7 h-7 flex items-center justify-center rounded-lg text-sm border border-gray-200 text-gray-400 hover:border-red-300 hover:bg-red-50 hover:text-red-500 transition-all">
          🗑
        </button>
      </div>

      ${_aiFixPanelId === m.id ? _aiFixPanelHTML(m) : ''}
      ${_editPanelId  === m.id ? _editPanelHTML(m)  : ''}
      ${_rotPanelId   === m.id ? _rotPanelHTML(m.id): ''}
    </div>`;
  }).join('');
}

function filterModelsCat(cat) {
  _mfCat = cat;
  document.querySelectorAll('.mf-cat-btn').forEach(btn => {
    const active = btn.dataset.mfCat === cat;
    btn.classList.toggle('bg-indigo-600', active);
    btn.classList.toggle('text-white',    active);
    btn.classList.toggle('shadow-sm',     active);
    btn.classList.toggle('bg-gray-100',   !active);
    btn.classList.toggle('text-gray-600', !active);
  });
  renderModelsGrid();
}

function filterModelsStyle(style) {
  _mfStyle = style;
  document.querySelectorAll('.mf-style-btn').forEach(btn => {
    const active = btn.dataset.mfStyle === style;
    btn.classList.toggle('bg-amber-500',  active);
    btn.classList.toggle('text-white',    active);
    btn.classList.toggle('shadow-sm',     active);
    btn.classList.toggle('bg-gray-100',   !active);
    btn.classList.toggle('text-gray-600', !active);
  });
  renderModelsGrid();
}

function filterModelsSearch(val) {
  _mfSearch = val;
  renderModelsGrid();
}

function toggleModelCard(id) {
  const m = _allModels.find(x => x.id === id);
  if (!m) return;
  if (_modelSelections[id]) {
    delete _modelSelections[id];
  } else {
    _modelSelections[id] = { id, name: m.name, subcategory: m.subcategory, qty: 1 };
  }
  _renderModelSelectionBar();
  renderModelsGrid();
}

function changeModelQty(id, delta) {
  const m = _allModels.find(x => x.id === id);
  if (!m) return;
  if (!_modelSelections[id]) {
    _modelSelections[id] = { id, name: m.name, subcategory: m.subcategory, qty: 1 };
  }
  const newQty = Math.max(1, Math.min(20, _modelSelections[id].qty + delta));
  _modelSelections[id].qty = newQty;
  const qtyEl = document.getElementById(`mqty-${id}`);
  if (qtyEl) qtyEl.textContent = newQty;
  _renderModelSelectionBar();
  const card = document.getElementById(`mcard-${id}`);
  if (card && !card.classList.contains('border-indigo-500')) renderModelsGrid();
}

function _renderModelSelectionBar() {
  const bar     = document.getElementById('model-sel-bar');
  const countEl = document.getElementById('model-sel-count');
  const prevEl  = document.getElementById('model-sel-preview');
  const items   = Object.values(_modelSelections);

  if (!items.length) {
    bar.classList.add('hidden');
    return;
  }
  bar.classList.remove('hidden');
  const totalQty = items.reduce((s, x) => s + x.qty, 0);
  countEl.textContent = `${items.length} model, ${totalQty} adet seçildi`;
  prevEl.textContent  = items.map(x => `${x.name} ×${x.qty}`).join('  ·  ');
}

function clearModelSelections() {
  _modelSelections = {};
  _renderModelSelectionBar();
  renderModelsGrid();
}

// ── AI Fix Panel (inline in model cards) ──────────────────────────

function _aiFixPanelHTML(m) {
  const llmGemini = _aiFixLLM === 'gemini';
  return `<div class="mx-3 mb-3 bg-indigo-50 border border-indigo-200 rounded-xl p-3 text-xs" id="aifix-panel-${m.id}">
    <p class="font-semibold text-indigo-700 mb-2">✦ AI ile Düzelt</p>

    <!-- Step 1: Load to Blender -->
    <div class="flex items-center gap-2 mb-3 bg-white border border-indigo-100 rounded-lg px-3 py-2">
      <div class="flex-1">
        <p class="font-medium text-gray-700 text-[11px]">1. Blender'a yükle</p>
        <p class="text-gray-400 text-[10px]">Modeli sahneye ekle, sonra düzelt</p>
      </div>
      <button onclick="loadModelToBlender('${m.id}')" id="aifix-load-${m.id}"
        class="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap">
        <span id="aifix-load-icon-${m.id}">📥</span>
        <span id="aifix-load-label-${m.id}">Yükle</span>
      </button>
    </div>

    <!-- Step 2: AI prompt -->
    <div class="mb-2">
      <p class="font-medium text-gray-700 text-[11px] mb-1">2. Ne değiştireyim?</p>
      <textarea id="aifix-prompt-${m.id}" rows="2" placeholder="ayaklarını daha ince yap, rengi koyu gri yap, metalik doku ekle..."
        class="w-full border border-indigo-200 rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none bg-white"></textarea>
    </div>

    <!-- LLM selector -->
    <div class="flex gap-1.5 mb-3">
      <button onclick="setAiFixLLM('gemini')"
        class="aifix-llm-btn flex items-center gap-1 px-2.5 py-1 rounded-lg border-2 text-[11px] font-semibold transition-all ${llmGemini ? 'border-indigo-500 text-indigo-700 bg-white' : 'border-gray-200 text-gray-400'}">
        <img src="https://lh3.googleusercontent.com/qnawW1V9XxMqekJBj2cNWIFST39eoiTUAW1kAcFMJwfIVkQlFh_kRw5LvRiUYnPgjb8" onerror="this.style.display='none'" class="w-3.5 h-3.5 rounded" />
        Gemini
      </button>
      <button onclick="setAiFixLLM('claude')"
        class="aifix-llm-btn flex items-center gap-1 px-2.5 py-1 rounded-lg border-2 text-[11px] font-semibold transition-all ${!llmGemini ? 'border-indigo-500 text-indigo-700 bg-white' : 'border-gray-200 text-gray-400'}">
        <span class="text-orange-500 font-bold leading-none">✦</span>
        Claude
      </button>
    </div>

    <div class="flex items-center gap-2">
      <button onclick="applyAiFix('${m.id}')" id="aifix-apply-${m.id}"
        class="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white py-2 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5">
        <span id="aifix-apply-icon-${m.id}">✦</span>
        <span id="aifix-apply-label-${m.id}">AI ile Uygula</span>
      </button>
    </div>
    <p id="aifix-status-${m.id}" class="text-[11px] text-gray-400 mt-2 min-h-4"></p>
  </div>`;
}

function toggleAiFixPanel(id) {
  if (_editPanelId === id) _editPanelId = null;
  if (_rotPanelId  === id) _rotPanelId  = null;
  _aiFixPanelId = (_aiFixPanelId === id) ? null : id;
  renderModelsGrid();
}

function setAiFixLLM(llm) {
  _aiFixLLM = llm;
  // Re-render just the LLM buttons without full grid re-render
  document.querySelectorAll('.aifix-llm-btn').forEach(btn => {
    const isActive = (llm === 'gemini' && btn.textContent.includes('Gemini'))
                  || (llm === 'claude' && btn.textContent.includes('Claude'));
    btn.classList.toggle('border-indigo-500', isActive);
    btn.classList.toggle('text-indigo-700',   isActive);
    btn.classList.toggle('bg-white',          isActive);
    btn.classList.toggle('border-gray-200',   !isActive);
    btn.classList.toggle('text-gray-400',     !isActive);
  });
}

async function loadModelToBlender(modelId) {
  const btn    = document.getElementById(`aifix-load-${modelId}`);
  const icon   = document.getElementById(`aifix-load-icon-${modelId}`);
  const label  = document.getElementById(`aifix-load-label-${modelId}`);
  const status = document.getElementById(`aifix-status-${modelId}`);

  if (btn) btn.disabled = true;
  if (icon)  icon.textContent  = '⏳';
  if (label) label.textContent = 'Yükleniyor...';
  if (status) { status.className = 'text-[11px] text-gray-400 mt-2'; status.textContent = 'Blender\'a gönderiliyor...'; }

  try {
    const importRes = await fetch(`${API_BASE}/blender/import-model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: modelId }),
      signal: AbortSignal.timeout(30000),
    });
    const importData = await importRes.json();

    if (importData.error) throw new Error(importData.error);

    const objName = importData.obj_name || modelId;
    if (status) { status.className = 'text-[11px] text-emerald-600 mt-2 font-semibold'; status.textContent = `✓ Sahneye eklendi → ${objName}`; }
    if (icon)  icon.textContent  = '✓';
    if (label) label.textContent = 'Yüklendi';
    // Store obj_name for applyAiFix to use
    const panel = document.getElementById(`aifix-panel-${modelId}`);
    if (panel) panel.dataset.objName = objName;
  } catch (e) {
    if (status) { status.className = 'text-[11px] text-red-500 mt-2'; status.textContent = `❌ ${e.message}`; }
    if (icon)  icon.textContent  = '📥';
    if (label) label.textContent = 'Tekrar Dene';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function applyAiFix(modelId) {
  const prompt  = (document.getElementById(`aifix-prompt-${modelId}`)?.value || '').trim();
  const btn     = document.getElementById(`aifix-apply-${modelId}`);
  const icon    = document.getElementById(`aifix-apply-icon-${modelId}`);
  const label   = document.getElementById(`aifix-apply-label-${modelId}`);
  const status  = document.getElementById(`aifix-status-${modelId}`);

  if (!prompt) {
    if (status) { status.className = 'text-[11px] text-red-500 mt-2'; status.textContent = 'Bir prompt yazın.'; }
    return;
  }

  if (btn) btn.disabled = true;
  if (icon)  icon.textContent  = '⏳';
  if (label) label.textContent = 'Uygulanıyor...';
  if (status) { status.className = 'text-[11px] text-gray-400 mt-2'; status.textContent = `${_aiFixLLM === 'claude' ? 'Claude' : 'Gemini'} script yazıyor...`; }

  try {
    // Use obj_name stored by loadModelToBlender, fallback to modelId variants
    const panel   = document.getElementById(`aifix-panel-${modelId}`);
    const objName = panel?.dataset.objName || modelId;
    const res = await fetch(`${API_BASE}/blender/modify-object`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        object_names: [objName, modelId],
        group_name:   objName,
        prompt,
        llm:          _aiFixLLM,
      }),
      signal: AbortSignal.timeout(60000),
    });
    const data = await res.json();

    if (data.error) {
      status.className = 'text-[11px] text-red-500 mt-2';
      status.textContent = `❌ ${data.error}`;
    } else {
      status.className = 'text-[11px] text-emerald-600 mt-2 font-semibold';
      status.textContent = '✓ Uygulandı';
      document.getElementById(`aifix-prompt-${modelId}`).value = '';
    }
  } catch (e) {
    if (status) { status.className = 'text-[11px] text-red-500 mt-2'; status.textContent = `❌ ${e.message}`; }
  } finally {
    if (btn) btn.disabled = false;
    if (icon)  icon.textContent  = '✦';
    if (label) label.textContent = 'AI ile Uygula';
  }
}

// ── Name / ID Edit Panel (inline in model cards) ──────────────────

const _KNOWN_SUBCATS = [
  'desk','sofa','armchair','office_chair','dining_chair','bar_stool','bench','pouf',
  'coffee_table','dining_table','side_table','console_table','nightstand',
  'bookshelf','wardrobe','tv_stand','dresser',
  'double_bed','single_bed','queen_bed','king_bed',
  'floor_lamp','table_lamp','chandelier','rug','plant','mirror','artwork','refrigerator',
];
const _KNOWN_ROOMS = [
  ['office','Ofis'], ['home_office','Ev Ofisi'], ['study','Çalışma'],
  ['living_room','Salon'], ['bedroom','Yatak Odası'],
  ['dining_room','Yemek Odası'], ['kitchen','Mutfak'], ['bathroom','Banyo'],
];

function _editPanelHTML(m) {
  const curRooms = Array.isArray(m.room_types) ? m.room_types : [];
  const roomChecks = _KNOWN_ROOMS.map(([val, label]) => `
    <label class="flex items-center gap-1 cursor-pointer select-none">
      <input type="checkbox" class="ep-room-${m.id}" value="${val}" ${curRooms.includes(val) ? 'checked' : ''} />
      <span>${label}</span>
    </label>`).join('');

  return `<div class="mx-3 mb-3 bg-violet-50 border border-violet-200 rounded-xl p-3 text-xs" id="edit-panel-${m.id}">
    <p class="font-semibold text-violet-700 mb-2">✏ Model Düzenle</p>

    <div class="space-y-2 mb-3">
      <div>
        <label class="block text-gray-500 mb-0.5">Görünen İsim</label>
        <input id="ep-name-${m.id}" type="text" value="${m.name.replace(/"/g, '&quot;')}"
          class="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 bg-white" />
      </div>
      <div>
        <label class="block text-gray-500 mb-0.5">
          ID <span class="text-gray-400 font-normal">(küçük harf, alt çizgi)</span>
        </label>
        <input id="ep-id-${m.id}" type="text" value="${m.id}"
          oninput="this.value=this.value.toLowerCase().replace(/[^a-z0-9_]/g,'_')"
          class="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-violet-400 bg-white" />
        <p class="text-[10px] text-amber-600 mt-0.5">⚠ ID değişirse thumbnail dosyası otomatik yeniden adlandırılır.</p>
      </div>
    </div>

    <div class="flex items-center gap-2 mb-3">
      <button onclick="saveModelRename('${m.id}')"
        class="flex-1 bg-violet-600 hover:bg-violet-700 text-white py-1.5 rounded-lg text-xs font-semibold transition-colors">
        💾 İsim/ID Kaydet
      </button>
      <span id="ep-status-${m.id}" class="text-[11px] text-gray-400 flex-1 text-right"></span>
    </div>

    <!-- ── Kategori & Oda Tipleri (eksik sorununu çözer) ──────────── -->
    <div class="border-t border-violet-200 pt-2.5 space-y-2">
      <p class="font-semibold text-emerald-700">🏷 Kategori & Oda Tipleri</p>
      <div>
        <label class="block text-gray-500 mb-0.5">Kategori (subcategory)</label>
        <input id="ep-sub-${m.id}" type="text" value="${(m.subcategory||'').replace(/"/g,'&quot;')}"
          list="ep-sub-list" placeholder="örn: desk"
          class="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-emerald-400 bg-white" />
      </div>
      <div>
        <label class="block text-gray-500 mb-1">
          Hangi odalarda kullanılsın?
          <span class="text-gray-400 font-normal">(hiçbiri seçili değilse → her odada serbest)</span>
        </label>
        <div class="grid grid-cols-3 gap-x-2 gap-y-1 text-gray-700">
          ${roomChecks}
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button onclick="saveModelMetadata('${m.id}')"
          class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white py-1.5 rounded-lg text-xs font-semibold transition-colors">
          💾 Kategori/Oda Kaydet
        </button>
        <button onclick="toggleEditPanel('${m.id}')"
          class="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:bg-gray-100 transition-colors">
          Kapat
        </button>
        <span id="ep-meta-status-${m.id}" class="text-[11px] text-gray-400 flex-1 text-right"></span>
      </div>
    </div>

    <datalist id="ep-sub-list">
      ${_KNOWN_SUBCATS.map(s => `<option value="${s}">`).join('')}
    </datalist>
  </div>`;
}

async function saveModelMetadata(id) {
  const sub = document.getElementById(`ep-sub-${id}`)?.value.trim() || '';
  const rooms = Array.from(document.querySelectorAll(`.ep-room-${id}:checked`)).map(c => c.value);
  const statusEl = document.getElementById(`ep-meta-status-${id}`);

  if (statusEl) { statusEl.className = 'text-[11px] text-gray-400 flex-1 text-right'; statusEl.textContent = 'Kaydediliyor...'; }

  try {
    const r = await fetch(`${API_BASE}/catalog/asset/${encodeURIComponent(id)}/metadata`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subcategory: sub, room_types: rooms }),
    });
    const d = await r.json();

    if (d.ok) {
      // Yerel listeyi güncelle
      const m = _allModels.find(x => x.id === id);
      if (m) { m.subcategory = d.subcategory; m.room_types = d.room_types; }
      if (statusEl) {
        statusEl.className = 'text-[11px] text-green-600 font-semibold flex-1 text-right';
        const roomTxt = d.room_types.length ? d.room_types.join(', ') : 'her oda';
        statusEl.textContent = `✓ ${d.subcategory || '—'} · ${roomTxt}`;
      }
    } else {
      if (statusEl) { statusEl.className = 'text-[11px] text-red-500 flex-1 text-right'; statusEl.textContent = d.error || 'Hata'; }
    }
  } catch (e) {
    if (statusEl) { statusEl.className = 'text-[11px] text-red-500 flex-1 text-right'; statusEl.textContent = 'Hata: ' + e.message; }
  }
}

function toggleEditPanel(id) {
  if (_rotPanelId   === id) _rotPanelId   = null;
  if (_aiFixPanelId === id) _aiFixPanelId = null;
  _editPanelId = (_editPanelId === id) ? null : id;
  renderModelsGrid();
}

async function saveModelRename(oldId) {
  const newName = document.getElementById(`ep-name-${oldId}`)?.value.trim();
  const newId   = document.getElementById(`ep-id-${oldId}`)?.value.trim();
  const statusEl = document.getElementById(`ep-status-${oldId}`);

  if (!newName && !newId) {
    if (statusEl) statusEl.textContent = 'En az biri gerekli.';
    return;
  }
  if (newId && !/^[a-z0-9_]+$/.test(newId)) {
    if (statusEl) { statusEl.className = 'text-[11px] text-red-500 flex-1 text-right'; statusEl.textContent = 'Geçersiz ID formatı'; }
    return;
  }

  if (statusEl) { statusEl.className = 'text-[11px] text-gray-400 flex-1 text-right'; statusEl.textContent = 'Kaydediliyor...'; }

  try {
    const r = await fetch(`${API_BASE}/catalog/asset/${encodeURIComponent(oldId)}/rename`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_name: newName, new_id: newId }),
    });
    const d = await r.json();

    if (d.ok) {
      const idChanged = d.id_changed;
      const msg = idChanged
        ? `✓ ID: ${d.old_id} → ${d.new_id}`
        : `✓ İsim güncellendi`;
      if (statusEl) {
        statusEl.className = 'text-[11px] text-green-600 font-semibold flex-1 text-right';
        statusEl.textContent = msg;
      }
      // Update local list
      const m = _allModels.find(x => x.id === oldId);
      if (m) {
        if (newName) m.name = d.new_name;
        if (idChanged) m.id = d.new_id;
      }
      // Close panel after user has time to read the message (1.5s)
      setTimeout(() => {
        _editPanelId = null;
        renderModelsGrid();
      }, 1500);
    } else {
      if (statusEl) {
        statusEl.className = 'text-[11px] text-red-500 font-semibold flex-1 text-right';
        statusEl.textContent = `❌ ${d.error || 'Hata'}`;
      }
    }
  } catch (e) {
    if (statusEl) { statusEl.className = 'text-[11px] text-red-500 flex-1 text-right'; statusEl.textContent = e.message; }
  }
}

// ── Rotation Correction Panel (inline in model cards) ──────────────

function _rotPanelHTML(id) {
  return `<div class="mx-3 mb-3 bg-orange-50 border border-orange-200 rounded-xl p-3 text-xs" id="rot-panel-${id}">
    <p class="font-semibold text-orange-700 mb-2">↻ Eksen / Rotasyon Düzelt</p>
    <p class="text-orange-600 mb-2 text-[11px]">Model yan/ters geliyorsa aşağıdan düzelt, sonra kaydet:</p>

    <!-- Presets -->
    <div class="grid grid-cols-2 gap-1 mb-2">
      <button onclick="applyModelRotPreset('${id}',90,0,0)"
        class="py-1 px-1.5 rounded border border-orange-200 hover:bg-orange-100 bg-white text-orange-700 text-[11px] transition-colors">
        X+90° — sırt üstü yatıyor
      </button>
      <button onclick="applyModelRotPreset('${id}',-90,0,0)"
        class="py-1 px-1.5 rounded border border-orange-200 hover:bg-orange-100 bg-white text-orange-700 text-[11px] transition-colors">
        X−90° — yüz üstü yatıyor
      </button>
      <button onclick="applyModelRotPreset('${id}',0,90,0)"
        class="py-1 px-1.5 rounded border border-orange-200 hover:bg-orange-100 bg-white text-orange-700 text-[11px] transition-colors">
        Y+90° — sağa yatıyor
      </button>
      <button onclick="applyModelRotPreset('${id}',0,-90,0)"
        class="py-1 px-1.5 rounded border border-orange-200 hover:bg-orange-100 bg-white text-orange-700 text-[11px] transition-colors">
        Y−90° — sola yatıyor
      </button>
      <button onclick="applyModelRotPreset('${id}',0,0,0)"
        class="col-span-2 py-1 px-1.5 rounded border border-gray-200 hover:bg-gray-50 bg-white text-gray-600 text-[11px] transition-colors">
        ✓ Sıfırla — zaten dik duruyor
      </button>
    </div>

    <!-- Manual inputs -->
    <div class="grid grid-cols-3 gap-1 mb-2">
      <div><label class="text-gray-500 block mb-0.5">RX°</label>
        <input id="rp-rx-${id}" type="number" value="0" step="90"
          class="w-full border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-orange-400" /></div>
      <div><label class="text-gray-500 block mb-0.5">RY°</label>
        <input id="rp-ry-${id}" type="number" value="0" step="90"
          class="w-full border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-orange-400" /></div>
      <div><label class="text-gray-500 block mb-0.5">RZ extra°</label>
        <input id="rp-rz-${id}" type="number" value="0" step="90"
          class="w-full border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-orange-400" /></div>
    </div>

    <div class="flex items-center gap-2">
      <button onclick="saveModelRotCorrection('${id}')"
        class="flex-1 bg-orange-600 hover:bg-orange-700 text-white py-1.5 rounded-lg text-xs font-semibold transition-colors">
        💾 Kaydet
      </button>
      <span id="rp-status-${id}" class="text-[11px] text-gray-500 flex-1"></span>
    </div>
  </div>`;
}

function toggleRotPanel(id) {
  if (_editPanelId  === id) _editPanelId  = null;
  if (_aiFixPanelId === id) _aiFixPanelId = null;
  _rotPanelId = (_rotPanelId === id) ? null : id;
  renderModelsGrid();
}

function applyModelRotPreset(id, rx, ry, rz) {
  const rxEl = document.getElementById(`rp-rx-${id}`);
  const ryEl = document.getElementById(`rp-ry-${id}`);
  const rzEl = document.getElementById(`rp-rz-${id}`);
  if (rxEl) rxEl.value = rx;
  if (ryEl) ryEl.value = ry;
  if (rzEl) rzEl.value = rz;
}

async function saveModelRotCorrection(id) {
  const rx = parseFloat(document.getElementById(`rp-rx-${id}`)?.value || 0);
  const ry = parseFloat(document.getElementById(`rp-ry-${id}`)?.value || 0);
  const rz = parseFloat(document.getElementById(`rp-rz-${id}`)?.value || 0);
  const statusEl = document.getElementById(`rp-status-${id}`);

  if (statusEl) statusEl.textContent = 'Kaydediliyor...';

  try {
    const r = await fetch(`${API_BASE}/catalog/asset/${encodeURIComponent(id)}/rotation-correction`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rx, ry, rz }),
    });
    const d = await r.json();
    if (d.ok) {
      if (statusEl) { statusEl.className = 'text-[11px] text-green-600 font-semibold flex-1'; statusEl.textContent = `✓ [${rx},${ry},${rz}]° kaydedildi`; }
    } else {
      if (statusEl) { statusEl.className = 'text-[11px] text-red-500 flex-1'; statusEl.textContent = d.error || 'Hata'; }
    }
  } catch (e) {
    if (statusEl) { statusEl.className = 'text-[11px] text-red-500 flex-1'; statusEl.textContent = e.message; }
  }
}

async function deleteCatalogEntry(id) {
  const m = _allModels.find(x => x.id === id);
  const label = m ? `"${m.name}" (${id})` : `"${id}"`;
  if (!confirm(`${label} katalogdan kaldırılsın mı?\n\nNot: Fiziksel dosya silinmez, sadece katalog kaydı kaldırılır.`)) return;
  try {
    const r = await fetch(`${API_BASE}/catalog/asset/${encodeURIComponent(id)}`, { method: 'DELETE' });
    const d = await r.json();
    if (d.ok) {
      _allModels = _allModels.filter(x => x.id !== id);
      renderModelsGrid();
    } else {
      alert(`❌ ${d.error || 'Silme hatası'}`);
    }
  } catch (e) {
    alert(`❌ ${e.message}`);
  }
}

function insertModelsToPrompt() {
  const items = Object.values(_modelSelections);
  if (!items.length) return;

  // 1) Prompt'a detaylı JSON bloğu ekle
  //    Hem coach'un okuyabileceği zengin bağlam, hem de post-processor'ın
  //    parse ettiği "şu modelleri kullan: id1, id2" satırı korunur.
  const idList = items.flatMap(x =>
    Array.from({ length: x.qty || 1 }, () => x.id)
  ).join(', ');

  const jsonItems = items.map(x => {
    const full = _allModels.find(m => m.id === x.id) || {};
    // _allModels'de style string, dims string, room_types array olarak tutuluyor
    const entry = {
      id:          x.id,
      name:        x.name || x.id,
      subcategory: x.subcategory || full.subcategory || '',
      ...(full.dims                       && { dimensions: full.dims }),
      ...(full.style                      && { style: full.style }),
      ...(full.room_types?.length         && { room_types: full.room_types.join(', ') }),
      ...(x.qty > 1                       && { qty: x.qty }),
    };
    return entry;
  });

  const jsonBlock = JSON.stringify(jsonItems, null, 2);
  const insertion = `şu modelleri kullan: ${idList}\nModel detayları:\n${jsonBlock}`;

  const promptEl = document.getElementById('prompt-input');
  const cur = promptEl.value.trim();
  promptEl.value = cur ? `${cur}\n\n${insertion}` : insertion;

  // 2) Doğrudan yapboza spec olarak ekle — coach yorumlamasın, isimler korunsun
  if (!lastCoachResult) {
    lastCoachResult = { room: { width: 5, depth: 4, height: 2.7, type: '', style: '' }, specs: [], house: null };
  }
  // Placement pool: yeni eklenen itemlar sırayla farklı konumlara gider
  // böylece hepsi "center"a yığılıp birbirini bloklamaz.
  const _PLACEMENT_POOL = [
    'center', 'east_wall', 'west_wall', 'north_wall', 'south_wall',
    'corner_ne', 'corner_nw', 'corner_se', 'corner_sw',
  ];
  const _WALL_SUBCATS = new Set([
    'wardrobe','bookshelf','tv_stand','dresser','console_table',
    'kitchen_counter','bathtub','toilet','floor_lamp','plant',
    'artwork','mirror','chandelier','refrigerator','bench','bar_stool',
  ]);
  let _placementIdx = 0;

  items.forEach(x => {
    for (let q = 0; q < (x.qty || 1); q++) {
      const slotName = x.qty > 1 ? `${x.id}_${q + 1}` : x.id;
      const exists = lastCoachResult.specs.find(s => s.asset_id === x.id && s.slot === slotName);
      if (!exists) {
        // Duvar tipi subcat → duvar placement'ından başla, aksi → pool'dan al
        const placement = _WALL_SUBCATS.has(x.subcategory)
          ? _PLACEMENT_POOL[1 + (_placementIdx % 4)]   // east/west/north/south rotasyonu
          : _PLACEMENT_POOL[_placementIdx % _PLACEMENT_POOL.length];
        _placementIdx++;
        lastCoachResult.specs.push({
          slot:                slotName,
          asset_id:            x.id,
          subcategory:         x.subcategory || '',
          placement,
          allow_room_mismatch: true,
          _manual:             true,   // coach update'ten korur
        });
      }
    }
  });

  document.getElementById('plan-canvas-wrap')?.classList.remove('hidden');
  fetchAndRenderPlanPreview().catch(() => {});

  switchTab('tasarim');
  promptEl.focus();
  promptEl.setSelectionRange(promptEl.value.length, promptEl.value.length);
  lastCoachResult = lastCoachResult;  // keep specs, don't reset
}
