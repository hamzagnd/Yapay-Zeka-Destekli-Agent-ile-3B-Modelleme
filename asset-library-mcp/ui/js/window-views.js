// ── window-views.js ───────────────────────────────────────────────
// Window views: refreshWindowWalls, _renderWallChips, toggleWallChip,
// generateWindowViews, loadWindowViewsCatalog, applyCatalogEntry.

async function loadWindowViewsCatalog() {
  const el = document.getElementById('window-views-catalog');
  if (!el) return;
  try {
    const res     = await fetch(`${API_BASE}/blender/window-views/catalog`);
    const data    = await res.json();
    const entries = data.entries || [];
    if (!entries.length) {
      el.innerHTML = '<span class="text-slate-500">Henüz üretilmiş görsel yok.</span>';
      return;
    }
    el.innerHTML =
      `<div class="flex flex-wrap gap-2 mt-1">` +
      entries.map((e, idx) => {
        const shortWall = (e.wall_name || '').replace(/^Room_/, '');
        const safeEntry = JSON.stringify(e).replace(/"/g, '&quot;');
        return `
        <div class="relative group cursor-pointer" title="${e.atmosphere}\n${e.compass} · ${e.created_at}">
          <img src="${e.url}" onclick="applyCatalogEntry(${safeEntry})"
            class="h-16 w-24 object-cover rounded border border-slate-600 group-hover:border-violet-400 transition-colors block" />
          <span class="absolute top-1 left-1 bg-black/60 text-white text-[9px] px-1 rounded backdrop-blur-sm pointer-events-none">${e.compass}</span>
          <span class="absolute bottom-0 left-0 right-0 text-center text-white text-[10px] bg-black/60 rounded-b truncate px-1 pointer-events-none">${shortWall}</span>
          <div class="absolute inset-0 bg-violet-900/70 opacity-0 group-hover:opacity-100 transition-opacity rounded flex items-center justify-center pointer-events-none">
            <span class="text-white text-xs font-semibold">Uygula</span>
          </div>
        </div>`;
      }).join('') +
      `</div>
       <p class="text-[10px] text-slate-600 mt-2">Görsele tıkla → yukarıdaki "Hangi duvara" seçicindeki duvara uygulanır.</p>`;
  } catch (e) {
    el.innerHTML = `<span class="text-red-400">Hata: ${e.message}</span>`;
  }
}

async function applyCatalogEntry(entry) {
  const status = document.getElementById('window-views-status');

  let wallName = (document.getElementById('window-apply-target')?.value || '').trim();

  if (!wallName) {
    if (Object.keys(_windowWallsData).length) {
      wallName = Object.keys(_windowWallsData)[0];
    } else {
      status.className = 'text-xs text-slate-400';
      status.textContent = 'Pencereler alınıyor...';
      try {
        const r = await fetch(`${API_BASE}/blender/windows`, { signal: AbortSignal.timeout(8000) });
        const d = await r.json();
        _windowWallsData = {};
        for (const w of (d.walls || [])) {
          _windowWallsData[w.wall_name] = { pane_count: w.pane_count, glass_names: w.glass_names };
        }
        _renderWallChips();
        wallName = Object.keys(_windowWallsData)[0] || '';
      } catch (e) {
        status.className = 'text-xs text-red-400';
        status.textContent = 'Blender bağlantı hatası: ' + e.message;
        return;
      }
    }
  }

  if (!wallName) {
    status.className = 'text-xs text-red-400';
    status.textContent = 'Sahnede pencere yok veya duvar seçilmedi.';
    return;
  }

  status.className = 'text-xs text-slate-400';
  status.textContent = `Uygulanıyor → ${wallName.replace(/^Room_/, '')}...`;
  try {
    const res  = await fetch(`${API_BASE}/blender/apply-window-view`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wall_name: wallName, filename: entry.filename }),
    });
    const data = await res.json();
    if (data.error) {
      status.className = 'text-xs text-red-400';
      status.textContent = '❌ ' + data.error;
    } else {
      status.className = 'text-xs text-green-400';
      status.textContent = `✓ ${wallName.replace(/^Room_/, '')} güncellendi`;
    }
  } catch (e) {
    status.className = 'text-xs text-red-400';
    status.textContent = '❌ ' + e.message;
  }
}

function _renderWallChips() {
  const chips = document.getElementById('window-walls-chips');
  const applyTarget = document.getElementById('window-apply-target');
  const walls = Object.entries(_windowWallsData);

  if (!chips) return;
  if (!walls.length) {
    chips.innerHTML = '<span class="text-xs text-slate-500">Sahnede pencere camı yok — önce pencere ekle.</span>';
    if (applyTarget) applyTarget.innerHTML = '<option value="">— duvar yok —</option>';
    return;
  }

  chips.innerHTML = walls.map(([name, data]) => {
    const sel = _selectedWallChips.has(name);
    const cls = sel
      ? 'bg-violet-600 text-white border-violet-500'
      : 'bg-slate-700 text-slate-300 border-slate-600 hover:border-violet-500 hover:text-slate-100';
    const short = name.replace(/^Room_/, '');
    return `<button onclick="toggleWallChip('${name}')"
      class="wall-chip px-3 py-1 rounded-full text-xs font-medium border transition-all ${cls}">
      🪟 ${short} · ${data.pane_count} cam
    </button>`;
  }).join('');

  if (applyTarget) {
    applyTarget.innerHTML = '<option value="">— duvar seçin —</option>' +
      walls.map(([name]) =>
        `<option value="${name}">${name.replace(/^Room_/, '')}</option>`
      ).join('');
  }
}

function toggleWallChip(wallName) {
  if (_selectedWallChips.has(wallName)) {
    _selectedWallChips.delete(wallName);
  } else {
    _selectedWallChips.add(wallName);
  }
  _renderWallChips();
}

function refreshWindowWalls() {
  if (_sceneData && _sceneData.objects) {
    const GLASS_RE = /^Win_(.+?)_Glass\d*$/i;
    const groups   = {};
    for (const obj of _sceneData.objects) {
      const m = obj.name.match(GLASS_RE);
      if (!m) continue;
      const key = m[1];
      if (!groups[key]) groups[key] = { pane_count: 0, glass_names: [], wall_obj: null };
      groups[key].glass_names.push(obj.name);
      groups[key].pane_count++;
    }
    _windowWallsData = groups;
    _renderWallChips();
  } else {
    const chips = document.getElementById('window-walls-chips');
    if (chips) chips.innerHTML = '<span class="text-xs text-slate-400">⏳ Yükleniyor...</span>';
    fetch(`${API_BASE}/blender/windows`, { signal: AbortSignal.timeout(8000) })
      .then(r => r.json())
      .then(d => {
        _windowWallsData = {};
        for (const w of (d.walls || [])) {
          _windowWallsData[w.wall_name] = { pane_count: w.pane_count, glass_names: w.glass_names };
        }
        _renderWallChips();
      })
      .catch(e => {
        if (chips) chips.innerHTML = `<span class="text-xs text-red-400">❌ ${e.message}</span>`;
      });
  }
}

async function generateWindowViews() {
  const atmosphere = (document.getElementById('window-atmosphere')?.value || '').trim();
  const status     = document.getElementById('window-views-status');
  const progress   = document.getElementById('window-views-progress');
  const genBtn     = document.getElementById('btn-gen-window-views');
  const genIcon    = document.getElementById('wv-gen-icon');
  const genLabel   = document.getElementById('wv-gen-label');

  if (!atmosphere) {
    status.className = 'text-xs text-red-400';
    status.textContent = 'Atmosfer yazın.';
    return;
  }

  let wallNames = [..._selectedWallChips];
  if (!wallNames.length) {
    if (Object.keys(_windowWallsData).length) {
      wallNames = Object.keys(_windowWallsData);
    } else {
      status.className = 'text-xs text-slate-400';
      status.textContent = 'Pencereler alınıyor...';
      try {
        const wr = await fetch(`${API_BASE}/blender/windows`, { signal: AbortSignal.timeout(10000) });
        const wd = await wr.json();
        _windowWallsData = {};
        for (const w of (wd.walls || [])) {
          _windowWallsData[w.wall_name] = { pane_count: w.pane_count, glass_names: w.glass_names };
        }
        wallNames = Object.keys(_windowWallsData);
        _renderWallChips();
      } catch (_) {}
    }
  }

  if (!wallNames.length) {
    status.className = 'text-xs text-red-400';
    status.textContent = 'Sahnede pencere yok — Win_*_Glass* nesnesi ekle.';
    return;
  }

  genBtn.disabled = true;
  genIcon.textContent = '⏳';
  genLabel.textContent = 'Üretiliyor...';
  progress.classList.remove('hidden');

  const rowId = w => `wv-row-${w.replace(/\W/g, '_')}`;
  progress.innerHTML = wallNames.map(w =>
    `<div id="${rowId(w)}" class="flex items-center gap-2 text-xs text-slate-400">
       <span class="wv-icon">⏳</span>
       <span class="flex-1">${w.replace(/^Room_/, '')} — bekliyor...</span>
     </div>`
  ).join('');

  let doneOk = 0;
  for (let i = 0; i < wallNames.length; i++) {
    const wName = wallNames[i];
    const row   = document.getElementById(rowId(wName));
    if (row) {
      row.querySelector('.wv-icon').textContent = '⏳';
      row.querySelector('span:last-child').textContent = `${wName.replace(/^Room_/, '')} — üretiliyor... (${i+1}/${wallNames.length})`;
    }
    status.className  = 'text-xs text-slate-400';
    status.textContent = `${i+1}/${wallNames.length} — ${wName.replace(/^Room_/, '')}...`;

    try {
      const res = await fetch(`${API_BASE}/blender/generate-window-views`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ atmosphere, wall_names: [wName] }),
        signal: AbortSignal.timeout(150000),
      });
      const data = await res.json();
      const w = (data.walls || [])[0] || { wall_name: wName, error: data.error || 'Bilinmeyen hata' };
      const ok = !w.error;
      if (ok) doneOk++;
      const preview = ok && w.image_url
        ? `<img src="${w.image_url}" class="h-8 rounded border border-slate-600 ml-1" />`
        : '';
      if (row) {
        row.className = `flex items-center gap-2 text-xs ${ok ? 'text-green-400' : 'text-red-400'}`;
        row.innerHTML = `<span>${ok ? '✓' : '✗'}</span>
          <span class="flex-1">${wName.replace(/^Room_/, '')} — ${w.error || w.pane_count + ' cama uygulandı'}</span>
          ${preview}`;
      }
    } catch (e) {
      const isTimeout = e.name === 'TimeoutError' || e.name === 'AbortError';
      if (row) {
        row.className = 'flex items-center gap-2 text-xs text-yellow-400';
        row.innerHTML = `<span>⚠</span><span class="flex-1">${wName.replace(/^Room_/, '')} — ${isTimeout ? 'Zaman aşımı (tekrar dene)' : e.message}</span>`;
      }
    }
  }

  genBtn.disabled = false;
  genIcon.textContent = '✦';
  genLabel.textContent = 'Üret ve Uygula';
  status.className  = doneOk ? 'text-xs text-green-400' : 'text-xs text-yellow-400';
  status.textContent = `✓ ${doneOk}/${wallNames.length} tamamlandı`;
  if (doneOk) loadWindowViewsCatalog();
}
