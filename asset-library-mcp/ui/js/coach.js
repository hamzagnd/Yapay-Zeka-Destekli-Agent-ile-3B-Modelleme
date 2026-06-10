// ── coach.js ─────────────────────────────────────────────────────
// Prompt coach, yapboz SVG canvas, submitDesign, clearResponse.

// ── Plan Canvas → Base64 PNG ────────────────────────────────────
function getPlanCanvasImage() {
  const svg = document.getElementById("plan-canvas");
  if (!svg) return "";
  const xml = new XMLSerializer().serializeToString(svg);
  const svg64 = btoa(unescape(encodeURIComponent(xml)));
  return `data:image/svg+xml;base64,${svg64}`;
}

async function runPromptCoach() {
  const input = document.getElementById("prompt-input");
  const prompt = input.value.trim();
  const btnCoach = document.getElementById("btn-coach");
  const coachIcon = document.getElementById("coach-icon");
  const coachLabel = document.getElementById("coach-label");
  const note = document.getElementById("coach-note");

  if (!prompt) return;

  if (btnCoach) btnCoach.disabled = true;
  if (coachIcon) coachIcon.textContent = "⏳";
  if (coachLabel) coachLabel.textContent = "Geliştiriliyor...";
  
  note.classList.remove("hidden");
  note.innerHTML = `<div class="flex items-center gap-2 text-indigo-400">
    <div class="spinner-xs"></div> ${_sfEnabled
      ? 'Akıllı asistan katalog + Sketchfab tarıyor...'
      : 'Akıllı asistan kataloğu tarıyor...'}
  </div>`;

  // Ensure Yapboz is visible during development
  document.getElementById("plan-canvas-wrap")?.classList.remove("hidden");

  // Reset SF area
  document.getElementById("sf-coach-recommendations").classList.add("hidden");

  // Yapboz kilitliyse tüm spec'ler _manual sayılır — coach hiçbirini değiştiremez
  if (_yapbozLocked && lastCoachResult?.specs) {
    lastCoachResult.specs.forEach(s => { s._manual = true; });
  }

  // Modeller tabından elle eklenen spec'leri koru — coach bunları silecek
  const _manualSpecsBefore = (lastCoachResult?.specs || []).filter(s => s._manual);

  try {
    const res = await fetch(`${API_BASE}/coach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, llm: currentLLM }),
    });
    const data = await res.json();

    if (data.error) {
      note.innerHTML = `<span class="text-red-700">❌ Coach hatası: ${data.error}</span>`;
      return;
    }

    if (data.refined_prompt) {
      input.value = data.refined_prompt;
    }

    if (data.specs && data.specs.length) {
      lastCoachResult = {
        room: data.room || {},
        specs: data.specs,
        house: data.house || null,
      };
      if (_drawnRoom) {
        lastCoachResult.room = { ...lastCoachResult.room,
          width: _drawnRoom.width, depth: _drawnRoom.depth, height: _drawnRoom.height };
      }
    } else {
      lastCoachResult = null;
    }

    // Coach bittikten sonra manuel spec'leri geri ekle.
    // Kural: _manual=true olan spec HER ZAMAN korunur.
    //   • Coach aynı asset_id'yi döndürdüyse → o spec'e _manual=true ekle
    //     (bir sonraki coach çalışmasında da korunsun)
    //   • Coach aynı asset_id'yi döndürmediyse → spec'i listeye ekle
    // Subcategory bazlı silme yapılmıyor — iki farklı asset coexist edebilir,
    // kullanıcı istemediğini yapbozdan sağ-tık ile silebilir.
    if (_manualSpecsBefore.length) {
      if (!lastCoachResult) {
        lastCoachResult = { room:{width:5,depth:4,height:2.7,type:'',style:''}, specs:[], house:null };
      }
      const existingIds = new Set(lastCoachResult.specs.map(s => s.asset_id).filter(Boolean));
      for (const ms of _manualSpecsBefore) {
        if (ms.asset_id && existingIds.has(ms.asset_id)) {
          // Coach bu asset'i zaten aldı — _manual flag'ini koru
          const hit = lastCoachResult.specs.find(s => s.asset_id === ms.asset_id);
          if (hit) hit._manual = true;
        } else if (ms.sf_uid && lastCoachResult.specs.some(s => s.sf_uid === ms.sf_uid)) {
          // SF spec zaten var — flag koru
          const hit = lastCoachResult.specs.find(s => s.sf_uid === ms.sf_uid);
          if (hit) hit._manual = true;
        } else {
          // Coach bu parçayı almadı — kullanıcının seçimini geri ekle
          lastCoachResult.specs.push(ms);
        }
      }
    }

    const parts = [];
    if (data.rationale) {
      const isError = data.rationale.startsWith("⚠");
      parts.push(isError
        ? `<div class="text-amber-700">${data.rationale}</div>`
        : `<div><span class="font-semibold">💡 Neden:</span> ${data.rationale}</div>`);
    }
    if (data.warnings && data.warnings.length) {
      const items = data.warnings.map(w => `<li>${w}</li>`).join("");
      parts.push(`<div class="mt-1"><span class="font-semibold">⚠ Uyarılar:</span><ul class="list-disc list-inside">${items}</ul></div>`);
    }
    if (lastCoachResult) {
      parts.push(`<div class="mt-2 text-emerald-700 text-[11px] font-semibold">🎯 Deterministik yol aktif — <b>Tasarla</b> Coach planını LLM zincirini atlayarak doğrudan uygulayacak.</div>`);
    } else {
      parts.push(`<div class="mt-2 text-indigo-600 text-[11px]">Prompt güncellendi — düzenleyip <b>Tasarla</b>'ya basabilirsiniz.</div>`);
    }
    note.innerHTML = parts.join("");

    _populateCoachMatDropdowns();
    document.getElementById('coach-mat-picker').classList.remove('hidden');
    document.getElementById('coach-mat-result').textContent = '';

    // Önce yapboz önizlemesini render et (hızlı), SONRA yavaş Sketchfab
    // aramalarını başlat — aksi halde SF fetch'leri tarayıcının bağlantı
    // havuzunu doldurup coach-preview'i bekletiyor (yapboz boş kalıyor).
    if (lastCoachResult) {
      await fetchAndRenderPlanPreview().catch(() => { /* silent */ });
    }
    if (_sfEnabled && data.warnings && data.warnings.length) {
      _triggerSfRecommendations(data.warnings);
    }
  } catch (e) {
    note.innerHTML = `<span class="text-red-700">❌ Bağlantı hatası: ${e.message}</span>`;
  } finally {
    if (btnCoach) btnCoach.disabled = false;
    if (coachIcon) coachIcon.textContent = "✨";
    if (coachLabel) coachLabel.textContent = "Prompt Geliştir";
  }
}

function refinePrompt() {
  runPromptCoach();
}

async function _pollSfJob(jobId, responseBox) {
  return new Promise((resolve, reject) => {
    const iv = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/sketchfab/job/${jobId}`);
        const d = await r.json();
        if (d.output && responseBox) responseBox.textContent = "⏳ İndiriliyor...\n" + d.output;
        if (d.status === 'done')  { clearInterval(iv); resolve(d.asset_id); }
        if (d.status === 'error') { clearInterval(iv); reject(new Error(d.error || 'İndirme hatası')); }
      } catch (e) { clearInterval(iv); reject(e); }
    }, 2000);
  });
}

async function submitDesign() {
  const btn   = document.querySelector('button[onclick="submitDesign()"]');
  const icon  = document.getElementById("btn-icon");
  const label = document.getElementById("btn-label");
  const prompt = document.getElementById("prompt-input")?.value.trim();

  if (!prompt && !_sfDesignModel) return;

  if (btn)   btn.disabled    = true;
  if (icon)  icon.textContent  = "⏳";
  if (label) label.textContent = "Tasarlanıyor...";

  const resultBox  = document.getElementById("response-section");
  const responseBox = document.getElementById("response-box");
  if (resultBox)  resultBox.classList.remove("hidden");
  if (responseBox) responseBox.textContent = "İşleniyor...";

  try {
    // ── Sketchfab hızlı import ───────────────────────────────────
    if (_sfDesignModel) {
      if (responseBox) responseBox.textContent = `⏳ "${_sfDesignModel.name}" indiriliyor...`;
      const dlRes = await fetch(`${API_BASE}/sketchfab/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid: _sfDesignModel.uid, name: _sfDesignModel.name, thumbnailUrl: _sfDesignModel.thumbnailUrl }),
      });
      const dlData = await dlRes.json();
      if (dlData.error) throw new Error(dlData.error);

      const assetId = await _pollSfJob(dlData.job_id, responseBox);
      if (!assetId) throw new Error('Asset ID alınamadı');

      if (responseBox) responseBox.textContent = `✓ İndirildi (${assetId})\n🔄 Blender'a aktarılıyor...`;
      const impRes = await fetch(`${API_BASE}/blender/import-model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_id: assetId, location: [0, 0, 0] }),
      });
      const impData = await impRes.json();
      if (responseBox) responseBox.textContent = impData.ok
        ? `✓ Blender'a eklendi → ${impData.obj_name || assetId}`
        : `⚠ Import: ${impData.error || 'bilinmeyen hata'}`;

      if (typeof clearSfDesignModel === 'function') clearSfDesignModel();
      if (typeof loadModelsTab === 'function') loadModelsTab(true);
      switchTab('sahne');
      return;
    }

    // ── Coach deterministik yol ──────────────────────────────────
    if (lastCoachResult) {
      // Pending Sketchfab specs'leri önce indir (sadece toggle açıksa)
      const sfPending = _sfEnabled
        ? lastCoachResult.specs.filter(s => s.sf_uid && !s.asset_id)
        : [];
      for (const s of sfPending) {
        if (responseBox) responseBox.textContent = `⏳ "${s.sf_name || s.sf_uid}" indiriliyor...`;
        try {
          const dlR = await fetch(`${API_BASE}/sketchfab/download`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ uid: s.sf_uid, name: s.sf_name, thumbnailUrl: s.sf_thumb }),
          });
          const dlD = await dlR.json();
          if (!dlD.error) {
            const aid = await _pollSfJob(dlD.job_id, responseBox);
            if (aid) s.asset_id = aid;
          }
        } catch { /* hata durumunda atla */ }
      }

      if (responseBox) responseBox.textContent = "İşleniyor...";
      const res = await fetch(`${API_BASE}/design-from-coach`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          room:       lastCoachResult.room,
          specs:      lastCoachResult.specs,
          house:      lastCoachResult.house,
          drawn_room: _drawnRoom
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      if (responseBox) responseBox.textContent = data.result || "İşlem tamamlandı.";
      switchTab('sahne');
      return;
    }

    // ── Direkt AI yol (/design) ──────────────────────────────────
    const res = await fetch(`${API_BASE}/design`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, llm: currentLLM }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (responseBox) responseBox.textContent = data.result || "İşlem tamamlandı.";

  } catch (e) {
    if (responseBox) responseBox.textContent = "Hata: " + e.message;
  } finally {
    if (btn)   btn.disabled    = false;
    if (icon)  icon.textContent  = "⚡";
    if (label) label.textContent = "Tasarla";
  }
}

function clearResponse() {
  const rs = document.getElementById("response-section");
  if (rs) rs.classList.add("hidden");
  const rb = document.getElementById("response-box");
  if (rb) rb.textContent = "";
  const pi = document.getElementById("prompt-input");
  if (pi) pi.value = "";
}

// ── Yapboz SVG canvas ──────────────────────────────────────────

// Global drag state — registered ONCE on window, avoids per-render accumulation
let _planDrag     = null;   // { p, g, idx, startX, startY, didMove }
let _planDragInfo = null;   // { scale, w2sx, w2sy } — updated each renderPlanPreview

window.addEventListener('mousemove', (e) => {
  if (!_planDrag || !_planDragInfo) return;
  const { scale, w2sx, w2sy } = _planDragInfo;
  const { p, g } = _planDrag;
  if (Math.abs(e.clientX - _planDrag.startX) > 3 ||
      Math.abs(e.clientY - _planDrag.startY) > 3) {
    _planDrag.didMove = true;
  }
  if (!_planDrag.didMove) return;
  p.location[0] += (e.clientX - _planDrag.startX) / scale;
  p.location[1] -= (e.clientY - _planDrag.startY) / scale;
  g.setAttribute("transform",
    `translate(${w2sx(p.location[0])},${w2sy(p.location[1])}) rotate(${-p.rotation_z})`);
  _planDrag.startX = e.clientX;
  _planDrag.startY = e.clientY;
});

window.addEventListener('mouseup', () => {
  if (!_planDrag) return;
  const { p, idx } = _planDrag;
  if (_planDrag.didMove) {
    const spec = lastCoachResult?.specs?.find(s => (s.slot || s.asset_id) === p.slot);
    if (spec) spec.location_override = [p.location[0], p.location[1], p.location[2]];
  } else {
    selectYapbozItem(idx);
  }
  _planDrag = null;
});

function planTransform(roomW, roomD) {
  const scale = Math.min(PLAN_SVG_W / (roomW||5), PLAN_SVG_H / (roomD||4)) * 0.9;
  const cx = PLAN_SVG_W / 2, cy = PLAN_SVG_H / 2;
  return {
    scale, cx, cy,
    w2sx: wx => cx + wx * scale,
    w2sy: wy => cy - wy * scale,
    s2wx: sx => (sx - cx) / scale,
    s2wy: sy => (cy - sy) / scale,
  };
}

async function fetchAndRenderPlanPreview() {
  if (!lastCoachResult) return;
  const wrap = document.getElementById("plan-canvas-wrap");
  const note = document.getElementById("plan-canvas-note");

  if (wrap) wrap.classList.remove("hidden");
  if (note) note.innerHTML = `<span class="animate-pulse text-indigo-400">Önizleme hesaplanıyor...</span>`;

  try {
    const res = await fetch(`${API_BASE}/coach-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room: lastCoachResult.room,
        specs: lastCoachResult.specs,
        house: lastCoachResult.house,
        drawn_room: _drawnRoom
      }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    renderPlanPreview(data);
    
    if (note) {
      const sfCount = (lastCoachResult?.specs || []).filter(s => s.sf_uid && !s.asset_id).length;
      let noteTxt = `<b>${data.room.width}×${data.room.depth}m</b>`;
      if (data.placed.length) noteTxt += ` · <b>${data.placed.length}</b> parça yerleşti`;
      if (sfCount) noteTxt += ` · <span class="text-blue-600"><b>${sfCount}</b> Sketchfab (indirilecek)</span>`;
      if (data.skipped && data.skipped.length) {
        const reasons = data.skipped.join('\n');
        noteTxt += ` · <span class="text-red-500 cursor-help underline decoration-dotted" title="${reasons.replace(/"/g, '&quot;')}"><b>${data.skipped.length}</b> eksik ⓘ</span>`;
      }
      noteTxt += ` · <span class="text-red-600">━ kırmızı kenar = ön yüz</span>`;
      note.innerHTML = noteTxt;
    }

  } catch (e) {
    if (note) note.innerHTML = `<span class="text-red-500">Önizleme hatası: ${e.message}</span>`;
  }
}

let _planPreviewData = null;  // last preview data — used by yapboz edit panel

function renderPlanPreview(data) {
  const canvas = document.getElementById("plan-canvas");
  if (!canvas) return;
  canvas.innerHTML = "";
  _planPreviewData = data;

  const room = data.room;
  const { scale, cx, cy, w2sx, w2sy } = planTransform(room.width, room.depth);
  // Update global drag info so the single window-level listener has current scale/transform
  _planDragInfo = { scale, w2sx, w2sy };

  // Setup drag events for the canvas container to allow drop
  const wrap = document.getElementById("plan-canvas-wrap");
  wrap.ondragover = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; };
  wrap.ondrop = handleYapbozDrop;

  const floor = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
  let pointsStr = "";
  if (_drawnRoom && _drawnRoom.points) {
    const dcx = _drawnRoom.center_x, dcy = _drawnRoom.center_y;
    pointsStr = _drawnRoom.points.map(p => `${w2sx(p[0]-dcx)},${w2sy(p[1]-dcy)}`).join(" ");
  } else {
    const hw = room.width / 2, hd = room.depth / 2;
    pointsStr = `${w2sx(-hw)},${w2sy(-hd)} ${w2sx(hw)},${w2sy(-hd)} ${w2sx(hw)},${w2sy(hd)} ${w2sx(-hw)},${w2sy(hd)}`;
  }
  floor.setAttribute("points", pointsStr);
  floor.setAttribute("fill", "#f8fafc");
  floor.setAttribute("stroke", "#cbd5e1");
  floor.setAttribute("stroke-width", "2");
  canvas.appendChild(floor);

  data.placed.forEach((p, idx) => {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "yapboz-item cursor-move group");
    g.dataset.idx = idx;
    g.dataset.assetId = p.asset_id;

    const dims = p.dimensions_m || { width: 0.8, depth: 0.8 };
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    const rw = dims.width * scale;
    const rd = dims.depth * scale;
    
    rect.setAttribute("width", rw);
    rect.setAttribute("height", rd);
    rect.setAttribute("x", -rw/2);
    rect.setAttribute("y", -rd/2);
    rect.setAttribute("rx", "4");
    const isSelected = idx === _selectedIdx;
    const specForItem = lastCoachResult?.specs?.find(s => (s.slot || s.asset_id) === p.slot);
    // is_elevated: server confirms OR client spec has on_surface set
    const isElevated = !!(p.is_elevated || specForItem?.on_surface);
    let fillColor = p.asset_id?.startsWith('sf_') ? "#dbeafe" : "#e0e7ff";
    let strokeColor = p.asset_id?.startsWith('sf_') ? "#3b82f6" : "#6366f1";
    if (isElevated) { fillColor = "#fef9c3"; strokeColor = "#ca8a04"; }
    if (isSelected) { fillColor = "#fef3c7"; strokeColor = "#f59e0b"; }
    rect.setAttribute("fill", fillColor);
    rect.setAttribute("stroke", strokeColor);
    rect.setAttribute("stroke-width", isSelected ? "2.5" : (isElevated ? "2" : "1.5"));
    rect.setAttribute("stroke-dasharray", isElevated && !isSelected ? "5 2" : "none");
    rect.setAttribute("class", "transition-colors group-hover:fill-indigo-200");

    const sx = w2sx(p.location[0]);
    const sy = w2sy(p.location[1]);
    const rotDeg = -p.rotation_z;
    g.setAttribute("transform", `translate(${sx},${sy}) rotate(${rotDeg})`);

    g.appendChild(rect);

    // Elevated badge: küçük "↑" ikonu sol üst köşede (sadece yüzey üstü öğelerde)
    if (isElevated) {
      const badge = document.createElementNS("http://www.w3.org/2000/svg", "text");
      badge.textContent = "↑";
      badge.setAttribute("x", -rw/2 + 3);
      badge.setAttribute("y", -rd/2 + 9);
      badge.setAttribute("font-size", "10");
      badge.setAttribute("fill", "#92400e");
      badge.setAttribute("font-weight", "bold");
      g.appendChild(badge);
    }

    // Ön yüz göstergesi — kırmızı çizgi. Yüzey öğelerinde gösterme (zemin yok).
    // facing_correction_z = 180 → model "-Y" eksenli (desk, lounge chair):
    //   grup rotate(-rotation_z) içinde kırmızı çizgi +y kenarda doğru görünür.
    // facing_correction_z = 0  → model "+Y" eksenli (sofa, office chair vs.):
    //   +y kenarda arka yüzü gösterir, -y kenarda ön yüzü doğru gösterir.
    if (!isElevated) {
      const fcorr = (p.facing_correction_z || 0) % 360;
      const facingY = (fcorr === 180) ? rd / 2 : -rd / 2;
      const facing = document.createElementNS("http://www.w3.org/2000/svg", "line");
      facing.setAttribute("x1", -rw/2); facing.setAttribute("y1", facingY);
      facing.setAttribute("x2",  rw/2); facing.setAttribute("y2", facingY);
      facing.setAttribute("stroke", "#dc2626");
      facing.setAttribute("stroke-width", isSelected ? "4" : "3");
      g.appendChild(facing);
    }

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.textContent = _cleanDisplayName(p.name || p.slot || p.asset_id);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("dy", "0.35em");
    text.setAttribute("font-size", "9");
    text.setAttribute("fill", "#4338ca");
    text.setAttribute("font-weight", "bold");
    g.appendChild(text);

    const overlay = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    overlay.setAttribute("width", rw);
    overlay.setAttribute("height", rd);
    overlay.setAttribute("x", -rw/2);
    overlay.setAttribute("y", -rd/2);
    overlay.setAttribute("fill", "transparent");
    overlay.setAttribute("style", "pointer-events: all;");
    
    overlay.onmousedown = (e) => {
      e.stopPropagation();
      g.parentElement.appendChild(g);  // bring to front
      _planDrag = { p, g, idx, startX: e.clientX, startY: e.clientY, didMove: false };
    };

    overlay.ondblclick = (e) => {
      e.stopPropagation();
      p.rotation_z = (p.rotation_z + 90) % 360;
      const newRot = -p.rotation_z;
      const curT = g.getAttribute("transform").split("rotate")[0];
      g.setAttribute("transform", `${curT} rotate(${newRot})`);
      const spec = lastCoachResult.specs.find(s => (s.slot||s.asset_id) === p.slot);
      if (spec) spec.rotation_override = p.rotation_z;
      if (idx === _selectedIdx) {
        const rotInput = document.getElementById('yep-rot');
        if (rotInput) rotInput.value = p.rotation_z;
      }
    };

    overlay.oncontextmenu = (e) => {
      e.preventDefault();
      if (confirm(`'${p.name || p.slot}' silinsin mi?`)) {
        lastCoachResult.specs = lastCoachResult.specs.filter(s => (s.slot||s.asset_id) !== p.slot);
        data.placed = data.placed.filter(it => it.slot !== p.slot);
        if (_selectedIdx === idx) deselectYapbozItem();
        renderPlanPreview(data);
      }
    };

    g.appendChild(overlay);
    canvas.appendChild(g);
  });

  // ── Sketchfab placeholder items (not yet in local catalog) ──────
  const sfSpecs = (lastCoachResult?.specs || []).filter(s => s.sf_uid && !s.asset_id);
  sfSpecs.forEach((s, i) => {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const rw = scale, rd = scale; // default 1m × 1m
    // Place in a row below local items
    const sx = w2sx(-1 + i * 1.2);
    const sy = w2sy(-room.depth / 2 + 0.7);
    g.setAttribute("transform", `translate(${sx},${sy})`);

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("width", rw); rect.setAttribute("height", rd);
    rect.setAttribute("x", -rw/2); rect.setAttribute("y", -rd/2);
    rect.setAttribute("rx", "4");
    rect.setAttribute("fill", "#dbeafe"); rect.setAttribute("stroke", "#3b82f6");
    rect.setAttribute("stroke-width", "1.5"); rect.setAttribute("stroke-dasharray", "4 2");
    g.appendChild(rect);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("text-anchor", "middle"); label.setAttribute("dy", "-0.2em");
    label.setAttribute("font-size", "8"); label.setAttribute("fill", "#1d4ed8");
    label.setAttribute("font-weight", "bold"); label.textContent = "SF";
    g.appendChild(label);

    const name = document.createElementNS("http://www.w3.org/2000/svg", "text");
    name.setAttribute("text-anchor", "middle"); name.setAttribute("dy", "1em");
    name.setAttribute("font-size", "7"); name.setAttribute("fill", "#3b82f6");
    name.textContent = (s.sf_name || '').slice(0, 14);
    g.appendChild(name);

    canvas.appendChild(g);
  });
}

function handleYapbozDrop(e) {
  e.preventDefault();
  if (!lastCoachResult) {
    alert("Lütfen önce bir oda boyutu belirlemek için 'Prompt Geliştir'e basın.");
    return;
  }
  
  const raw = e.dataTransfer.getData('application/json');
  if (!raw) return;
  const data = JSON.parse(raw);
  
  // Calculate relative world coords from drop pixel pos
  const rect = document.getElementById("plan-canvas").getBoundingClientRect();
  const px = e.clientX - rect.left;
  const py = e.clientY - rect.top;
  
  const { s2wx, s2wy } = planTransform(lastCoachResult.room.width, lastCoachResult.room.depth);
  const wx = s2wx(px);
  const wy = s2wy(py);

  if (data.type === 'sketchfab') {
    const assetId = `sf_${data.uid.slice(0, 12)}`;
    // Deduplicate: update existing SF spec instead of adding another
    const existingSf = lastCoachResult.specs.find(s => s.sf_uid === data.uid);
    if (existingSf) {
      existingSf.location_override = [wx, wy, 0];
      existingSf._manual = true;
    } else {
      lastCoachResult.specs.push({
        slot: data.name.slice(0, 15),
        asset_id: data.is_local ? assetId : null,
        sf_uid: data.uid,
        subcategory: 'furniture',
        location_override: [wx, wy, 0],
        placement: 'manual',
        _manual: true,
      });
    }
  } else {
    // Standard local asset — deduplicate by asset_id
    const existing = lastCoachResult.specs.find(s => s.asset_id === data.id);
    if (existing) {
      existing.location_override = [wx, wy, 0];
      existing.placement = 'manual';
      existing._manual = true;
    } else {
      lastCoachResult.specs.push({
        slot: data.name || data.id,
        asset_id: data.id,
        location_override: [wx, wy, 0],
        placement: 'manual',
        _manual: true,
      });
    }
  }
  
  fetchAndRenderPlanPreview();
}

function resetPlanOverrides() {
  if (!lastCoachResult) return;
  lastCoachResult.specs.forEach(s => {
    delete s.location_override;
    delete s.rotation_override;
  });
  deselectYapbozItem();
  fetchAndRenderPlanPreview();
}

// ── Yapboz öğe düzenleme paneli (yön / rotasyon) ───────────────────

function selectYapbozItem(idx) {
  if (!_planPreviewData || !_planPreviewData.placed[idx]) return;
  _selectedIdx = idx;
  const p = _planPreviewData.placed[idx];

  const panel = document.getElementById('yapboz-edit-panel');
  if (panel) panel.classList.remove('hidden');

  const label = document.getElementById('yep-asset-label');
  if (label) label.textContent = _cleanDisplayName(p.name || p.slot || p.asset_id) || '—';

  const rotInput = document.getElementById('yep-rot');
  if (rotInput) rotInput.value = ((Math.round(p.rotation_z) % 360) + 360) % 360;

  const msg = document.getElementById('yep-save-msg');
  if (msg) { msg.classList.add('hidden'); msg.textContent = ''; }

  // Yüzey dropdown'ını diğer yerleştirilmiş nesnelerle doldur
  const surfaceSel = document.getElementById('yep-surface');
  if (surfaceSel) {
    const spec = lastCoachResult?.specs?.find(s => (s.slot || s.asset_id) === p.slot);
    const curSurface = spec?.on_surface || '';
    const otherOptions = (_planPreviewData.placed || [])
      .filter((_, i) => i !== idx)
      .map(item => {
        const itemSlot = item.slot || item.asset_id;
        const itemLabel = item.slot || item.name || item.asset_id;
        const h = item.dimensions_m?.height;
        const suffix = h ? ` (${Number(h).toFixed(2)}m yüksek)` : '';
        const sel = curSurface === itemSlot ? ' selected' : '';
        return `<option value="${itemSlot}"${sel}>${itemLabel}${suffix}</option>`;
      }).join('');
    surfaceSel.innerHTML = `<option value=""${!curSurface ? ' selected' : ''}>Zemin (varsayılan)</option>${otherOptions}`;
  }

  // Seçili öğeyi vurgula (yeniden çiz)
  renderPlanPreview(_planPreviewData);
}

function updateYapbozSurface() {
  if (_selectedIdx === null || !_planPreviewData) return;
  const p = _planPreviewData.placed[_selectedIdx];
  if (!p) return;
  const val = document.getElementById('yep-surface')?.value || '';
  const spec = lastCoachResult?.specs?.find(s => (s.slot || s.asset_id) === p.slot);
  if (spec) {
    if (val) spec.on_surface = val;
    else delete spec.on_surface;
  }
  // Re-fetch layout so the item moves to the parent surface's XY position
  const keepSlot = p.slot;
  fetchAndRenderPlanPreview().then(() => {
    // Re-select the same item after re-render (find its new index)
    if (_planPreviewData) {
      const newIdx = _planPreviewData.placed.findIndex(x => x.slot === keepSlot);
      if (newIdx >= 0) selectYapbozItem(newIdx);
    }
  }).catch(() => {});
}

function deselectYapbozItem() {
  _selectedIdx = null;
  const panel = document.getElementById('yapboz-edit-panel');
  if (panel) panel.classList.add('hidden');
  if (_planPreviewData) renderPlanPreview(_planPreviewData);
}

function updateYapbozRotation() {
  if (_selectedIdx === null || !_planPreviewData) return;
  const p = _planPreviewData.placed[_selectedIdx];
  if (!p) return;
  let val = parseInt(document.getElementById('yep-rot').value, 10) || 0;
  val = ((val % 360) + 360) % 360;
  p.rotation_z = val;
  const spec = lastCoachResult.specs.find(s => (s.slot||s.asset_id) === p.slot);
  if (spec) spec.rotation_override = val;
  renderPlanPreview(_planPreviewData);
}

async function applyFacingCorrection(deg) {
  if (_selectedIdx === null || !_planPreviewData) return;
  const p = _planPreviewData.placed[_selectedIdx];
  const msg = document.getElementById('yep-save-msg');
  if (!p || !p.asset_id) {
    if (msg) { msg.textContent = 'Bu öğe için asset bulunamadı.'; msg.className = 'text-[11px] rounded px-2 py-0.5 bg-red-50 text-red-700'; }
    return;
  }
  if (msg) { msg.textContent = '⏳ Kaydediliyor...'; msg.className = 'text-[11px] rounded px-2 py-0.5 bg-blue-50 text-blue-700'; }
  try {
    const r = await fetch(`${API_BASE}/catalog/asset/${p.asset_id}/facing`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ facing_correction_z: deg }),
    });
    const d = await r.json();
    if (d.ok) {
      if (msg) { msg.textContent = `✓ Ön yüz kaydedildi (${deg}°)`; msg.className = 'text-[11px] rounded px-2 py-0.5 bg-green-50 text-green-700'; }
      // Katalog değişti → önizlemeyi tazele (seçimi koru)
      const keepIdx = _selectedIdx;
      await fetchAndRenderPlanPreview();
      if (_planPreviewData?.placed[keepIdx]) selectYapbozItem(keepIdx);
    } else {
      if (msg) { msg.textContent = d.error || 'Hata'; msg.className = 'text-[11px] rounded px-2 py-0.5 bg-red-50 text-red-700'; }
    }
  } catch (e) {
    if (msg) { msg.textContent = 'Hata: ' + e.message; msg.className = 'text-[11px] rounded px-2 py-0.5 bg-red-50 text-red-700'; }
  }
}

function removeFromYapboz() {
  if (_yapbozLocked) return;  // kilitli ise silmeye izin verme
  if (_selectedIdx === null || !_planPreviewData) return;
  const p = _planPreviewData.placed[_selectedIdx];
  if (!p) return;
  lastCoachResult.specs = lastCoachResult.specs.filter(s => (s.slot||s.asset_id) !== p.slot);
  deselectYapbozItem();
  fetchAndRenderPlanPreview();
}

async function loadYapbozCatalog() {
  const sel = document.getElementById("yapboz-asset-sel");
  if (!sel) return;
  try {
    const res = await fetch(`${API_BASE}/asset-manager/catalog`);
    const data = await res.json();
    if (data.assets) {
      sel.innerHTML = '<option value="">Katalogdan asset ekle...</option>' + 
        data.assets.map(a => `<option value="${a.id}">${a.name} (${a.subcategory})</option>`).join("");
    }
  } catch (e) {
    console.error("Yapboz catalog load error:", e);
  }
}

// "+ Ekle" butonu — seçili kataloğu yapboza ekler
async function addCatalogAssetToYapboz() {
  const sel = document.getElementById("yapboz-asset-sel");
  const assetId = sel?.value;
  if (!assetId) return;
  if (!lastCoachResult) {
    lastCoachResult = { room: { width: 5, depth: 4, height: 2.7, type: '', style: '' }, specs: [], house: null };
    document.getElementById("plan-canvas-wrap")?.classList.remove("hidden");
  }
  try {
    const res = await fetch(`${API_BASE}/catalog/asset/${assetId}`);
    const data = await res.json();
    if (data.asset) {
      const a = data.asset;
      const _WALL_SUBCATS = new Set([
        "wardrobe","bookshelf","tv_stand","dresser","console_table",
        "kitchen_counter","bathtub","toilet","floor_lamp","plant",
        "artwork","mirror","chandelier","refrigerator","bench","bar_stool",
      ]);
      const defaultPlacement = _WALL_SUBCATS.has(a.subcategory) ? "east_wall" : "center";

      // Deduplicate: aynı asset_id zaten varsa yeni spec ekleme
      const existing = lastCoachResult.specs.find(s => s.asset_id === a.id);
      if (!existing) {
        lastCoachResult.specs.push({
          slot:                a.id,
          asset_id:            a.id,
          subcategory:         a.subcategory,
          placement:           defaultPlacement,
          allow_room_mismatch: true,
          _manual:             true,   // coach update'ten korur
        });
      }
      await fetchAndRenderPlanPreview();
      sel.value = "";
    }
  } catch (err) { console.error(err); }
}

function openYapbozManual() {
  if (!lastCoachResult) {
    lastCoachResult = { room: { width: 5, depth: 4, height: 2.7 }, specs: [] };
  }
  document.getElementById("plan-canvas-wrap").classList.remove("hidden");
  fetchAndRenderPlanPreview();
}

// ── Materials ────────────────────────────────────────────────────
function switchCoachMatMode(mode) {
  _coachMatMode = mode;
  const pm = document.getElementById('coach-mat-mode-preset');
  const fm = document.getElementById('coach-mat-mode-file');
  if (pm) pm.className = `px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${mode==='preset' ? 'bg-white text-amber-800 shadow-sm' : 'text-amber-600'}`;
  if (fm) fm.className = `px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${mode==='file' ? 'bg-white text-amber-800 shadow-sm' : 'text-amber-600'}`;
  _populateCoachMatDropdowns();
}

async function _populateCoachMatDropdowns() {
  const fSel = document.getElementById('coach-floor-tex');
  const wSel = document.getElementById('coach-wall-tex');
  if (!fSel || !wSel) return;
  try {
    if (_coachMatMode === 'preset') {
      const res = await fetch(`${API_BASE}/materials/presets`);
      const data = await res.json();
      const options = data.map(p => `<option value="${p.name}">${p.name}</option>`).join('');
      fSel.innerHTML = '<option value="">Yok</option>' + options;
      wSel.innerHTML = '<option value="">Yok</option>' + options;
    } else {
      const res = await fetch(`${API_BASE}/files/textures`);
      const data = await res.json();
      const options = data.textures.map(t => `<option value="${t.path}">${t.name}</option>`).join('');
      fSel.innerHTML = '<option value="">Yok</option>' + options;
      wSel.innerHTML = '<option value="">Yok</option>' + options;
    }
  } catch (e) { console.error(e); }
}

async function applyCoachMaterials() {
  const fVal = document.getElementById('coach-floor-tex')?.value;
  const wVal = document.getElementById('coach-wall-tex')?.value;
  const btn    = document.getElementById('btn-coach-mat');
  const icon   = document.getElementById('coach-mat-icon');
  const result = document.getElementById('coach-mat-result');
  if (!fVal && !wVal) return;
  if (btn)  btn.disabled  = true;
  if (icon) icon.textContent = "⏳";
  if (result) result.textContent = "Uygulanıyor...";

  try {
    // Presets listesini bir kez çek
    let presets = [];
    if (_coachMatMode === 'preset') {
      const r = await fetch(`${API_BASE}/materials/presets`);
      presets = await r.json();
    }

    // Sahnedeki gerçek duvar isimlerini al; bulamazsa fallback listesini kullan
    let wallNames = ['Room_Wall_North','Room_Wall_South','Room_Wall_East','Room_Wall_West'];
    try {
      const sr = await fetch(`${API_BASE}/blender/scene`, { signal: AbortSignal.timeout(3000) });
      const sd = await sr.json();
      const fromScene = (sd.objects || [])
        .filter(o => o.name && o.name.startsWith('Room_Wall'))
        .map(o => o.name);
      if (fromScene.length) wallNames = fromScene;
    } catch { /* sahneden okunamazsa fallback'le devam et */ }

    // Materyal body'sini oluştur
    const buildBody = (objectNames, val) => {
      if (_coachMatMode === 'preset') {
        const p = presets.find(x => x.name === val);
        if (!p) return null;
        const m = p.mat || {};
        // Preset mode: pbr veya file olabilir — diff_path/rough_path/normal_path doğru alanlar
        if (m.mode === 'file') {
          return { object_names: objectNames, mode: 'file', texture_path: m.texture_path };
        }
        return {
          object_names: objectNames,
          mode:         'pbr',
          diff_path:    m.diff_path   || '',
          rough_path:   m.rough_path  || '',
          normal_path:  m.normal_path || '',
        };
      }
      // Dosya modu: val doğrudan dosya yolu
      return { object_names: objectNames, mode: 'file', texture_path: val };
    };

    const apply = async (objectNames, val) => {
      const body = buildBody(objectNames, val);
      if (!body) return;
      await fetch(`${API_BASE}/blender/apply-material`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });
    };

    if (fVal) await apply(['Room_Floor'], fVal);
    if (wVal) await apply(wallNames, wVal);

    if (result) result.textContent = "✓ Tamamlandı!";
  } catch (e) {
    if (result) result.textContent = "Hata: " + e.message;
  } finally {
    if (btn)  btn.disabled  = false;
    if (icon) icon.textContent = "🎨";
  }
}

function clearResponse() {
  const rs = document.getElementById("response-section");
  if (rs) rs.classList.add("hidden");
  const rb = document.getElementById("response-box");
  if (rb) rb.textContent = "";
  const pi = document.getElementById("prompt-input");
  if (pi) pi.value = "";
}

// ── Sketchfab Recommendations ──────────────────────────────────

let _sfCoachOffsets = {}; 

const _SF_TRANS_MAP = {
  "tv": "television", "buzdolabı": "refrigerator", "buzdolabi": "refrigerator",
  "kitaplık": "bookshelf", "kitaplik": "bookshelf", "çalışma masası": "desk",
  "masa": "table", "zemin lambası": "floor lamp", "yer lambası": "floor lamp",
  "koltuk": "armchair", "sandalye": "chair", "kanepe": "sofa", "yatak": "bed",
  "fırın": "oven", "ocak": "stove", "çamaşır makinesi": "washing machine",
  "bulaşık makinesi": "dishwasher", "halı": "rug", "bitki": "plant", "ayna": "mirror",
  "oyuncak ayı": "toy bear", "oyuncak ayi": "toy bear", "sehpa": "coffee table",
  "orta sehpa": "coffee table", "yan sehpa": "side table", "kahve masası": "coffee table",
  "masa lambası": "desk lamp", "ayaklı lamba": "floor lamp"
};

async function _triggerSfRecommendations(warnings) {
  _sfCoachOffsets = {}; 
  const itemsToSearch = new Set();
  
  warnings.forEach(w => {
    if (!w.startsWith("❌")) return;
    let mainMatch = w.match(/❌\s*(?:Preset slot\s*[–-]\s*)?([^:]+):/);
    if (mainMatch) {
      let name = mainMatch[1].split('(')[0].trim().toLowerCase();
      itemsToSearch.add(name);
    }
    let subMatch = w.match(/"([^"]+)"\s+subcategory'sinde/);
    if (subMatch) {
      itemsToSearch.add(subMatch[1].replace(/_/g, ' '));
    }
  });

  const missingItemsRaw = Array.from(itemsToSearch);
  const container = document.getElementById("sf-coach-recommendations");
  const list = document.getElementById("sf-recommendations-list");
  const globalLoader = document.getElementById("sf-global-loader");
  
  if (!missingItemsRaw.length || !container || !list) {
    if (container) container.classList.add("hidden");
    return;
  }

  const unifiedSet = new Set();
  const displayMap = {}; 
  
  missingItemsRaw.forEach(item => {
    const english = _SF_TRANS_MAP[item] || item;
    unifiedSet.add(english);
    if (!displayMap[english]) displayMap[english] = item;
  });

  const missingItems = Array.from(unifiedSet);

  container.classList.remove("hidden");
  if (globalLoader) globalLoader.classList.remove("hidden");
  list.innerHTML = `
    <div id="sf-placeholder" class="py-4 text-center text-[10px] text-blue-400 font-medium">
      ${missingItems.length} kategori için modeller getiriliyor...
    </div>
  `;
  
  let finishedCount = 0;
  let totalFound = 0;

  missingItems.forEach(englishQ => {
    const originalQ = displayMap[englishQ];
    _sfCoachOffsets[englishQ] = 0;
    _fetchNextSfPage(englishQ, originalQ).then(found => {
      finishedCount++;
      if (found) {
        totalFound++;
        document.getElementById("sf-placeholder")?.remove();
      }
      if (finishedCount === missingItems.length) {
        if (globalLoader) globalLoader.classList.add("hidden");
        if (totalFound === 0) {
          list.innerHTML = `<div class="py-6 text-center text-blue-400">
            <div class="text-xl mb-1">😕</div>
            <p class="text-[10px] font-bold uppercase tracking-tight">Uygun model bulunamadı.</p>
          </div>`;
        }
      }
    }); 
  });
}

async function _fetchNextSfPage(englishQ, displayQ = null) {
  const originalQ = displayQ || englishQ;
  const offset = _sfCoachOffsets[englishQ] || 0;
  const list = document.getElementById("sf-recommendations-list");
  if (!list) return false;

  const cardId = `sf-card-${englishQ.replace(/\s+/g, '-')}`;
  let card = document.getElementById(cardId);
  
  if (!card) {
    list.insertAdjacentHTML('beforeend', `
      <div id="${cardId}" class="bg-white rounded-xl border border-blue-100 shadow-sm overflow-hidden flex flex-col hidden">
        <div class="px-3 py-1.5 bg-blue-100/30 border-b border-blue-50 flex justify-between items-center">
          <div class="flex items-center gap-2">
            <span class="text-[10px] font-bold text-blue-900 uppercase tracking-tight">Eksik: "${originalQ}"</span>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-[9px] text-blue-300 font-mono italic">🔍 ${englishQ}</span>
            <button onclick="_fetchNextSfPage('${englishQ}', '${originalQ}')" 
              class="text-[9px] bg-white border border-indigo-200 text-indigo-600 px-2 py-0.5 rounded-md hover:bg-indigo-600 hover:text-white transition-all font-bold">
              🔄 Sıradaki 4'lü
            </button>
          </div>
        </div>
        <div class="sf-grid p-2 overflow-x-auto scrollbar-hide">
          <div class="sf-inner-grid flex gap-3 min-w-max pb-1"></div>
        </div>
      </div>
    `);
    card = document.getElementById(cardId);
  }

  const innerGrid = card.querySelector('.sf-inner-grid');
  if (innerGrid && (innerGrid.innerHTML.includes("yükleniyor") || innerGrid.innerHTML === "")) {
    innerGrid.innerHTML = `<div class="w-full py-4 text-center text-[10px] text-blue-300 animate-pulse">Modeller yükleniyor...</div>`;
  }

  try {
    const res = await fetch(`${API_BASE}/sketchfab/search?q=${encodeURIComponent(englishQ)}&count=24`);
    const data = await res.json();
    const allRecs = data.results || [];
    const pageSize = 4;
    const pageRecs = allRecs.slice(offset, offset + pageSize);
    
    if (pageRecs.length === 0 && offset > 0) {
      _sfCoachOffsets[englishQ] = 0;
      return _fetchNextSfPage(englishQ, originalQ);
    }

    if (pageRecs.length > 0) {
      card.classList.remove('hidden');
      innerGrid.innerHTML = pageRecs.map(m => {
        const isLocal = m.is_local;
        _sfModelCache[m.uid] = m; // Update cache
        
        const inYapboz = lastCoachResult?.specs?.some(s => s.sf_uid === m.uid);
        return `
          <div class="w-36 bg-gray-50 rounded-lg overflow-hidden flex flex-col border border-gray-100 relative">
            <div class="relative h-16">
              <img src="${m.thumbnailUrl}" class="w-full h-full object-cover" onerror="this.src='/ui/img/no-thumb.png'" />
              <!-- Yapboza Ekle — resmin üstünde -->
              <button onclick="addSfToYapboz('${m.uid}')"
                class="absolute inset-x-0 bottom-0 py-1 text-[8px] font-black flex items-center justify-center gap-1 transition-all
                  ${inYapboz ? 'bg-emerald-500/90 text-white' : 'bg-emerald-600/90 hover:bg-emerald-600 text-white'}">
                ${inYapboz ? '✓ Yapbozda' : '📐 Yapboza Ekle'}
              </button>
              ${isLocal ? `
                <div class="absolute top-1 right-1 bg-emerald-500 text-white text-[7px] px-1 rounded-sm font-bold shadow-sm">
                  KÜTÜPHANEDE
                </div>
              ` : ''}
            </div>
            <div class="p-1.5 flex flex-col flex-1">
              <div class="text-[8px] font-bold text-gray-800 line-clamp-1 mb-1" title="${m.name}">${m.name}</div>
              ${isLocal ? `
                <div class="w-full bg-emerald-50 text-emerald-600 py-0.5 rounded text-[8px] font-black text-center border border-emerald-100">
                  ✅ İNDİRİLDİ
                </div>
              ` : `
                <button onclick="downloadSketchfab('${m.uid}')"
                  class="w-full bg-indigo-100 hover:bg-indigo-200 text-indigo-700 py-0.5 rounded text-[8px] font-bold transition-colors">
                  📥 İndir
                </button>
              `}
            </div>
          </div>
        `;
      }).join('');
      _sfCoachOffsets[englishQ] = (offset + pageSize) % allRecs.length;
      return true;
    } else {
      card.remove();
      return false;
    }
  } catch (e) {
    if (innerGrid) innerGrid.innerHTML = `<div class="text-[9px] text-red-400 p-2">Yüklenemedi.</div>`;
    return false;
  }
}
