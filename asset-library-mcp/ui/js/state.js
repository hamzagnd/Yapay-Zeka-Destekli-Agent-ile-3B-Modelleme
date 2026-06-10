// ── state.js ─────────────────────────────────────────────────────
// Global variables and constants shared across all modules.

const API_BASE = "http://localhost:8080";
let currentLLM = "gemini";

// ── Oda Çiz state ─────────────────────────────────────────────────
const DRAW_W = 600, DRAW_H = 460;
const DRAW_SCALE = 55;   // px per meter
const DRAW_SNAP  = 0.5;  // snap grid in meters
const DRAW_CLOSE = 14;   // px radius to close polygon

let _drawPts    = [];
let _drawHover  = null;
let _drawClosed = false;
let _drawnRoom  = null;  // { points, width, depth, area, height, center_x, center_y }
let _drawInited = false;

// Holds the last successful coach response so submitDesign can take the
// deterministic /design-from-coach path. Cleared whenever the user edits
// the textarea, because then specs no longer match the prompt.
let lastCoachResult = null;

// ── Sketchfab mode toggle ─────────────────────────────────────────
// false (default) = sadece katalog; true = eksik modeller Sketchfab'dan aranır
let _sfEnabled = false;

// ── Yapboz kilit ──────────────────────────────────────────────────
// true = itemlar kilitli: sürükle ✓, sil ✗, Prompt Geliştir specs'e dokunamaz
let _yapbozLocked = false;

// ── Yapboz / Plan canvas state ────────────────────────────────────
const PLAN_SVG_W = 480, PLAN_SVG_H = 384;
const PLAN_COLORS = {
  desk: "#94a3b8", dining_table: "#94a3b8", coffee_table: "#94a3b8",
  side_table: "#cbd5e1", nightstand: "#cbd5e1", console_table: "#94a3b8",
  sofa: "#7c3aed", armchair: "#a855f7", dining_chair: "#c084fc",
  office_chair: "#c084fc", bench: "#a855f7", bar_stool: "#c084fc",
  double_bed: "#ec4899", single_bed: "#ec4899", queen_bed: "#ec4899", king_bed: "#ec4899",
  wardrobe: "#f59e0b", bookshelf: "#f59e0b", tv_stand: "#f59e0b", dresser: "#f59e0b",
  floor_lamp: "#facc15", table_lamp: "#facc15", chandelier: "#facc15",
  rug: "#10b981", plant: "#22c55e",
};

let _planState = null;          // { room, placed (mutated), t (transform) }
let _drag = null;               // { idx, startMouse:[x,y], startWorld:[wx,wy] }
let _selectedIdx = null;        // yapboz edit panel: currently selected item index
let _prevFacingCorrection = 0;  // facing_correction_z value when item was selected

// ── Scene tab state ───────────────────────────────────────────────
let _sceneData = null;
const SCENE_SVG_W = 720, SCENE_SVG_H = 540;
let _sceneMode = 'none';       // 'none' | 'select' | 'delete'
let _selectedGroupIdx = null;
let _sceneGroups = [];
let _sceneLLM = 'gemini';      // 'gemini' | 'claude'  (modify-object panel)
let _genLLM   = 'gemini';      // 'gemini' | 'claude'  (generate-in-area panel)

// ── Scene area selection state ────────────────────────────────────
let _sceneSelMode   = false;
let _sceneSelStart  = null;   // {svgX, svgY}
let _sceneSelection = null;   // {x, y, width, depth} in world meters
let _sceneTransform = null;   // saved from renderSceneCanvas

// ── Window views state ────────────────────────────────────────────
let _windowWallsData   = {};   // { wall_name: { pane_count, glass_names, wall_obj } }
let _selectedWallChips = new Set();

// ── House model state ─────────────────────────────────────────────
let _houseRoomsCache = {};
let _cursorLocation = [0, 0, 0];

// ── Material tab state ────────────────────────────────────────────
let _lastMaterial = null;   // { mode, texture_path? } | { mode:'ai', prompt, llm }
let _matLLM = 'gemini';
let _matFileMode = 'quick';   // 'quick' | 'pbr'
let _matSetsList = [];   // filled by renderSavedSets — avoids HTML quoting issues
let _coachMatMode = 'preset';  // 'preset' | 'file'

// ── Models tab state ──────────────────────────────────────────────
let _allModels   = [];   // [{ id, name, category, subcategory, style, rooms, dims }]
let _modelsLoaded = false;
let _mfCat    = '';      // active category filter
let _mfStyle  = '';      // active style filter
let _mfSearch = '';      // active search string
let _modelSelections = {};  // { id: { id, name, subcategory, qty } }

// ── Sketchfab state ───────────────────────────────────────────────
let _modelSource    = 'local';      // 'local' | 'sketchfab'
let _sfResults      = [];           // current search results
let _sfCategory     = '';           // active sketchfab category filter
let _sfDownloading  = {};           // { uid: {status, job_id} }
let _sfDesignModel  = null;         // { uid, name, thumbnailUrl } — selected for quick import

const _CAT_GRAD = {
  seating:      'from-violet-500 to-purple-600',
  tables:       'from-indigo-500 to-blue-600',
  architecture: 'from-emerald-500 to-teal-600',
  kitchen:      'from-amber-500 to-orange-600',
};
const _CAT_LABEL = {
  seating: 'Oturma', tables: 'Masalar', architecture: 'Mimari', kitchen: 'Mutfak',
};

// ── Visual Builder constants ──────────────────────────────────────
const FURNITURE_TYPES = [
  "sofa", "armchair", "desk", "coffee_table", "dining_table", "dining_chair",
  "bed", "nightstand", "wardrobe", "bookshelf", "floor_lamp", "bar_stool",
  "kitchen_counter", "bathtub", "toilet",
];
const PLACEMENTS = [
  "north_wall", "south_wall", "east_wall", "west_wall", "center",
  "corner_nw", "corner_ne", "corner_sw", "corner_se",
  "in_front_of:desk", "in_front_of:sofa", "in_front_of:counter",
  "beside:sofa:left", "beside:sofa:right",
  "beside:bed:left", "beside:bed:right",
];
const ROTATIONS = [0, 90, 180, 270];

// ── Shared utility functions ──────────────────────────────────────
// (Used by both coach.js/scene.js — must be defined before those files load)

/**
 * Ham asset id/name'i okunabilir başlık haline getirir.
 * "metal_office_desk_4k" → "Metal Office Desk"
 * "sf_af2f07d06f63"      → "Office Chair" (catalog name zaten güzel, sadece _ temizle)
 * "Office chair"          → "Office Chair" (zaten iyi, küçük harf başını düzelt)
 */
function _cleanDisplayName(raw) {
  if (!raw) return '';
  // Eğer zaten boşluklu kelimeler varsa, sadece title-case yap
  if (raw.includes(' ')) {
    return raw.replace(/\b\w/g, c => c.toUpperCase());
  }
  // Yoksa alt çizgileri boşluğa çevir, sayısal k/4k gibi çözünürlük son ekini at, title-case yap
  return raw
    .replace(/_(4k|2k|8k|hd|4K|2K|8K|HD)$/i, '')   // "_4k" ekini at
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .trim();
}

// Translate a mouse event into SVG-local coordinates regardless of CSS scale
function svgPoint(svg, evt) {
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

const round3 = n => Math.round(n * 1000) / 1000;

// ── Models tab — panel states ─────────────────────────────────────
let _rotPanelId  = null;   // currently open rotation correction panel
let _editPanelId = null;   // currently open name/ID edit panel
let _aiFixPanelId = null;  // currently open AI fix panel
let _aiFixLLM = 'gemini';  // LLM for AI fix

// ── Model Üret (generate-model) state ────────────────────────────
let _gmLLM           = 'gemini';
let _gmCursorPos     = [0, 0, 0];        // 3D cursor position read from Blender
let _gmLastObjName   = null;             // last successfully generated object name
let _gmPanelOpen     = true;             // collapsible panel state
let _gmHistory       = [];               // [{ obj_name, prompt, ts }]
