// ── app.js ────────────────────────────────────────────────────────
// Tab navigation, visual builder, house model, calibration, health check,
// and DOMContentLoaded initialization.

// ── Tab Navigation ─────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    const active = btn.id === `tab-btn-${name}`;
    btn.classList.toggle("border-indigo-600", active);
    btn.classList.toggle("text-indigo-700",   active);
    btn.classList.toggle("border-transparent", !active);
    btn.classList.toggle("text-gray-500",     !active);
  });
  document.getElementById("tab-tasarim").classList.toggle("hidden", name !== "tasarim");
  document.getElementById("tab-sahne").classList.toggle("hidden",   name !== "sahne");
  document.getElementById("tab-materyal").classList.toggle("hidden", name !== "materyal");
  document.getElementById("tab-ciz").classList.toggle("hidden",      name !== "ciz");
  document.getElementById("tab-modeller").classList.toggle("hidden", name !== "modeller");
  document.getElementById("tab-sketchfab").classList.toggle("hidden", name !== "sketchfab");
  document.getElementById("tab-sistem").classList.toggle("hidden",    name !== "sistem");

  if (name === "sahne"  && !_sceneData) loadBlenderScene();
  if (name === "sistem") initSistemTab();
  if (name === "materyal") { loadTextureList(); refreshMatTargets(); renderSavedSets(); loadRoomStructureForMat(); loadTextureGallery(); }
  if (name === "ciz") { initDrawCanvas(); renderSavedDrawRooms(); }
  if (name === "modeller" && !_modelsLoaded) loadModelsTab(false);
  if (name === "sketchfab") _modelSource = 'sketchfab';
  if (name !== "modeller") document.getElementById("model-sel-bar").classList.add("hidden");
}

// ── Visual Builder ─────────────────────────────────────────────
function addFurnitureRow() {
  const list = document.getElementById("furniture-list");
  const idx = Date.now();
  const row = document.createElement("div");
  row.className = "furniture-row rounded-lg p-3 flex flex-wrap gap-2 items-center";
  row.id = `fur-${idx}`;
  row.innerHTML = `
    <select class="fur-type border border-gray-300 rounded-md px-2 py-1 text-xs flex-1 min-w-24">
      ${FURNITURE_TYPES.map(t => `<option value="${t}">${t}</option>`).join("")}
    </select>
    <select class="fur-place border border-gray-300 rounded-md px-2 py-1 text-xs flex-1 min-w-32">
      ${PLACEMENTS.map(p => `<option value="${p}">${p}</option>`).join("")}
    </select>
    <select class="fur-rot border border-gray-300 rounded-md px-2 py-1 text-xs w-20">
      ${ROTATIONS.map(r => `<option value="${r}">${r}°</option>`).join("")}
    </select>
    <button onclick="removeFurRow('fur-${idx}')" class="text-red-400 hover:text-red-600 text-sm font-bold">✕</button>
  `;
  list.appendChild(row);
}

function removeFurRow(id) {
  document.getElementById(id)?.remove();
}

function buildPrompt() {
  const room = document.getElementById("sel-room").value;
  const style = document.getElementById("sel-style").value;
  const w = document.getElementById("sel-width").value;
  const d = document.getElementById("sel-depth").value;
  const h = document.getElementById("sel-height").value;

  const rows = document.querySelectorAll("#furniture-list .furniture-row");
  let furnitureParts = [];
  rows.forEach(row => {
    const type = row.querySelector(".fur-type").value;
    const place = row.querySelector(".fur-place").value;
    const rot = row.querySelector(".fur-rot").value;
    furnitureParts.push(`${type} (${place}, ${rot}°)`);
  });

  const roomLabel = {
    living_room: "oturma odası", office: "ofis", bedroom: "yatak odası",
    dining_room: "yemek odası", kitchen: "mutfak", bathroom: "banyo",
  }[room] || room;

  let prompt = `${w}x${d}m`;
  if (h !== "2.7") prompt += ` ${h}m tavan`;
  if (style) prompt += ` ${style} tarzında`;
  prompt += ` ${roomLabel} tasarla`;
  if (furnitureParts.length) {
    prompt += `, özel mobilya: ${furnitureParts.join(", ")}`;
  }

  document.getElementById("prompt-input").value = prompt;
  document.getElementById("prompt-input").focus();
}

async function buildAndSubmit() {
  buildPrompt();
  await submitDesign();
}

// ── Example Cards ──────────────────────────────────────────────
function useExample(card) {
  const text = card.querySelector(".prompt-text").textContent;
  document.getElementById("prompt-input").value = text;
  document.getElementById("prompt-input").focus();
}

function copyPrompt(btn, e) {
  e.stopPropagation();
  const text = btn.closest(".card-example").querySelector(".prompt-text").textContent;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = "✓ Kopyalandı";
    setTimeout(() => (btn.textContent = orig), 1500);
  });
}

// ── House Model ────────────────────────────────────────────────
async function loadHouseList() {
  try {
    const r = await fetch(`${API_BASE}/catalog/houses`, { signal: AbortSignal.timeout(3000) });
    const data = await r.json();
    const sel = document.getElementById("house-sel");
    sel.innerHTML = '<option value="">-- Ev seçin --</option>';
    const text = data.houses || "";
    const ids = [...text.matchAll(/ID:\s*([\w_]+)/g)].map(m => m[1]);
    const names = [...text.matchAll(/Name:\s*(.+)/g)].map(m => m[1].trim());
    ids.forEach((id, i) => {
      sel.insertAdjacentHTML("beforeend", `<option value="${id}">${names[i] || id}</option>`);
    });
  } catch { /* API not running yet */ }
}

async function loadHouseRooms() {
  const houseId = document.getElementById("house-sel").value;
  const roomSel = document.getElementById("room-sel");
  roomSel.innerHTML = '<option value="">Yükleniyor...</option>';
  if (!houseId) { roomSel.innerHTML = '<option value="">Önce ev seçin</option>'; return; }
  try {
    const r = await fetch(`${API_BASE}/catalog/house/${houseId}/rooms`);
    const data = await r.json();
    roomSel.innerHTML = '<option value="">-- Oda seçin --</option>';
    const text = data.rooms || "";
    const matches = [...text.matchAll(/room_id:\s*([\w_]+)\s*\n\s*name:\s*(.+)/g)];
    _houseRoomsCache[houseId] = matches.map(m => ({ id: m[1], name: m[2].trim() }));
    _houseRoomsCache[houseId].forEach(room => {
      roomSel.insertAdjacentHTML("beforeend", `<option value="${room.id}">${room.name} (${room.id})</option>`);
    });
    if (!matches.length) roomSel.innerHTML = '<option value="">Oda tanımı yok</option>';
  } catch (e) {
    roomSel.innerHTML = '<option value="">Hata: API çalışmıyor</option>';
  }
}

function buildHousePrompt() {
  const houseId = document.getElementById("house-sel").value;
  const roomId  = document.getElementById("room-sel").value;
  const style   = document.getElementById("house-style").value;
  const extra   = document.getElementById("house-extra").value.trim();
  if (!houseId) { alert("Ev modeli seçin."); return; }

  let prompt = `${houseId} evi`;
  if (roomId) prompt += `nin ${roomId} odasını`;
  if (style) prompt += ` ${style} tarzında`;
  prompt += " tasarla";
  if (extra) prompt += `, ${extra}`;

  document.getElementById("prompt-input").value = prompt;
  document.getElementById("prompt-input").focus();
}

async function buildHouseAndSubmit() {
  buildHousePrompt();
  await submitDesign();
}

async function designHouseRoom() {
  const houseId = document.getElementById("house-sel").value;
  const roomId  = document.getElementById("room-sel").value;
  const style   = document.getElementById("house-style").value || "modern";

  if (!houseId) { alert("Ev modeli seçin."); return; }
  if (!roomId)  { alert("Oda seçin."); return; }

  const section = document.getElementById("response-section");
  const box     = document.getElementById("response-box");
  const spinner = document.getElementById("loading-spinner");

  section.classList.remove("hidden");
  spinner.classList.remove("hidden");
  box.textContent = `Deterministik tasarım başlatıldı...\nEv: ${houseId} | Oda: ${roomId} | Stil: ${style}\n`;

  try {
    const res = await fetch(`${API_BASE}/design/house-room`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ house_id: houseId, room_id: roomId, style }),
    });
    const data = await res.json();

    if (data.error) {
      box.textContent = `HATA:\n${data.error}`;
    } else {
      const placedLines = (data.placed || [])
        .map(p => `  • ${p.slot}: ${p.name}  @ [${(p.location||[]).map(v=>v.toFixed(2)).join(", ")}]`)
        .join("\n");
      box.textContent = data.result + (placedLines ? "\n\nYerleştirilen:\n" + placedLines : "");
    }
  } catch (err) {
    box.textContent = `Bağlantı hatası: ${err.message}\n\nAPI çalışıyor mu?  python run_team.py --serve`;
  } finally {
    spinner.classList.add("hidden");
  }
}

async function readCursor() {
  const code = document.getElementById("cursor-result");
  try {
    const r = await fetch(`${API_BASE}/blender/cursor`, { signal: AbortSignal.timeout(5000) });
    const data = await r.json();
    const text = data.result || "";
    const match = text.match(/\[([^\]]+)\]/);
    if (match) {
      _cursorLocation = match[1].split(",").map(Number);
      code.textContent = `[${match[1]}]`;
      code.className = "flex-1 bg-white border border-green-300 rounded-lg px-3 py-1.5 text-xs text-green-700 font-mono";
    } else {
      code.textContent = text || "Blender bağlı değil";
    }
  } catch (e) {
    code.textContent = `Hata: ${e.message}`;
  }
}

async function saveCursorAsRoomOrigin() {
  const houseId = document.getElementById("house-sel").value;
  const roomId  = document.getElementById("room-sel").value;
  const res = document.getElementById("cursor-save-result");
  if (!houseId || !roomId) { alert("Ev ve oda seçin."); return; }
  try {
    const r = await fetch(`${API_BASE}/catalog/house/${houseId}/room/${roomId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin_offset_m: _cursorLocation }),
    });
    const data = await r.json();
    if (data.ok) {
      res.className = "mt-2 text-xs text-green-700 bg-green-50 rounded p-2";
      res.classList.remove("hidden");
      res.textContent = `✓ ${roomId} origin_offset_m = [${_cursorLocation.join(", ")}] kaydedildi.`;
    } else {
      res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
      res.classList.remove("hidden");
      res.textContent = data.error || "Hata";
    }
  } catch (e) {
    res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
    res.classList.remove("hidden");
    res.textContent = `Hata: ${e.message}`;
  }
}

// ── Calibration ───────────────────────────────────────────────
async function loadCatalogAssets() {
  try {
    await fetch(`${API_BASE}/catalog/reload`, { method: "POST", signal: AbortSignal.timeout(3000) }).catch(() => {});
    const res = await fetch(`${API_BASE}/catalog/assets`, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();
    const sel = document.getElementById("cal-asset");
    sel.innerHTML = "";
    const raw = data.assets || "";
    const lines = raw.split("\n").filter(l => l.includes("ID:"));
    if (lines.length === 0) {
      const r2 = await fetch(`${API_BASE}/catalog/search`, { signal: AbortSignal.timeout(3000) });
      const d2 = await r2.json();
      const results = d2.results || "";
      results.split("ID:").slice(1).forEach(chunk => {
        const id = chunk.split("|")[0].trim();
        if (id) sel.insertAdjacentHTML("beforeend", `<option value="${id}">${id}</option>`);
      });
    } else {
      lines.forEach(l => {
        const id = l.replace("ID:", "").split("|")[0].trim();
        sel.insertAdjacentHTML("beforeend", `<option value="${id}">${id}</option>`);
      });
    }
    if (!sel.options.length) sel.innerHTML = '<option value="">Asset bulunamadı</option>';
  } catch {
    document.getElementById("cal-asset").innerHTML = '<option value="">API çalışmıyor</option>';
  }
}

async function testFacing() {
  const assetId = document.getElementById("cal-asset").value;
  if (!assetId) { alert("Bir asset seçin."); return; }
  const res = document.getElementById("cal-result");
  res.className = "mt-2 text-xs text-blue-700 bg-blue-50 rounded p-2";
  res.classList.remove("hidden");
  res.textContent = "Blender'a gönderiliyor...";
  try {
    const r = await fetch(`${API_BASE}/test-facing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: assetId }),
    });
    const data = await r.json();
    res.textContent = data.result || JSON.stringify(data);
  } catch (e) {
    res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
    res.classList.remove("hidden");
    res.textContent = `Hata: ${e.message}`;
  }
}

async function saveCorrection() {
  const assetId = document.getElementById("cal-asset").value;
  const correction = parseFloat(document.getElementById("cal-correction").value) || 0;
  if (!assetId) { alert("Bir asset seçin."); return; }
  const res = document.getElementById("cal-result");
  try {
    const r = await fetch(`${API_BASE}/catalog/asset/${assetId}/facing`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ facing_correction_z: correction }),
    });
    const data = await r.json();
    if (data.ok) {
      res.className = "mt-2 text-xs text-green-700 bg-green-50 rounded p-2";
      res.classList.remove("hidden");
      res.textContent = `✓ ${assetId} → facing_correction_z = ${correction}° kaydedildi.`;
    } else {
      res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
      res.classList.remove("hidden");
      res.textContent = data.error || "Hata";
    }
  } catch (e) {
    res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
    res.classList.remove("hidden");
    res.textContent = `Hata: ${e.message}`;
  }
}

// ── Rotation preset buttons ────────────────────────────────────
function applyRotPreset(rx, ry, rz) {
  document.getElementById("cal-rx").value = rx;
  document.getElementById("cal-ry").value = ry;
  document.getElementById("cal-rz").value = rz;
  // Highlight active preset
  document.querySelectorAll(".rot-preset-btn").forEach(btn => {
    btn.classList.remove("bg-red-100", "border-red-400", "font-semibold");
  });
  event?.currentTarget?.classList.add("bg-red-100", "border-red-400", "font-semibold");
}

// Save both facing (Z) correction AND rotation_correction (X/Y/Z extra)
async function saveAllCorrections() {
  const assetId    = document.getElementById("cal-asset").value;
  const facingZ    = parseFloat(document.getElementById("cal-correction").value) || 0;
  const rx         = parseFloat(document.getElementById("cal-rx").value) || 0;
  const ry         = parseFloat(document.getElementById("cal-ry").value) || 0;
  const rz         = parseFloat(document.getElementById("cal-rz").value) || 0;
  const res        = document.getElementById("cal-result");

  if (!assetId) { alert("Bir asset seçin."); return; }

  res.classList.remove("hidden");
  res.className = "mt-2 text-xs text-blue-700 bg-blue-50 rounded p-2";
  res.textContent = "Kaydediliyor...";

  try {
    // Save facing Z
    const r1 = await fetch(`${API_BASE}/catalog/asset/${assetId}/facing`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ facing_correction_z: facingZ }),
    });
    const d1 = await r1.json();

    // Save rotation_correction
    const r2 = await fetch(`${API_BASE}/catalog/asset/${assetId}/rotation-correction`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rx, ry, rz }),
    });
    const d2 = await r2.json();

    if (d1.ok && d2.ok) {
      res.className = "mt-2 text-xs text-green-700 bg-green-50 rounded p-2";
      res.textContent = `✓ Kaydedildi — facing_z=${facingZ}°  rotation=[${rx},${ry},${rz}]°`;
    } else {
      res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
      res.textContent = d1.error || d2.error || "Hata";
    }
  } catch (e) {
    res.className = "mt-2 text-xs text-red-700 bg-red-50 rounded p-2";
    res.textContent = `Hata: ${e.message}`;
  }
}

// ── LLM Selector ──────────────────────────────────────────────
function selectLLM(llm) {
  currentLLM = llm;
  ['gemini', 'claude'].forEach(id => {
    const btn = document.getElementById(`btn-${id}`);
    if (!btn) return;
    const active = id === llm;
    btn.classList.toggle('active',          active);
    btn.classList.toggle('border-indigo-500', active);
    btn.classList.toggle('text-indigo-700',   active);
    btn.classList.toggle('border-gray-300',  !active);
    btn.classList.toggle('text-gray-600',    !active);
  });
  const indicator = document.getElementById('llm-indicator');
  if (indicator) indicator.textContent = llm === 'gemini' ? 'Gemini kullanılıyor' : 'Claude kullanılıyor';
}

// ── Prompt Chip Shortcuts ─────────────────────────────────────
// Appends a preset sentence to the prompt textarea.
function appendPromptChip(text) {
  const el = document.getElementById("prompt-input");
  if (!el) return;
  const current = el.value.trimEnd();
  el.value = current ? current + " " + text : text;
  el.focus();
  // Clear cached coach result — prompt changed so specs are stale
  lastCoachResult = null;
  // Visual flash to confirm the chip was applied
  el.classList.add("ring-2", "ring-indigo-400");
  setTimeout(() => el.classList.remove("ring-2", "ring-indigo-400"), 600);
}

// Chip: "var olanları koru" — mevcut tüm spec'leri _manual=true olarak işaretle
// (coach sonrasında restore mekanizması bunları geri koyar) + prompt'a metin ekle.
function appendKeepExistingChip() {
  if (lastCoachResult?.specs?.length) {
    lastCoachResult.specs.forEach(s => { s._manual = true; });
  }
  const el = document.getElementById("prompt-input");
  if (!el) return;
  const text = "Mevcut eşyaları koru, sadece yazdığım eşyalar dışına çıkma.";
  const current = el.value.trimEnd();
  el.value = current ? current + " " + text : text;
  el.focus();
  el.classList.add("ring-2", "ring-emerald-400");
  setTimeout(() => el.classList.remove("ring-2", "ring-emerald-400"), 600);
}

// ── Prompt Şablonları ─────────────────────────────────────────
const _PROMPT_TEMPLATES = {
  "sadece-benim-modellerim": {
    title: "Sadece benim modellerim",
    content:
      "Sadece benim belirttiğim modelleri kullan, başka model ekleme, dışına çıkma. " +
      "Katalogdan ekstra mobilya seçme. Verdiğim her modeli odada mantıklı bir konuma yerleştir: " +
      "masaları duvara yakın, sandalyeleri masanın önüne karşılıklı, " +
      "kanepeyi odanın merkezine baksın, dolap ve rafları duvara daya. " +
      "Mobilyalar birbirini kapatmasın, aralarında yürüyüş boşluğu bırak.",
  },
  "ic-mimar": {
    title: "İç mimar yerleşim talimatları",
    content:
      "İç mimar gibi düşün: önce odanın odak noktasını belirle (pencere, TV duvarı veya kuzey duvarı). " +
      "Ana mobilyayı (masa/kanepe/yatak) bu odak noktasına göre konumlandır. " +
      "Her oturma birimi bir şeye baksın — masaya, sehpaya veya oda merkezine. " +
      "Hiçbir koltuk veya sandalye boş duvara bakmasın. " +
      "Giriş kapısından odanın karşı duvarına en az 90 cm yürüyüş yolu bırak. " +
      "Masa + sandalye her zaman karşılıklı dursun: masa duvarda, sandalye masanın önünde masaya baksın. " +
      "Tüm mobilyalar oda sınırları içinde kalsın.",
  },
};

function fillPromptTemplate(key) {
  const tpl = _PROMPT_TEMPLATES[key];
  if (!tpl) return;
  const titleEl   = document.getElementById("sp-title");
  const contentEl = document.getElementById("sp-content");
  if (titleEl)   titleEl.value   = tpl.title;
  if (contentEl) contentEl.value = tpl.content;
  titleEl?.focus();
}

// ── Kayıtlı Promptlar ────────────────────────────────────────
const _SP_KEY = "assetlib_prompts_v1";

function _spLoad()       { try { return JSON.parse(localStorage.getItem(_SP_KEY) || "[]"); } catch { return []; } }
function _spSave(list)   { localStorage.setItem(_SP_KEY, JSON.stringify(list)); }
function _spEsc(s)       { return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }

function toggleSavedPrompts() {
  const body  = document.getElementById("sp-body");
  const arrow = document.getElementById("sp-arrow");
  if (!body) return;
  const opening = body.classList.contains("hidden");
  body.classList.toggle("hidden", !opening);
  if (arrow) arrow.style.transform = opening ? "rotate(180deg)" : "";
  if (opening) _spRender();
}

function addSavedPrompt() {
  const title   = (document.getElementById("sp-title")?.value || "").trim();
  const content = (document.getElementById("sp-content")?.value || "").trim();
  if (!title)   { document.getElementById("sp-title")?.focus();   return; }
  if (!content) { document.getElementById("sp-content")?.focus(); return; }

  const list = _spLoad();
  list.unshift({ id: Date.now(), title, content });
  _spSave(list);

  document.getElementById("sp-title").value   = "";
  document.getElementById("sp-content").value = "";
  _spRender();
}

function loadSavedPrompt(id) {
  const item = _spLoad().find(p => p.id === id);
  if (!item) return;
  const el = document.getElementById("prompt-input");
  if (!el) return;
  const current = el.value.trimEnd();
  el.value = current ? current + " " + item.content : item.content;
  el.focus();
  lastCoachResult = null;
  el.classList.add("ring-2","ring-indigo-400");
  setTimeout(() => el.classList.remove("ring-2","ring-indigo-400"), 600);
}

function deleteSavedPrompt(id) {
  _spSave(_spLoad().filter(p => p.id !== id));
  _spRender();
}

function _spRender() {
  const list    = _spLoad();
  const listEl  = document.getElementById("sp-list");
  const emptyEl = document.getElementById("sp-empty");
  const countEl = document.getElementById("sp-count");

  if (countEl) {
    countEl.textContent = list.length || "";
    countEl.classList.toggle("hidden", !list.length);
  }
  if (!listEl) return;

  if (!list.length) {
    listEl.innerHTML = "";
    emptyEl?.classList.remove("hidden");
    return;
  }
  emptyEl?.classList.add("hidden");

  listEl.innerHTML = list.map(p => `
    <div class="group flex items-start gap-2 px-3 py-2.5 hover:bg-gray-50 transition-colors">
      <div class="flex-1 min-w-0">
        <p class="text-xs font-semibold text-gray-700 truncate mb-0.5">${_spEsc(p.title)}</p>
        <p class="text-[11px] text-gray-400 line-clamp-2 leading-relaxed">${_spEsc(p.content)}</p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0 mt-0.5">
        <button onclick="loadSavedPrompt(${p.id})"
          class="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-2 py-1 rounded-lg transition-colors whitespace-nowrap">
          + Ekle
        </button>
        <button onclick="deleteSavedPrompt(${p.id})"
          class="text-lg leading-none text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all"
          title="Sil">×</button>
      </div>
    </div>`).join("");
}

// Sayfa yüklenince sayacı güncelle
document.addEventListener("DOMContentLoaded", () => {
  const n = _spLoad().length;
  const c = document.getElementById("sp-count");
  if (c && n) { c.textContent = n; c.classList.remove("hidden"); }
}, { once: true });

// ── Yapboz Kilit Toggle ───────────────────────────────────────
function toggleYapbozLock() {
  _yapbozLocked = !_yapbozLocked;

  const btn   = document.getElementById("yapboz-lock-btn");
  const knob  = document.getElementById("yapboz-lock-knob");
  const label = document.getElementById("yapboz-lock-label");
  const rmBtn = document.querySelector('button[onclick="removeFromYapboz()"]');

  if (_yapbozLocked) {
    btn.classList.replace("bg-gray-200", "bg-amber-400");
    knob.classList.replace("translate-x-0", "translate-x-4");
    label.textContent = "🔒 Kilitli";
    label.classList.replace("text-gray-400", "text-amber-600");
    if (rmBtn) rmBtn.classList.add("opacity-30", "pointer-events-none");
    // Tüm mevcut spec'leri _manual yaparak Prompt Geliştir'den koru
    if (lastCoachResult?.specs) lastCoachResult.specs.forEach(s => { s._manual = true; });
  } else {
    btn.classList.replace("bg-amber-400", "bg-gray-200");
    knob.classList.replace("translate-x-4", "translate-x-0");
    label.textContent = "🔓 Serbest";
    label.classList.replace("text-amber-600", "text-gray-400");
    if (rmBtn) rmBtn.classList.remove("opacity-30", "pointer-events-none");
  }
}

// ── Sketchfab Mode Toggle ─────────────────────────────────────
function toggleSfMode() {
  _sfEnabled = !_sfEnabled;

  const btn   = document.getElementById("sf-toggle-btn");
  const knob  = document.getElementById("sf-toggle-knob");
  const wrap  = document.getElementById("sf-toggle-wrap");
  const label = document.getElementById("sf-toggle-label");
  const sub   = document.getElementById("sf-toggle-sub");

  if (_sfEnabled) {
    btn.classList.replace("bg-gray-300", "bg-blue-500");
    btn.setAttribute("aria-pressed", "true");
    knob.classList.replace("translate-x-0", "translate-x-5");
    wrap.classList.replace("border-gray-200", "border-blue-300");
    wrap.classList.replace("bg-gray-50", "bg-blue-50");
    label.textContent = "Sketchfab Açık";
    label.classList.replace("text-gray-500", "text-blue-700");
    sub.textContent   = "Eksik modeller Sketchfab'dan aranır";
    sub.classList.replace("text-gray-400", "text-blue-500");
  } else {
    btn.classList.replace("bg-blue-500", "bg-gray-300");
    btn.setAttribute("aria-pressed", "false");
    knob.classList.replace("translate-x-5", "translate-x-0");
    wrap.classList.replace("border-blue-300", "border-gray-200");
    wrap.classList.replace("bg-blue-50", "bg-gray-50");
    label.textContent = "Sadece Katalog";
    label.classList.replace("text-blue-700", "text-gray-500");
    sub.textContent   = "Sketchfab kapalı";
    sub.classList.replace("text-blue-500", "text-gray-400");
    // SF öneri alanını gizle
    document.getElementById("sf-coach-recommendations")?.classList.add("hidden");
  }
}

// ── Health Check ───────────────────────────────────────────────
async function checkHealth() {
  const dotApi = document.getElementById("dot-api");
  const labelApi = document.getElementById("label-api");
  const dotBlender = document.getElementById("dot-blender");
  const labelBlender = document.getElementById("label-blender");

  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();

    dotApi.className = "status-dot ok";
    const models = data.available_models || [];
    labelApi.textContent = `API ✓  (${models.join(", ") || "key yok"})`;

    dotBlender.className = data.blender_connected ? "status-dot ok" : "status-dot err";
    labelBlender.textContent = data.blender_connected ? "Blender ✓" : "Blender bağlı değil";
  } catch {
    dotApi.className = "status-dot err";
    labelApi.textContent = "API çalışmıyor";
    dotBlender.className = "status-dot unk";
    labelBlender.textContent = "Blender bilinmiyor";
  }
}

// ── DOMContentLoaded ───────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  setInterval(checkHealth, 15000);
  renderSavedSets();
  loadCatalogAssets();
  loadWindowViewsCatalog();
  loadHouseList();
  loadYapbozCatalog();
  renderSavedDrawRooms();

  const sceneCanvas = document.getElementById("scene-canvas");
  sceneCanvas.addEventListener("mousedown",  sceneMouseDown);
  sceneCanvas.addEventListener("mousemove",  sceneMouseMove);
  sceneCanvas.addEventListener("mouseup",    sceneMouseUp);
  sceneCanvas.addEventListener("mouseleave", sceneMouseUp);

  const promptEl = document.getElementById("prompt-input");
  promptEl.addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitDesign();
  });
  promptEl.addEventListener("input", () => {
    if (lastCoachResult) {
      lastCoachResult = null;
      const note = document.getElementById("coach-note");
      if (note && !note.classList.contains("hidden")) {
        note.innerHTML = `<div class="text-amber-700 text-[11px]">⚠ Promptu düzenledin — Coach planı geçersiz oldu. <b>Tasarla</b> artık LLM zincirini kullanacak. Tekrar <b>Prompt Geliştir</b>'e bas, deterministik yola dön.</div>`;
      }
    }
  });
});
