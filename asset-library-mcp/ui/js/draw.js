// ── draw.js ───────────────────────────────────────────────────────
// Draw canvas: initDrawCanvas, clearDrawCanvas, useDrawnRoom,
// saveDrawnRoom, renderSavedDrawRooms, useSavedRoom,
// _getRoomWallNames (helper used by draw and coach materials).

const _DRAW_ROOMS_KEY = 'asset_lib_saved_rooms';
let _drawSceneFn = null;  // exposed so useSavedRoom can trigger a redraw

async function _getRoomWallNames() {
  const fromScene = src => (src?.objects||[]).filter(o=>o.name.startsWith('Room_Wall')).map(o=>o.name);
  if (_sceneData){const n=fromScene(_sceneData);if(n.length)return n;}
  try {
    const res=await fetch(`${API_BASE}/blender/scene/analyze`,{signal:AbortSignal.timeout(8000)});
    const data=await res.json();
    const n=fromScene(data);if(n.length)return n;
  } catch{}
  return ['Room_Wall_North','Room_Wall_South','Room_Wall_East','Room_Wall_West'];
}

function initDrawCanvas() {
  if (_drawInited) {
    if (_drawSceneFn) _drawSceneFn();  // just redraw with current _drawPts
    return;
  }
  _drawInited = true;

  const canvas = document.getElementById("draw-canvas");
  const ctx = canvas.getContext("2d");

  function snap(v) { return Math.round(v / DRAW_SNAP) * DRAW_SNAP; }
  function canvasToWorld(ex, ey) {
    const r = canvas.getBoundingClientRect();
    return [snap((ex - r.left - DRAW_W/2) / DRAW_SCALE), snap((DRAW_H/2 - (ey - r.top)) / DRAW_SCALE)];
  }
  function worldToCanvas(wx, wy) { return [DRAW_W/2 + wx*DRAW_SCALE, DRAW_H/2 - wy*DRAW_SCALE]; }
  function dist(ax,ay,bx,by) { return Math.sqrt((ax-bx)**2+(ay-by)**2); }
  function shoelaceArea(pts) {
    let s=0; for(let i=0;i<pts.length;i++){const[ax,ay]=pts[i],[bx,by]=pts[(i+1)%pts.length];s+=ax*by-bx*ay;} return Math.abs(s)/2;
  }

  function drawScene() {
    ctx.clearRect(0,0,DRAW_W,DRAW_H);

    const gs = DRAW_SNAP * DRAW_SCALE;
    ctx.strokeStyle="#e2e8f0"; ctx.lineWidth=0.5;
    for(let x=(DRAW_W/2)%gs;x<DRAW_W;x+=gs){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,DRAW_H);ctx.stroke();}
    for(let y=(DRAW_H/2)%gs;y<DRAW_H;y+=gs){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(DRAW_W,y);ctx.stroke();}

    const g1 = DRAW_SCALE;
    ctx.strokeStyle="#d1d5db"; ctx.lineWidth=0.8;
    for(let x=(DRAW_W/2)%g1;x<DRAW_W;x+=g1){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,DRAW_H);ctx.stroke();}
    for(let y=(DRAW_H/2)%g1;y<DRAW_H;y+=g1){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(DRAW_W,y);ctx.stroke();}

    ctx.strokeStyle="#94a3b8"; ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(DRAW_W/2,0);ctx.lineTo(DRAW_W/2,DRAW_H);ctx.stroke();
    ctx.beginPath();ctx.moveTo(0,DRAW_H/2);ctx.lineTo(DRAW_W,DRAW_H/2);ctx.stroke();

    ctx.fillStyle="#94a3b8"; ctx.font="9px monospace"; ctx.textAlign="center";
    const xRange = Math.floor(DRAW_W/2/g1);
    for(let m=-xRange;m<=xRange;m++){
      if(m===0) continue;
      const px=DRAW_W/2+m*g1, py=DRAW_H/2;
      ctx.fillText(m+"m", px, py+10);
    }
    ctx.textAlign="right";
    const yRange = Math.floor(DRAW_H/2/g1);
    for(let m=-yRange;m<=yRange;m++){
      if(m===0) continue;
      const px=DRAW_W/2-3, py=DRAW_H/2-m*g1;
      ctx.fillText(m+"m", px, py+3);
    }

    ctx.strokeStyle="#64748b"; ctx.fillStyle="#64748b"; ctx.lineWidth=1.5;
    ctx.textAlign="center"; ctx.font="9px sans-serif";
    const sbX=12, sbY=DRAW_H-12, sbW=g1;
    ctx.beginPath();ctx.moveTo(sbX,sbY-4);ctx.lineTo(sbX,sbY+4);ctx.stroke();
    ctx.beginPath();ctx.moveTo(sbX,sbY);ctx.lineTo(sbX+sbW,sbY);ctx.stroke();
    ctx.beginPath();ctx.moveTo(sbX+sbW,sbY-4);ctx.lineTo(sbX+sbW,sbY+4);ctx.stroke();
    ctx.fillText("1m",sbX+sbW/2,sbY-6);

    if(_drawHover && !_drawClosed){
      const[hx,hy]=worldToCanvas(_drawHover[0],_drawHover[1]);
      ctx.fillStyle="rgba(30,41,59,0.75)";
      const txt=`(${_drawHover[0].toFixed(1)}, ${_drawHover[1].toFixed(1)})`;
      ctx.font="10px monospace"; ctx.textAlign="left";
      const tw=ctx.measureText(txt).width;
      const tx=Math.min(hx+12,DRAW_W-tw-6), ty=Math.max(hy-10,16);
      ctx.fillRect(tx-3,ty-11,tw+6,14);
      ctx.fillStyle="#f8fafc"; ctx.fillText(txt,tx,ty);
    }

    if(_drawPts.length===0) return;

    if(_drawClosed && _drawPts.length>=3){
      ctx.beginPath();
      const[sx0,sy0]=worldToCanvas(_drawPts[0][0],_drawPts[0][1]);ctx.moveTo(sx0,sy0);
      for(let i=1;i<_drawPts.length;i++){const[cx,cy]=worldToCanvas(_drawPts[i][0],_drawPts[i][1]);ctx.lineTo(cx,cy);}
      ctx.closePath(); ctx.fillStyle="rgba(99,102,241,0.10)"; ctx.fill();
    }

    ctx.setLineDash(_drawClosed?[]:[6,3]);
    ctx.strokeStyle=_drawClosed?"#334155":"#6366f1"; ctx.lineWidth=2;
    const drawEdge=(p1,p2,lbl)=>{
      const[ax,ay]=worldToCanvas(p1[0],p1[1]),[bx,by]=worldToCanvas(p2[0],p2[1]);
      ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);ctx.stroke();
      if(lbl){
        const mx=(ax+bx)/2,my=(ay+by)/2,angle=Math.atan2(by-ay,bx-ax);
        ctx.save();ctx.translate(mx,my);ctx.rotate(angle);
        ctx.font="bold 11px monospace"; const tw=ctx.measureText(lbl).width;
        ctx.fillStyle="rgba(255,255,255,0.85)"; ctx.fillRect(-tw/2-3,-14,tw+6,14);
        ctx.fillStyle="#1e293b"; ctx.textAlign="center"; ctx.fillText(lbl,0,-3);
        ctx.restore();
      }
    };
    for(let i=0;i<_drawPts.length-1;i++){
      const len=dist(_drawPts[i][0],_drawPts[i][1],_drawPts[i+1][0],_drawPts[i+1][1]);
      drawEdge(_drawPts[i],_drawPts[i+1],len.toFixed(1)+"m");
    }
    if(_drawClosed && _drawPts.length>=2){
      const last=_drawPts[_drawPts.length-1],first=_drawPts[0];
      drawEdge(last,first,dist(last[0],last[1],first[0],first[1]).toFixed(1)+"m");
    } else if(_drawHover && _drawPts.length>=1){
      ctx.setLineDash([4,4]); drawEdge(_drawPts[_drawPts.length-1],_drawHover,null); ctx.setLineDash([]);
    }
    ctx.setLineDash([]);

    if(_drawHover && !_drawClosed && _drawPts.length>=3){
      const[hx,hy]=worldToCanvas(_drawHover[0],_drawHover[1]);
      const[fx,fy]=worldToCanvas(_drawPts[0][0],_drawPts[0][1]);
      if(dist(hx,hy,fx,fy)<DRAW_CLOSE){
        ctx.strokeStyle="#dc2626"; ctx.lineWidth=2;
        ctx.beginPath();ctx.arc(fx,fy,DRAW_CLOSE,0,Math.PI*2);ctx.stroke();
        ctx.fillStyle="rgba(220,38,38,0.15)"; ctx.beginPath();ctx.arc(fx,fy,DRAW_CLOSE,0,Math.PI*2);ctx.fill();
      }
    }

    if(_drawHover && !_drawClosed){
      const[hx,hy]=worldToCanvas(_drawHover[0],_drawHover[1]);
      ctx.fillStyle="rgba(99,102,241,0.7)"; ctx.beginPath();ctx.arc(hx,hy,4,0,Math.PI*2);ctx.fill();
    }

    for(let i=0;i<_drawPts.length;i++){
      const[cx,cy]=worldToCanvas(_drawPts[i][0],_drawPts[i][1]);
      ctx.fillStyle="#fff"; ctx.beginPath();ctx.arc(cx,cy,i===0?8:6,0,Math.PI*2);ctx.fill();
      ctx.fillStyle=i===0?"#dc2626":"#6366f1"; ctx.beginPath();ctx.arc(cx,cy,i===0?6:4,0,Math.PI*2);ctx.fill();
      if(i===0){ctx.fillStyle="#fff";ctx.font="bold 8px sans-serif";ctx.textAlign="center";ctx.fillText("1",cx,cy+3);}
    }
  }

  function updateStats() {
    if(_drawPts.length<2){
      document.getElementById("draw-stat-dims").textContent="—";
      document.getElementById("draw-stat-area").textContent="—";
      document.getElementById("draw-stat-perim").textContent="—"; return;
    }
    const xs=_drawPts.map(p=>p[0]),ys=_drawPts.map(p=>p[1]);
    const w=(Math.max(...xs)-Math.min(...xs)).toFixed(1);
    const d=(Math.max(...ys)-Math.min(...ys)).toFixed(1);
    let perim=0;
    for(let i=0;i<_drawPts.length;i++) perim+=dist(_drawPts[i][0],_drawPts[i][1],_drawPts[(i+1)%_drawPts.length][0],_drawPts[(i+1)%_drawPts.length][1]);
    const area=_drawClosed?shoelaceArea(_drawPts).toFixed(1):"—";
    document.getElementById("draw-stat-dims").textContent=`${w}×${d}m`;
    document.getElementById("draw-stat-area").textContent=`Alan: ${area}m²`;
    document.getElementById("draw-stat-perim").textContent=`Çevre: ${perim.toFixed(1)}m`;
  }

  function undoLastPoint() {
    if(_drawClosed || _drawPts.length===0) return;
    _drawPts.pop(); updateStats(); drawScene();
  }

  canvas.addEventListener("pointermove", e => {
    if(_drawClosed) return;
    _drawHover=canvasToWorld(e.clientX,e.clientY); drawScene();
  });
  canvas.addEventListener("pointerleave", () => { _drawHover=null; drawScene(); });
  canvas.addEventListener("contextmenu", e => { e.preventDefault(); undoLastPoint(); });
  canvas.addEventListener("click", e => {
    if(_drawClosed) return;
    const pt=canvasToWorld(e.clientX,e.clientY);
    if(_drawPts.length>=3){
      const[fx,fy]=worldToCanvas(_drawPts[0][0],_drawPts[0][1]);
      const[cx,cy]=worldToCanvas(pt[0],pt[1]);
      if(dist(cx,cy,fx,fy)<DRAW_CLOSE){
        _drawClosed=true; _drawHover=null;
        updateStats(); drawScene(); return;
      }
    }
    _drawPts.push(pt); updateStats(); drawScene();
  });

  const keyHandler = e => {
    if(document.getElementById("tab-ciz").classList.contains("hidden")) return;
    if(e.key==="Backspace"||e.key==="Delete") { e.preventDefault(); undoLastPoint(); }
  };
  document.addEventListener("keydown", keyHandler);
  canvas._keyHandler = keyHandler;

  _drawSceneFn = drawScene;  // expose for external redraw triggers
  drawScene();
}

function clearDrawCanvas() {
  const canvas = document.getElementById("draw-canvas");
  if(canvas._keyHandler){ document.removeEventListener("keydown",canvas._keyHandler); canvas._keyHandler=null; }
  _drawPts=[]; _drawHover=null; _drawClosed=false; _drawnRoom=null; _drawInited=false;
  document.getElementById("draw-used-note").classList.add("hidden");
  initDrawCanvas();
}

function useDrawnRoom() {
  if (!_drawClosed || _drawPts.length < 3) {
    const btn = document.getElementById('btn-use-drawn-room');
    const orig = btn.textContent;
    btn.textContent = '⚠ Önce oda çiz ve kapat';
    setTimeout(() => { btn.textContent = orig; }, 2000);
    return;
  }
  const xs=_drawPts.map(p=>p[0]), ys=_drawPts.map(p=>p[1]);
  const center_x=(Math.max(...xs)+Math.min(...xs))/2;
  const center_y=(Math.max(...ys)+Math.min(...ys))/2;
  const width=parseFloat((Math.max(...xs)-Math.min(...xs)).toFixed(2));
  const depth=parseFloat((Math.max(...ys)-Math.min(...ys)).toFixed(2));
  const height=parseFloat(document.getElementById("draw-height").value)||2.7;
  function shoelace(pts){let s=0;for(let i=0;i<pts.length;i++){const[ax,ay]=pts[i],[bx,by]=pts[(i+1)%pts.length];s+=ax*by-bx*ay;}return Math.abs(s)/2;}
  const area=shoelace(_drawPts);
  _drawnRoom={points:_drawPts.map(p=>[...p]),width,depth,area,height,center_x,center_y};

  const n=_drawPts.length, isRect=n===4;
  function edgeLen(a,b){return Math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2);}
  const cornerList=_drawPts.map(([x,y])=>`(${x.toFixed(1)},${y.toFixed(1)})`).join(', ');
  const wallLengths=_drawPts.map((p,i)=>edgeLen(p,_drawPts[(i+1)%n]).toFixed(1));
  let roomText=`[ÖZEL_ODA] ${width}x${depth}m ${isRect?'dikdörtgen':`${n}-köşeli polygon`} oda`;
  if (!isRect){roomText+=` Köşe koordinatları: ${cornerList}.`;roomText+=` Duvar uzunlukları: ${wallLengths.join('m, ')}m.`;}
  roomText+=` Alan: ${area.toFixed(1)}m². Bu odanın polygon şeklini Blender'da oluştur, mobilyaları sınırlayıcı kutu içine yerleştir.`;

  const input=document.getElementById("prompt-input");
  const cleaned=input.value.trim().replace(/\[ÖZEL_ODA\][^\n]*/g,'').trim();
  input.value=(cleaned?cleaned+'\n':'')+roomText;
  document.getElementById("draw-used-note").classList.remove("hidden");
  switchTab("tasarim");
}

// ── Kayıtlı Odalar ──────────────────────────────────────────────

function _makeMiniSvg(points, W=68, H=52) {
  if (!points || points.length < 2) return '';
  const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const rangeX = maxX - minX || 1, rangeY = maxY - minY || 1;
  const pad = 7;
  const sc = Math.min((W - pad*2) / rangeX, (H - pad*2) / rangeY);
  const sx = p => (pad + (p[0] - minX) * sc).toFixed(1);
  const sy = p => (H - pad - (p[1] - minY) * sc).toFixed(1);
  const pts = points.map(p => `${sx(p)},${sy(p)}`).join(' ');
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">
    <rect width="${W}" height="${H}" fill="#f8fafc" rx="4"/>
    <polygon points="${pts}" fill="rgba(99,102,241,0.13)" stroke="#6366f1" stroke-width="2" stroke-linejoin="round"/>
    ${points.map(p => `<circle cx="${sx(p)}" cy="${sy(p)}" r="2.5" fill="#6366f1"/>`).join('')}
  </svg>`;
}

function _loadSavedDrawRooms() {
  try { return JSON.parse(localStorage.getItem(_DRAW_ROOMS_KEY) || '[]'); } catch { return []; }
}

function saveDrawnRoom() {
  const hintEl = document.getElementById('draw-save-hint');
  if (!_drawClosed || _drawPts.length < 3) {
    const btn = document.getElementById('btn-save-drawn-room');
    const orig = btn.textContent;
    btn.textContent = '⚠ Önce oda çiz ve kapat';
    btn.classList.replace('bg-emerald-600', 'bg-amber-500');
    if (hintEl) { hintEl.textContent = 'İpucu: en az 3 nokta koy, ilk noktaya (kırmızı) tıklayarak kapat.'; hintEl.className = 'text-[10px] text-amber-600 mt-1.5'; }
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.replace('bg-amber-500', 'bg-emerald-600');
      if (hintEl) { hintEl.textContent = 'Sol tarafta oda çiz ve ilk noktaya tıklayarak kapat, ardından kaydet.'; hintEl.className = 'text-[10px] text-gray-400 mt-1.5'; }
    }, 2500);
    return;
  }
  const nameEl = document.getElementById('draw-room-name');
  const name = (nameEl?.value.trim()) || `Oda ${new Date().toLocaleTimeString('tr-TR', {hour:'2-digit',minute:'2-digit'})}`;
  const xs = _drawPts.map(p => p[0]), ys = _drawPts.map(p => p[1]);
  const center_x = (Math.max(...xs) + Math.min(...xs)) / 2;
  const center_y = (Math.max(...ys) + Math.min(...ys)) / 2;
  const width = parseFloat((Math.max(...xs) - Math.min(...xs)).toFixed(2));
  const depth = parseFloat((Math.max(...ys) - Math.min(...ys)).toFixed(2));
  const height = parseFloat(document.getElementById('draw-height').value) || 2.7;
  function shoelace(pts){let s=0;for(let i=0;i<pts.length;i++){const[ax,ay]=pts[i],[bx,by]=pts[(i+1)%pts.length];s+=ax*by-bx*ay;}return Math.abs(s)/2;}
  const area = parseFloat(shoelace(_drawPts).toFixed(1));

  const room = {
    id: Date.now(),
    name,
    points: _drawPts.map(p => [...p]),
    width, depth, height, area, center_x, center_y,
    mini_svg: _makeMiniSvg(_drawPts),
    saved_at: new Date().toLocaleDateString('tr-TR'),
  };

  const rooms = _loadSavedDrawRooms();
  rooms.unshift(room);
  localStorage.setItem(_DRAW_ROOMS_KEY, JSON.stringify(rooms));
  if (nameEl) nameEl.value = '';
  renderSavedDrawRooms();

  // Kısa "kaydedildi" bildirimi
  const btn = document.getElementById('btn-save-drawn-room');
  const orig = btn.textContent;
  btn.textContent = '✓ Kaydedildi';
  setTimeout(() => { btn.textContent = orig; }, 1500);
}

function deleteSavedRoom(id) {
  const rooms = _loadSavedDrawRooms().filter(r => r.id !== id);
  localStorage.setItem(_DRAW_ROOMS_KEY, JSON.stringify(rooms));
  renderSavedDrawRooms();
}

function useSavedRoom(id) {
  const room = _loadSavedDrawRooms().find(r => r.id === id);
  if (!room) return;

  // Mevcut çizim state'ini temizle ve yüklenen odayı aktar
  _drawPts   = room.points.map(p => [...p]);
  _drawClosed = true;
  _drawHover  = null;
  _drawnRoom  = {
    points: room.points.map(p => [...p]),
    width: room.width, depth: room.depth,
    height: room.height, area: room.area,
    center_x: room.center_x, center_y: room.center_y,
  };
  document.getElementById('draw-height').value = room.height;

  const noteEl = document.getElementById('draw-used-note');
  noteEl.textContent = `✓ "${room.name}" yüklendi — "Bu Oda ile Tasarla"ya basabilirsin`;
  noteEl.classList.remove('hidden');

  // Tuval yeniden çiz (initDrawCanvas zaten başlatıldıysa sadece drawScene çağırır)
  switchTab('ciz');
  initDrawCanvas();

  // updateStats çağrısı (drawScene içinde değil, dışarıdan da erişilebilir olmalı)
  // Boyutlar bilgisini manuel güncelle
  document.getElementById('draw-stat-dims').textContent = `${room.width}×${room.depth}m`;
  document.getElementById('draw-stat-area').textContent = `Alan: ${room.area}m²`;
}

function renderSavedDrawRooms() {
  const list  = document.getElementById('saved-draw-rooms-list');
  const empty = document.getElementById('saved-draw-rooms-empty');
  if (!list) return;
  const rooms = _loadSavedDrawRooms();
  if (!rooms.length) {
    list.innerHTML = '';
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');
  list.innerHTML = rooms.map(r => `
    <div class="bg-gray-50 border border-gray-200 rounded-xl p-2.5 flex gap-2.5 items-center hover:shadow-sm hover:border-indigo-200 transition-all group">
      <!-- Mini SVG önizleme -->
      <div class="flex-shrink-0 rounded-lg overflow-hidden border border-gray-100 bg-white">
        ${r.mini_svg || `<div class="w-[68px] h-[52px] flex items-center justify-center text-gray-300 text-[10px]">—</div>`}
      </div>
      <!-- Bilgi + butonlar -->
      <div class="flex-1 min-w-0 flex flex-col gap-1">
        <div class="flex items-center justify-between gap-1">
          <span class="text-xs font-semibold text-gray-800 truncate" title="${r.name}">${r.name}</span>
          <button onclick="deleteSavedRoom(${r.id})" title="Sil"
            class="flex-shrink-0 text-gray-300 hover:text-red-400 transition-colors text-sm leading-none">✕</button>
        </div>
        <div class="text-[10px] text-gray-500 font-mono">${r.width}×${r.depth}m · ${r.height}m tavan</div>
        <div class="text-[10px] text-gray-400">${r.area}m² · ${r.saved_at || ''}</div>
        <button onclick="useSavedRoom(${r.id})"
          class="mt-0.5 w-full py-1 text-[11px] font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors">
          ➕ Yükle &amp; Kullan
        </button>
      </div>
    </div>
  `).join('');
}
