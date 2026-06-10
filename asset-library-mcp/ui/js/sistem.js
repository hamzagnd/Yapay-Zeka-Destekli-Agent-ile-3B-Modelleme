// ── sistem.js ─────────────────────────────────────────────────────
// "Sistem" sekmesi: ajan prompt'larını görüntüle ve düzenle.

const SISTEM_AGENTS = [
  {
    key:   "coach",
    name:  "Prompt Coach",
    icon:  "🎓",
    color: "indigo",
    desc:  "Kullanıcının kaba isteğini structured JSON prompt'a çevirir. Katalog doğrulaması yapar, eksik slotları tamamlar, placement keyword'lerini çözer.",
  },
  {
    key:   "space_analyst",
    name:  "Space Analyst",
    icon:  "📐",
    color: "blue",
    desc:  "Oda tipini, boyutlarını ve gerekli mobilya slotlarını belirler. Workflow B'de ev modelini ve oda listesini okur.",
  },
  {
    key:   "furniture_selector",
    name:  "Furniture Selector",
    icon:  "🛋",
    color: "violet",
    desc:  "Her slot için katalogdan en uygun asset'i seçer. Room type uyumunu kontrol eder, companion'ları önerir.",
  },
  {
    key:   "layout_designer",
    name:  "Layout Designer",
    icon:  "📍",
    color: "emerald",
    desc:  "Her mobilya için kesin 3D koordinatları hesaplar. calculate_furniture_layout() aracını çağırır; bbox clamp ve rotation uygular.",
  },
  {
    key:   "blender_executor",
    name:  "Blender Executor",
    icon:  "🎬",
    color: "orange",
    desc:  "Blender sahnesini oluşturur. Workflow A'da oda yaratır, Workflow B'de ev konteyneri import eder; ardından mobilyaları yerleştirir.",
  },
  {
    key:   "team",
    name:  "Team Coordinator",
    icon:  "🏗",
    color: "gray",
    desc:  "Tüm 4 ajanı koordine eder. Workflow A / B kurallarını, doğal dil eşleştirmesini ve özet formatını kontrol eder.",
  },
];

const COLOR_BORDER = {
  indigo: "border-indigo-300", blue: "border-blue-300", violet: "border-violet-300",
  emerald: "border-emerald-300", orange: "border-orange-300", gray: "border-gray-300",
};
const COLOR_BG = {
  indigo: "bg-indigo-50", blue: "bg-blue-50", violet: "bg-violet-50",
  emerald: "bg-emerald-50", orange: "bg-orange-50", gray: "bg-gray-50",
};
const COLOR_TEXT = {
  indigo: "text-indigo-700", blue: "text-blue-700", violet: "text-violet-700",
  emerald: "text-emerald-700", orange: "text-orange-700", gray: "text-gray-700",
};
const COLOR_RING = {
  indigo: "focus:ring-indigo-400", blue: "focus:ring-blue-400", violet: "focus:ring-violet-400",
  emerald: "focus:ring-emerald-400", orange: "focus:ring-orange-400", gray: "focus:ring-gray-400",
};

let _sistemLoaded  = false;
let _sistemPrompts = {};   // { key: text }
let _sistemDirty   = new Set();

// ── Public entry ──────────────────────────────────────────────
async function initSistemTab() {
  renderSistemDiagram();
  renderSistemFlowInfo();
  renderSistemAgents();   // render shells first (with loading state)
  await loadSystemPrompts();
}

// ── Load prompts from backend ─────────────────────────────────
async function loadSystemPrompts() {
  const statusEl = document.getElementById("sistem-save-status");
  if (statusEl) statusEl.textContent = "Yükleniyor...";
  try {
    const res  = await fetch(`${API_BASE}/system/prompts`);
    const data = await res.json();
    _sistemPrompts = data.prompts || {};
    _sistemDirty.clear();
    _sistemLoaded = true;
    // Fill textareas
    for (const ag of SISTEM_AGENTS) {
      const ta = document.getElementById(`sistem-ta-${ag.key}`);
      if (ta) ta.value = _sistemPrompts[ag.key] || "";
      const badge = document.getElementById(`sistem-badge-${ag.key}`);
      if (badge) badge.classList.add("hidden");
    }
    if (statusEl) statusEl.textContent =
      data.source === "custom" ? "✓ Özel promptlar yüklendi" : "✓ Varsayılan promptlar yüklendi";
  } catch (e) {
    if (statusEl) statusEl.textContent = "⚠ Yüklenemedi: " + e.message;
  }
}

// ── Save all ──────────────────────────────────────────────────
async function saveAllSystemPrompts() {
  const statusEl = document.getElementById("sistem-save-status");
  const btn      = document.querySelector('button[onclick="saveAllSystemPrompts()"]');
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.textContent = "Kaydediliyor...";

  const prompts = {};
  for (const ag of SISTEM_AGENTS) {
    const ta = document.getElementById(`sistem-ta-${ag.key}`);
    if (ta) prompts[ag.key] = ta.value;
  }

  try {
    const res  = await fetch(`${API_BASE}/system/prompts`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ prompts }),
    });
    const data = await res.json();
    if (data.ok) {
      _sistemDirty.clear();
      for (const ag of SISTEM_AGENTS) {
        const badge = document.getElementById(`sistem-badge-${ag.key}`);
        if (badge) badge.classList.add("hidden");
      }
      if (statusEl) statusEl.textContent = "✓ Kaydedildi — sonraki çalıştırmada aktif";
    } else {
      if (statusEl) statusEl.textContent = "⚠ Hata: " + (data.error || "bilinmiyor");
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = "⚠ Kayıt hatası: " + e.message;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Reset single agent ────────────────────────────────────────
async function resetAgentPrompt(key) {
  if (!confirm(`"${key}" promptunu varsayılana sıfırlamak istediğinden emin misin?`)) return;
  const statusEl = document.getElementById("sistem-save-status");
  if (statusEl) statusEl.textContent = "Sıfırlanıyor...";
  try {
    const res  = await fetch(`${API_BASE}/system/prompts/${key}`, { method: "DELETE" });
    const data = await res.json();
    if (data.ok) {
      _sistemDirty.delete(key);
      // Reload to get new default
      await loadSystemPrompts();
    } else {
      if (statusEl) statusEl.textContent = "⚠ " + (data.error || "bilinmiyor");
    }
  } catch (e) {
    if (statusEl) statusEl.textContent = "⚠ " + e.message;
  }
}

// ── Dirty tracking ────────────────────────────────────────────
function sistemMarkDirty(key) {
  _sistemDirty.add(key);
  const badge = document.getElementById(`sistem-badge-${key}`);
  if (badge) badge.classList.remove("hidden");
  const statusEl = document.getElementById("sistem-save-status");
  if (statusEl) statusEl.textContent = "Kaydedilmemiş değişiklikler var.";
}

// ── Scroll to agent editor ────────────────────────────────────
function scrollToAgent(key) {
  const el = document.getElementById(`agent-editor-${key}`);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Render: pipeline diagram ──────────────────────────────────
function renderSistemDiagram() {
  const el = document.getElementById("sistem-flow-diagram");
  if (!el) return;

  const nodes = SISTEM_AGENTS.filter(a => a.key !== "team");
  const arrows = nodes.slice(0, -1).map(() =>
    `<div class="text-gray-300 text-xl px-1 flex-shrink-0 self-center">→</div>`
  );

  let html = `<div class="flex items-stretch gap-0 overflow-x-auto pb-2 -mx-1">`;
  nodes.forEach((ag, i) => {
    const border = COLOR_BORDER[ag.color] || "border-gray-300";
    const bg     = COLOR_BG[ag.color]     || "bg-gray-50";
    const text   = COLOR_TEXT[ag.color]   || "text-gray-700";
    html += `
      <div onclick="scrollToAgent('${ag.key}')"
        class="cursor-pointer flex-shrink-0 border-2 ${border} ${bg} rounded-xl px-4 py-3 text-center min-w-[110px] hover:shadow-md transition-shadow">
        <div class="text-2xl mb-1">${ag.icon}</div>
        <div class="text-[11px] font-bold ${text}">${ag.name}</div>
      </div>`;
    if (i < nodes.length - 1) html += `<div class="text-gray-300 text-xl px-1 flex-shrink-0 self-center">→</div>`;
  });
  html += `</div>`;

  // Team coordinator note
  const teamAg = SISTEM_AGENTS.find(a => a.key === "team");
  html += `
    <div onclick="scrollToAgent('team')"
      class="cursor-pointer mt-3 flex items-center gap-3 border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 hover:shadow-sm transition-shadow">
      <span class="text-xl">${teamAg.icon}</span>
      <div>
        <span class="text-xs font-bold text-gray-700">${teamAg.name}</span>
        <span class="text-[11px] text-gray-500 ml-2">— Yukarıdaki 4 ajanı koordine eder, Workflow A/B kurallarını belirler</span>
      </div>
    </div>`;

  el.innerHTML = html;
}

// ── Render: flow info box ─────────────────────────────────────
function renderSistemFlowInfo() {
  const el = document.getElementById("sistem-flow-info");
  if (!el) return;
  el.innerHTML = `
    <h3 class="text-sm font-bold text-indigo-800 mb-3">🔀 Tasarla — Hangi Yol Ne Zaman Çalışır?</h3>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
      <div class="bg-white rounded-xl border border-indigo-200 p-3">
        <div class="font-bold text-indigo-700 mb-1">🎯 Coach Yolu <span class="font-normal text-gray-500">(varsayılan)</span></div>
        <p class="text-gray-600 leading-relaxed">Prompt Geliştir → Tasarla akışı. Coach structured plan üretir, deterministik executor çalışır. En güvenilir sonuç.</p>
        <div class="mt-2 text-[10px] text-indigo-500 font-mono">POST /design-from-coach</div>
      </div>
      <div class="bg-white rounded-xl border border-blue-200 p-3">
        <div class="font-bold text-blue-700 mb-1">⚡ Direkt LLM Yolu</div>
        <p class="text-gray-600 leading-relaxed">Coach atlanmış, direkt Tasarla basıldı. Team tüm 4 ajanı sırayla çalıştırır. Daha yavaş, daha az öngörülü.</p>
        <div class="mt-2 text-[10px] text-blue-500 font-mono">POST /design → Team</div>
      </div>
      <div class="bg-white rounded-xl border border-emerald-200 p-3">
        <div class="font-bold text-emerald-700 mb-1">🏠 Workflow B — Ev İçi</div>
        <p class="text-gray-600 leading-relaxed">"ev", "house", "iki katlı" keyword'leri → Space Analyst ev modelini bulur, oda bbox'u okur, mobilyaları içine clamp'ler.</p>
        <div class="mt-2 text-[10px] text-emerald-500 font-mono">list_house_assets() → origin_offset</div>
      </div>
    </div>`;
}

// ── Render: agent editor cards ────────────────────────────────
function renderSistemAgents() {
  const container = document.getElementById("sistem-agents-list");
  if (!container) return;

  container.innerHTML = SISTEM_AGENTS.map(ag => {
    const border = COLOR_BORDER[ag.color] || "border-gray-200";
    const ring   = COLOR_RING[ag.color]   || "focus:ring-gray-400";
    const text   = COLOR_TEXT[ag.color]   || "text-gray-700";
    return `
      <div id="agent-editor-${ag.key}" class="bg-white rounded-2xl shadow-sm border ${border} p-5">
        <div class="flex items-start justify-between mb-2">
          <div class="flex items-center gap-3">
            <span class="text-2xl">${ag.icon}</span>
            <div>
              <h3 class="text-sm font-bold text-gray-800">${ag.name}</h3>
              <p class="text-[11px] text-gray-500 mt-0.5 max-w-lg">${ag.desc}</p>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0 ml-4">
            <span id="sistem-badge-${ag.key}"
              class="hidden text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
              * Değiştirildi
            </span>
            <button onclick="resetAgentPrompt('${ag.key}')"
              class="text-xs text-gray-400 hover:text-red-600 border border-gray-200 hover:border-red-300 px-3 py-1 rounded-lg transition-colors whitespace-nowrap">
              ↺ Varsayılana Sıfırla
            </button>
          </div>
        </div>
        <textarea
          id="sistem-ta-${ag.key}"
          class="w-full border border-gray-200 rounded-xl p-3 text-xs font-mono focus:outline-none focus:ring-2 ${ring} resize-y leading-relaxed bg-gray-50"
          rows="16"
          oninput="sistemMarkDirty('${ag.key}')"
          placeholder="Yükleniyor..."
          spellcheck="false"
        ></textarea>
      </div>`;
  }).join("");
}
