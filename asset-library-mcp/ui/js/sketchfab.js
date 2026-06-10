// ── sketchfab.js ──────────────────────────────────────────────────

let _sfModelCache = {};

async function searchSketchfab() {
  const input = document.getElementById('sf-search-input');
  const q = input.value.trim();
  const grid = document.getElementById('sf-results-grid');
  const btn = document.getElementById('btn-sf-search');
  const icon = document.getElementById('sf-search-icon');

  if (!q) return;

  btn.disabled = true;
  icon.textContent = '⏳';
  grid.innerHTML = `<div class="col-span-full flex flex-col items-center justify-center py-20 text-gray-400">
    <div class="spinner mb-4 mx-auto"></div>
    <p class="text-lg font-medium">Sketchfab aranıyor...</p>
  </div>`;

  try {
    const url = `${API_BASE}/sketchfab/search?q=${encodeURIComponent(q)}&category=${_sfCategory}`;
    const res = await fetch(url);
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    _sfResults = data.results || [];
    _sfResults.forEach(m => _sfModelCache[m.uid] = m); // Cache them
    renderSketchfabGrid();
  } catch (e) {
    grid.innerHTML = `<div class="col-span-full flex flex-col items-center justify-center py-20 text-red-500">
      <div class="text-5xl mb-4">⚠️</div>
      <p class="font-bold text-lg">Sketchfab Hatası</p>
      <p class="text-sm opacity-80 mt-1 max-w-md text-center">${e.message}</p>
      <button onclick="searchSketchfab()" class="mt-4 px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg text-xs font-bold transition-all">Tekrar Dene</button>
    </div>`;
  } finally {
    btn.disabled = false;
    icon.textContent = '🔍';
  }
}

function setSfCategory(cat, el) {
  _sfCategory = cat;
  document.querySelectorAll('.sf-cat-btn-chip').forEach(btn => {
    btn.className = 'sf-cat-btn-chip px-3 py-1 rounded-full text-[11px] font-semibold bg-gray-50 text-gray-500 border border-gray-200 hover:bg-gray-100 transition-all';
  });
  el.className = 'sf-cat-btn-chip px-3 py-1 rounded-full text-[11px] font-semibold bg-indigo-100 text-indigo-700 border border-indigo-200 transition-all';
  if (document.getElementById('sf-search-input').value.trim()) {
    searchSketchfab();
  }
}

function renderSketchfabGrid() {
  const grid = document.getElementById('sf-results-grid');
  if (!_sfResults.length) {
    grid.innerHTML = `<div class="col-span-full flex flex-col items-center justify-center py-20 text-gray-400">
      <div class="text-6xl mb-4">🔍</div>
      <p class="text-lg font-medium">Sonuç bulunamadı</p>
    </div>`;
    return;
  }

  grid.innerHTML = _sfResults.map(m => {
    const isDownloading = _sfDownloading[m.uid];
    const poly = m.polyCount ? (m.polyCount > 1000 ? Math.round(m.polyCount/1000) + 'k' : m.polyCount) : '?';
    const isLocal = m.is_local;
    const inYapboz = typeof lastCoachResult !== 'undefined' && lastCoachResult?.specs?.some(s => s.sf_uid === m.uid);

    return `<div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col transition-all hover:shadow-md">
      <!-- Resim + üstünde Yapboza Ekle butonu -->
      <div class="relative h-40 overflow-hidden bg-gray-100">
        <img src="${m.thumbnailUrl}" class="w-full h-full object-cover" />
        <!-- Yapboza Ekle — resmin üstünde, her zaman görünür -->
        <button onclick="addSfToYapboz('${m.uid}')"
          class="absolute inset-x-0 bottom-0 py-2 text-xs font-black flex items-center justify-center gap-1.5 transition-all
            ${inYapboz
              ? 'bg-emerald-500/90 text-white'
              : 'bg-emerald-600/90 hover:bg-emerald-600 text-white'}">
          ${inYapboz ? '✓ Yapbozda' : '📐 Yapboza Ekle'}
        </button>
        <div class="absolute top-2 right-2 bg-white/90 text-gray-600 text-[10px] px-2 py-0.5 rounded-full shadow-sm font-bold">
          ${poly} polys
        </div>
      </div>

      <div class="p-3 flex-1 flex flex-col">
        <h3 class="font-bold text-sm text-gray-800 line-clamp-2 leading-tight mb-1" title="${m.name}">${m.name}</h3>
        <p class="text-[10px] text-gray-400 mt-auto">${m.author}</p>
      </div>

      <div class="px-3 pb-3 flex gap-1.5">
        ${isLocal
          ? `<div class="flex-1 bg-emerald-50 text-emerald-600 py-1.5 rounded-xl text-xs font-bold flex items-center justify-center border border-emerald-200">✅ İndirildi</div>`
          : `<button onclick="downloadSketchfab('${m.uid}')" id="sf-dl-btn-${m.uid}"
               class="flex-1 bg-indigo-50 hover:bg-indigo-600 text-indigo-600 hover:text-white py-1.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1"
               ${isDownloading ? 'disabled' : ''}>
               ${isDownloading ? '⏳ İndiriliyor' : '📥 İndir'}
             </button>`
        }
        <a href="${m.viewUrl}" target="_blank"
          class="w-8 h-8 flex items-center justify-center rounded-xl bg-gray-50 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all">👁</a>
      </div>
    </div>`;
  }).join('');
}

function addSfToYapboz(uid) {
  const model = _sfModelCache[uid] || _sfResults.find(m => m.uid === uid);
  if (!model) return;

  // Ensure lastCoachResult exists with a default room
  if (!lastCoachResult) {
    lastCoachResult = {
      room: { width: 5, depth: 4, height: 2.7, type: '', style: '' },
      specs: [],
      house: null,
    };
    document.getElementById('plan-canvas-wrap')?.classList.remove('hidden');
  }

  // Don't add duplicates
  if (lastCoachResult.specs.some(s => s.sf_uid === uid)) {
    if (typeof switchTab === 'function') switchTab('tasarim');
    return;
  }

  // Add as a spec with sf_uid marker (not yet in local catalog)
  lastCoachResult.specs.push({
    slot:     `sf_${uid.slice(0, 8)}`,
    sf_uid:   uid,
    sf_name:  model.name,
    sf_thumb: model.thumbnailUrl,
    asset_id: null,
    placement: 'center',
    rot_z:    0,
    _manual:  true,
  });

  // Re-render yapboz showing SF placeholder
  if (typeof fetchAndRenderPlanPreview === 'function') fetchAndRenderPlanPreview();
  // Update this button in grid
  renderSketchfabGrid();
  // Switch to tasarım tab
  if (typeof switchTab === 'function') switchTab('tasarim');
}

async function downloadSketchfab(uid) {
  const model = _sfModelCache[uid] || _sfResults.find(m => m.uid === uid);
  if (!model) return;

  const overlay = document.getElementById('sf-status-overlay');
  const log = document.getElementById('sf-dl-log');
  const nameEl = document.getElementById('sf-dl-name');
  const progress = document.getElementById('sf-dl-progress');
  const title = document.getElementById('sf-dl-title');
  const icon = document.getElementById('sf-dl-icon');

  overlay.classList.remove('hidden');
  log.innerHTML = 'İstek gönderiliyor...';
  nameEl.textContent = model.name;
  progress.style.width = '5%';
  title.textContent = 'İndiriliyor...';
  icon.className = 'animate-spin';

  _sfDownloading[uid] = { status: 'running' };
  
  // Refresh UI parts that might show this model
  renderSketchfabGrid();
  if (typeof _renderSfRecommendations === 'function') {
    // If coach is active, we might need a refresh logic there too
  }

  try {
    const res = await fetch(`${API_BASE}/sketchfab/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        uid: model.uid,
        name: model.name,
        thumbnailUrl: model.thumbnailUrl
      })
    });
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    const jobId = data.job_id;
    _sfDownloading[uid].job_id = jobId;
    pollSketchfabJob(jobId, uid);
    return jobId;
  } catch (e) {
    log.innerHTML += `<div class="text-red-500 mt-1">❌ HATA: ${e.message}</div>`;
    title.textContent = 'Hata!';
    icon.className = '';
    icon.textContent = '❌';
    _sfDownloading[uid].status = 'error';
    renderSketchfabGrid();
  }
}

async function pollSketchfabJob(jobId, uid) {
  const log = document.getElementById('sf-dl-log');
  const progress = document.getElementById('sf-dl-progress');
  const title = document.getElementById('sf-dl-title');
  const icon = document.getElementById('sf-dl-icon');

  const interval = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/sketchfab/job/${jobId}`);
      const data = await res.json();

      if (data.output) {
        const lines = data.output.split('\n');
        log.innerHTML = lines.map(l => `<div>${l}</div>`).join('');
        log.scrollTop = log.scrollHeight;
        const step = Math.min(95, 5 + (lines.length * 5));
        progress.style.width = `${step}%`;
      }

      if (data.status === 'done') {
        clearInterval(interval);
        progress.style.width = '100%';
        title.textContent = 'Tamamlandı!';
        icon.className = '';
        icon.textContent = '✅';
        log.innerHTML += `<div class="text-emerald-500 font-bold mt-1">✓ Başarıyla kataloğa eklendi.</div>`;
        
        // Mark as local in cache
        if (_sfModelCache[uid]) _sfModelCache[uid].is_local = true;
        delete _sfDownloading[uid];
        
        renderSketchfabGrid();
        loadModelsTab(true); 
      } else if (data.status === 'error') {
        clearInterval(interval);
        title.textContent = 'Başarısız!';
        icon.className = '';
        icon.textContent = '❌';
        log.innerHTML += `<div class="text-red-500 font-bold mt-1">❌ Hata: ${data.error || 'Bilinmeyen hata'}</div>`;
        _sfDownloading[uid].status = 'error';
        renderSketchfabGrid();
      }
    } catch (e) {
      clearInterval(interval);
      log.innerHTML += `<div class="text-red-500 mt-1">❌ Polling hatası: ${e.message}</div>`;
    }
  }, 2000);
}
