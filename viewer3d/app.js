import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/* ------------------------------------------------------------------ *
 *  K3B 机械臂 · STEP 三维图预览
 *  STEP 解析：occt-import-js (OpenCascade WASM)
 *  渲染：three.js
 * ------------------------------------------------------------------ */

const $ = (id) => document.getElementById(id);

const dom = {
  stage: $('stage'),
  cv: $('cv'),
  list: $('list'),
  search: $('search'),
  srcPath: $('srcPath'),
  selInfo: $('selInfo'),
  clearSel: $('clearSel'),
  hud: $('hud'),
  overlay: $('overlay'),
  ovText: $('ovText'),
  toast: $('toast'),
  views: $('views'),
  chips: $('chips'),
};

const state = {
  items: [],
  selected: new Set(),
  opts: { edges: true, wire: false, bbox: false, grid: true, axes: true, spin: false },
  models: [],       // [{ path, group, edges, meshes: [...], box, stats }]
  cache: new Map(), // path -> { group, edges, meshes, stats }
  viewDir: new THREE.Vector3(1, -1.06, 0.72).normalize(),
  box: null,
};

const EDGE_TRI_LIMIT = 420000;   // 超过这个三角面数就不生成边线（太慢）
const CACHE_LIMIT = 6;

/* ------------------------------------------------------------------ *
 *  three.js 基础场景
 * ------------------------------------------------------------------ */

const renderer = new THREE.WebGLRenderer({ canvas: dom.cv, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.92;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0e1014);

const camera = new THREE.PerspectiveCamera(38, 1, 0.5, 1e7);
camera.up.set(0, 0, 1);   // CAD 惯例：Z 轴朝上
camera.position.set(500, -500, 380);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.autoRotateSpeed = 1.6;
controls.screenSpacePanning = true;
controls.minDistance = 1e-2;
controls.maxDistance = 1e6;

/* 灯光：主光 + 补光 + 轮廓光，控制在不会把浅色件打白 */
scene.add(new THREE.AmbientLight(0xffffff, 0.45));
const hemi = new THREE.HemisphereLight(0xd6e4ff, 0x11151a, 0.5);
scene.add(hemi);

const keyLight = new THREE.DirectionalLight(0xffffff, 1.55);
const fillLight = new THREE.DirectionalLight(0xb8cdf0, 0.55);
const rimLight = new THREE.DirectionalLight(0x7fa8f0, 0.5);
scene.add(keyLight, fillLight, rimLight);

const keyLightTarget = new THREE.Object3D();
scene.add(keyLightTarget);
keyLight.target = keyLightTarget;
fillLight.target = keyLightTarget;
rimLight.target = keyLightTarget;

function placeLights(radius) {
  const r = Math.max(radius, 1);
  keyLight.position.set(r * 1.2, -r * 1.6, r * 1.8);
  fillLight.position.set(-r * 1.8, -r * 0.6, r * 0.7);
  rimLight.position.set(r * 0.4, r * 1.9, r * 0.9);
}

/* 场景辅助对象 */
const helpers = new THREE.Group();
scene.add(helpers);

const gridRoot = new THREE.Group();
const axesRoot = new THREE.Group();
helpers.add(gridRoot, axesRoot);
axesRoot.visible = state.opts.axes;

let gridHelper = null;

function rebuildGrid(center, size, divisions) {
  gridRoot.clear();
  if (gridHelper) { gridHelper.geometry.dispose(); gridHelper.material.dispose(); gridHelper = null; }
  if (!size || !isFinite(size) || size <= 0) return;
  const d = Math.max(8, Math.min(200, Math.round(divisions)));
  gridHelper = new THREE.GridHelper(size, d, 0x41505f, 0x252d37);
  gridHelper.rotation.x = Math.PI / 2;     // GridHelper 默认在 XZ 平面，转到 XY
  gridHelper.position.set(center.x, center.y, 0);
  gridRoot.add(gridHelper);
}

function rebuildAxes(size) {
  axesRoot.clear();
  if (!size || !isFinite(size) || size <= 0) return;
  const L = size * 0.5;
  const mk = (from, to, color) => {
    const g = new THREE.BufferGeometry().setFromPoints([from, to]);
    const m = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.85 });
    return new THREE.Line(g, m);
  };
  const O = new THREE.Vector3(0, 0, 0);
  axesRoot.add(mk(O, new THREE.Vector3(L, 0, 0), 0xff6b6b));      // X 红
  axesRoot.add(mk(O, new THREE.Vector3(0, L, 0), 0x59d68a));      // Y 绿
  axesRoot.add(mk(O, new THREE.Vector3(0, 0, L), 0x5aa9ff));      // Z 蓝
}

/* ------------------------------------------------------------------ *
 *  STEP -> three.js
 * ------------------------------------------------------------------ */

let occtPromise = null;
function getOcct() {
  if (occtPromise) return occtPromise;
  occtPromise = new Promise((resolve, reject) => {
    if (typeof window.occtimportjs !== 'function') {
      reject(new Error('occt-import-js 未加载（vendor/occt/occt-import-js.js）'));
      return;
    }
    window.occtimportjs().then(resolve).catch(reject);
  });
  return occtPromise;
}

let occt = null;

function makeMaterial(color) {
  return new THREE.MeshStandardMaterial({
    color,
    metalness: 0.12,
    roughness: 0.62,
    side: THREE.DoubleSide,
    envMapIntensity: 0.5,
  });
}

const edgeMaterial = new THREE.LineBasicMaterial({
  color: 0x080a0d,
  transparent: true,
  opacity: 0.55,
});

/** 把 occt 解析结果转成 three.js 组 */
function buildFromOcct(result, name) {
  const group = new THREE.Group();
  const edgeGroup = new THREE.Group();
  group.name = name;
  edgeGroup.name = name + '_edges';

  let tris = 0;
  let parts = 0;
  let multiColor = false;

  for (const m of result.meshes) {
    const posArr = m.attributes && m.attributes.position ? m.attributes.position.array : null;
    if (!posArr || posArr.length < 9) continue;
    parts++;

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(posArr, 3));

    const nrmArr = m.attributes.normal ? m.attributes.normal.array : null;
    if (nrmArr && nrmArr.length === posArr.length) {
      geo.setAttribute('normal', new THREE.Float32BufferAttribute(nrmArr, 3));
    } else {
      geo.computeVertexNormals();
    }

    const idxArr = m.index && m.index.array ? m.index.array : null;
    if (idxArr) {
      const ia = idxArr instanceof Uint32Array ? idxArr : Uint32Array.from(idxArr);
      geo.setIndex(new THREE.BufferAttribute(ia, 1));
    }

    const triCount = (idxArr ? idxArr.length : posArr.length / 3) / 3;
    tris += triCount;

    /* --- 材质分组：尽量保留 STEP 里的零件配色 --- */
    const baseColor = m.color
      ? new THREE.Color(m.color[0], m.color[1], m.color[2])
      : new THREE.Color(0xa9b5c4);
    const mats = [makeMaterial(baseColor)];
    mats[0].userData.hex = baseColor.getHexString();

    const faces = Array.isArray(m.brep_faces) ? m.brep_faces : [];
    const hasFaceColor = faces.some((f) => Array.isArray(f.color));
    if (hasFaceColor && geo.index) {
      multiColor = true;
      let t = 0;
      let fi = 0;
      let guard = 0;
      while (t < triCount && guard++ < triCount + faces.length + 8) {
        const first = t;
        let last, matIdx;
        if (fi >= faces.length) {
          last = triCount; matIdx = 0;
        } else if (t < faces[fi].first) {
          last = faces[fi].first; matIdx = 0;
        } else {
          const f = faces[fi];
          last = Math.min(f.last + 1, triCount);
          if (Array.isArray(f.color)) {
            const c = new THREE.Color(f.color[0], f.color[1], f.color[2]);
            const hex = c.getHexString();
            let k = mats.findIndex((x) => x.userData.hex === hex);
            if (k < 0) { const mm = makeMaterial(c); mm.userData.hex = hex; mats.push(mm); k = mats.length - 1; }
            matIdx = k;
          } else {
            matIdx = 0;
          }
          fi++;
        }
        if (last <= first) { fi++; t = first + 1; continue; }
        geo.addGroup(first * 3, (last - first) * 3, matIdx);
        t = last;
      }
    }

    const mesh = new THREE.Mesh(geo, mats.length > 1 ? mats : mats[0]);
    mesh.name = m.name || `part_${parts}`;
    group.add(mesh);

    /* --- 边线 --- */
    if (tris <= EDGE_TRI_LIMIT && triCount <= 200000) {
      try {
        const eg = new THREE.EdgesGeometry(geo, 34);
        if (eg.attributes.position && eg.attributes.position.count > 0) {
          edgeGroup.add(new THREE.LineSegments(eg, edgeMaterial));
        } else {
          eg.dispose();
        }
      } catch (_) { /* 个别几何体算边线失败就跳过 */ }
    }
  }

  return { group, edgeGroup, stats: { tris, parts, multiColor } };
}

/** 从 STEP 字节流解析 */
function parseStep(buffer, name) {
  const result = occt.ReadStepFile(new Uint8Array(buffer), {
    linearUnit: 'millimeter',
    linearDeflectionType: 'bounding_box_ratio',
    linearDeflection: 0.0015,
    angularDeflection: 0.28,
  });
  if (!result || result.success === false || !result.meshes || result.meshes.length === 0) {
    throw new Error('没有解析出实体网格（可能是装配体引用丢失或文件损坏）');
  }
  return buildFromOcct(result, name);
}

function disposeGroup(g) {
  g.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) {
      if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
      else o.material.dispose();
    }
  });
}

function cachePut(path, entry) {
  if (state.cache.has(path)) {
    const old = state.cache.get(path);
    if (old !== entry) { disposeGroup(old.group); disposeGroup(old.edgeGroup); }
    state.cache.delete(path);
  }
  state.cache.set(path, entry);
  while (state.cache.size > CACHE_LIMIT) {
    const k = state.cache.keys().next().value;
    const v = state.cache.get(k);
    if (state.selected.has(k)) { state.cache.delete(k); state.cache.set(k, v); continue; }
    disposeGroup(v.group); disposeGroup(v.edgeGroup);
    state.cache.delete(k);
  }
}

/* ------------------------------------------------------------------ *
 *  场景装配 / 布局
 * ------------------------------------------------------------------ */

const root = new THREE.Group();
scene.add(root);

function applyOptions() {
  for (const m of state.models) {
    m.edges.visible = state.opts.edges;
    m.group.traverse((o) => {
      if (o.isMesh) {
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((mt) => { mt.wireframe = state.opts.wire; });
      }
    });
    if (m.bboxHelper) m.bboxHelper.visible = state.opts.bbox;
  }
  gridRoot.visible = state.opts.grid;
  axesRoot.visible = state.opts.axes;
  controls.autoRotate = state.opts.spin;
}

function clearScene() {
  for (const m of state.models) {
    root.remove(m.group);
    root.remove(m.edges);
    if (m.bboxHelper) { root.remove(m.bboxHelper); m.bboxHelper.geometry.dispose(); m.bboxHelper.material.dispose(); }
  }
  state.models = [];
}

/** 把若干模型摆成一排（单个则居中） */
function layoutAndFit() {
  const single = state.models.length === 1;
  let cursor = 0;
  let gap = 0;

  if (!single && state.models.length > 1) {
    const widths = state.models.map((m) => m.box.max.x - m.box.min.x);
    const avg = widths.reduce((a, b) => a + b, 0) / widths.length;
    gap = Math.max(avg * 0.22, 1);
  }

  for (const m of state.models) {
    const b = m.box;
    const w = b.max.x - b.min.x;
    const cy = (b.min.y + b.max.y) / 2;
    let tx, ty;
    if (single) {
      tx = -((b.min.x + b.max.x) / 2);
      ty = -cy;
    } else {
      tx = cursor - b.min.x;
      ty = -cy;
    }
    const tz = -b.min.z;
    m.group.position.set(tx, ty, tz);
    m.edges.position.set(tx, ty, tz);
    if (m.bboxHelper) m.bboxHelper.position.set(tx, ty, tz);
    if (!single) cursor = b.max.x + tx + gap;
  }

  // 整体包围盒
  const total = new THREE.Box3();
  for (const m of state.models) {
    const b = m.box.clone();
    b.min.add(m.group.position);
    b.max.add(m.group.position);
    total.union(b);
  }
  if (total.isEmpty()) { state.box = null; return; }

  state.box = total;
  const size = total.getSize(new THREE.Vector3());
  const center = total.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 0.001);

  placeLights(radius);
  keyLightTarget.position.copy(center);

  const gridSize = Math.max(size.x, size.y) * 1.55;
  rebuildGrid(center, gridSize, Math.round(gridSize / Math.max(radius / 6, 0.1)));
  rebuildAxes(radius * 0.9);

  applyOptions();
  setView(state.viewDir, true);
}

/** 按包围盒 8 个角点精确计算取景距离（比包围球贴合得多） */
function fitDistance(box, dir) {
  const center = box.getCenter(new THREE.Vector3());
  const forward = dir.clone().normalize().negate();               // 相机朝向
  const upRef = Math.abs(dir.z) > 0.985 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1);
  const right = new THREE.Vector3().crossVectors(upRef, forward).normalize();
  const up = new THREE.Vector3().crossVectors(forward, right).normalize();

  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
  const tanV = Math.tan(vFov / 2);
  const tanH = Math.tan(hFov / 2);

  const { min, max } = box;
  let dist = 0;
  for (let i = 0; i < 8; i++) {
    const v = new THREE.Vector3(
      i & 1 ? max.x : min.x,
      i & 2 ? max.y : min.y,
      i & 4 ? max.z : min.z,
    ).sub(center);
    const dz = v.dot(forward);
    dist = Math.max(dist, Math.abs(v.dot(right)) / tanH - dz, Math.abs(v.dot(up)) / tanV - dz);
  }
  return Math.max(dist, 0.001) * 1.07;
}

function setView(dir, fit) {
  const box = state.box;
  if (!box) return;
  const d = dir.clone().normalize();
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.001);

  // 接近正上/正下方时换 up 向量，避免视线与 up 平行
  if (Math.abs(d.z) > 0.985) camera.up.set(0, 1, 0);
  else camera.up.set(0, 0, 1);

  const dist = fit ? fitDistance(box, d) : Math.max(camera.position.distanceTo(controls.target), 0.001);

  camera.position.copy(center).addScaledVector(d, dist);
  camera.near = Math.max(0.05, dist / 800);
  camera.far = dist * 12 + radius * 6;
  camera.updateProjectionMatrix();

  controls.target.copy(center);
  controls.update();
}

/* ------------------------------------------------------------------ *
 *  UI：文件列表
 * ------------------------------------------------------------------ */

function fmtSize(bytes) {
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + 'M';
  return Math.round(bytes / 1024) + 'K';
}

function renderList() {
  const q = dom.search.value.trim().toLowerCase();
  const items = state.items.filter((it) => !q || it.name.toLowerCase().includes(q) || it.path.toLowerCase().includes(q));

  dom.list.innerHTML = '';
  if (items.length === 0) {
    const e = document.createElement('div');
    e.className = 'grp';
    e.textContent = state.items.length ? '没有匹配的文件' : '目录里没有找到 STEP 文件';
    dom.list.appendChild(e);
    return;
  }

  const groups = new Map();
  for (const it of items) {
    const key = it.folder || '根目录';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(it);
  }

  for (const [folder, arr] of groups) {
    const h = document.createElement('div');
    h.className = 'grp';
    h.innerHTML = `<span>${escapeHtml(folder)}</span><span class="n">${arr.length}</span>`;
    dom.list.appendChild(h);

    for (const it of arr) {
      const row = document.createElement('label');
      row.className = 'row' + (state.selected.has(it.path) ? ' on' : '');
      row.title = it.path;
      row.innerHTML =
        `<input type="checkbox" ${state.selected.has(it.path) ? 'checked' : ''} />` +
        `<span class="nm">${escapeHtml(it.name)}</span>` +
        `<span class="sz">${fmtSize(it.size)}</span>`;

      const cb = row.querySelector('input');
      cb.addEventListener('change', () => {
        if (cb.checked) state.selected.add(it.path);
        else state.selected.delete(it.path);
        row.classList.toggle('on', cb.checked);
        updateSelInfo();
        scheduleLoad();
      });
      dom.list.appendChild(row);
    }
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function updateSelInfo() {
  const n = state.selected.size;
  if (n === 0) { dom.selInfo.textContent = '未选择'; return; }
  const bytes = state.items.filter((i) => state.selected.has(i.path)).reduce((a, b) => a + b.size, 0);
  dom.selInfo.textContent = `已选 ${n} 个 · ${fmtSize(bytes)}`;
}

/* ------------------------------------------------------------------ *
 *  HUD
 * ------------------------------------------------------------------ */

function renderHud() {
  if (state.models.length === 0) { dom.hud.innerHTML = ''; return; }
  const f = (v) => (v >= 100 ? v.toFixed(1) : v.toFixed(2));
  dom.hud.innerHTML = state.models.map((m, i) => {
    const s = m.box.getSize(new THREE.Vector3());
    return `<div class="card">
      <div class="t" title="${escapeHtml(m.title)}">${state.models.length > 1 ? `<span class="idx">${i + 1}.</span>` : ''}<span class="nm">${escapeHtml(m.title)}</span></div>
      <div class="r"><span>外形 mm</span><b>${f(s.x)} × ${f(s.y)} × ${f(s.z)}</b></div>
      <div class="r"><span>三角面 / 零件</span><b>${m.stats.tris.toLocaleString('en-US')} / ${m.stats.parts}</b></div>
    </div>`;
  }).join('');
}

/* ------------------------------------------------------------------ *
 *  加载流程
 * ------------------------------------------------------------------ */

let loadTimer = null;
let loadToken = 0;

function scheduleLoad() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(loadSelection, 180);
}

function showOverlay(text) {
  dom.ovText.innerHTML = text;
  dom.overlay.classList.add('on');
}
function hideOverlay() { dom.overlay.classList.remove('on'); }

async function ensureModel(item, token) {
  if (state.cache.has(item.path)) return state.cache.get(item.path);

  const res = await fetch(item.url || ('/files/' + encodeURI(item.path)));
  if (!res.ok) throw new Error(`下载失败 HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  if (token !== loadToken) return null;

  const built = parseStep(buf, item.name);
  const entry = built;
  entry.title = item.name;
  cachePut(item.path, entry);
  return entry;
}

async function loadSelection() {
  const token = ++loadToken;
  const items = state.items.filter((i) => state.selected.has(i.path));
  if (items.length === 0) { clearScene(); state.box = null; renderHud(); hideOverlay(); return; }

  try {
    occt = await getOcct();
  } catch (e) {
    showOverlay(`<div class="err">STEP 解析内核加载失败：${escapeHtml(e.message)}</div>`);
    return;
  }

  clearScene();
  const t0 = performance.now();

  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    showOverlay(`解析中 ${i + 1}/${items.length} · ${escapeHtml(it.name)}${i === 0 ? '<div style="font-size:10.5px;color:#5f6876;margin-top:6px">首次解析需要几秒</div>' : ''}`);
    await new Promise((r) => requestAnimationFrame(r));
    try {
      const entry = await ensureModel(it, token);
      if (!entry || token !== loadToken) return;

      // 克隆以便多个模型共享几何数据
      const group = entry.group.clone(true);
      const edges = entry.edgeGroup.clone(true);
      edges.visible = state.opts.edges;
      root.add(group, edges);

      const box = new THREE.Box3().setFromObject(group);
      const bboxHelper = new THREE.Box3Helper(box.clone(), 0x3b8dff);
      bboxHelper.material.transparent = true;
      bboxHelper.material.opacity = 0.35;
      bboxHelper.visible = state.opts.bbox;
      root.add(bboxHelper);

      state.models.push({ path: it.path, title: it.name, group, edges, box, bboxHelper, stats: entry.stats });
    } catch (e) {
      console.error(it.path, e);
      const div = document.createElement('div');
      div.className = 'err';
      div.textContent = `${it.name} 解析失败：${e.message}`;
      dom.ovText.appendChild(div);
      await new Promise((r) => setTimeout(r, 900));
    }
  }

  if (token !== loadToken) return;
  layoutAndFit();
  renderHud();
  hideOverlay();
  console.log(`加载 ${items.length} 个模型，用时 ${(performance.now() - t0).toFixed(0)} ms`);
}

/* ------------------------------------------------------------------ *
 *  交互
 * ------------------------------------------------------------------ */

dom.search.addEventListener('input', () => renderList());

dom.clearSel.addEventListener('click', () => {
  state.selected.clear();
  renderList();
  updateSelInfo();
  scheduleLoad();
});

dom.views.addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  dom.views.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
  const map = {
    iso: new THREE.Vector3(1, -1.06, 0.72),
    front: new THREE.Vector3(0, -1, 0),
    back: new THREE.Vector3(0, 1, 0),
    left: new THREE.Vector3(-1, 0, 0),
    right: new THREE.Vector3(1, 0, 0),
    top: new THREE.Vector3(0, 0, 1),
    bottom: new THREE.Vector3(0, 0, -1),
  };
  const d = map[b.dataset.view];
  if (!d) return;
  state.viewDir = d.clone().normalize();
  setView(state.viewDir, true);
});

dom.chips.addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  const k = b.dataset.opt;

  if (k === 'reload') { hardReload(); return; }

  state.opts[k] = !state.opts[k];
  b.classList.toggle('on', state.opts[k]);
  applyOptions();
});

/** 显示异常时的手动兜底：重设尺寸 + 重设像素比 + 重新取景 */
function hardReload() {
  try {
    if (ctxLost && renderer.forceContextRestore) renderer.forceContextRestore();
    curW = curH = 0; curDpr = 0;              // 强制走一遍完整尺寸设置
    resize(true);
    if (state.box) setView(state.viewDir, true);
    applyOptions();
    forcedRender();
    toast('渲染已重载', 1200);
  } catch (err) {
    console.error(err);
    location.reload();
  }
}

/* 拖入本地 STEP 文件 */
window.addEventListener('dragover', (e) => { e.preventDefault(); });
window.addEventListener('drop', async (e) => {
  e.preventDefault();
  const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (!file) return;
  if (!/\.(stp|step|igs|iges|brep)$/i.test(file.name)) return;
  try {
    occt = await getOcct();
    showOverlay(`解析中 · ${escapeHtml(file.name)}`);
    await new Promise((r) => requestAnimationFrame(r));
    const buf = await file.arrayBuffer();
    const entry = parseStep(buf, file.name.replace(/\.[^.]+$/, ''));
    clearScene();
    const group = entry.group;
    const edges = entry.edgeGroup;
    root.add(group, edges);
    const box = new THREE.Box3().setFromObject(group);
    const bboxHelper = new THREE.Box3Helper(box.clone(), 0x3b8dff);
    bboxHelper.visible = state.opts.bbox;
    root.add(bboxHelper);
    state.models.push({
      path: file.name, title: file.name, group, edges, box, bboxHelper, stats: entry.stats,
    });
    layoutAndFit();
    renderHud();
    hideOverlay();
  } catch (err) {
    showOverlay(`<div class="err">${escapeHtml(err.message)}</div>`);
    setTimeout(hideOverlay, 2600);
  }
});

/* ------------------------------------------------------------------ *
 *  尺寸自适应（对嵌入式面板做兜底：拿不到尺寸时多级回退 + 自愈）
 * ------------------------------------------------------------------ */

let curW = 0, curH = 0, curDpr = 0;
let ctxLost = false;

function readStageSize() {
  // 1) 正常路径
  const r = dom.stage.getBoundingClientRect();
  let w = Math.round(r.width);
  let h = Math.round(r.height);
  // 2) 面板正在显隐 / 动画时 rect 可能为 0，退回 clientWidth
  if (w < 2 || h < 2) { w = dom.stage.clientWidth; h = dom.stage.clientHeight; }
  // 3) 再不行按视口推算（左侧栏 322px）
  if (w < 2 || h < 2) { w = window.innerWidth - 322; h = window.innerHeight; }
  // 4) 最后兜底，但绝不用 1×1（会被拉伸成一片空白）
  if (!isFinite(w) || w < 2) w = 640;
  if (!isFinite(h) || h < 2) h = 480;
  return { w: Math.round(w), h: Math.round(h) };
}

function resize(force) {
  const { w, h } = readStageSize();

  // 像素比：面板放到很大时限制绘制缓冲长边，避免超显卡上限导致整屏黑
  const MAX_EDGE = 4096;
  let dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cap = MAX_EDGE / Math.max(w, h);
  if (dpr > cap) dpr = Math.max(cap, 0.5);

  if (!force && w === curW && h === curH && Math.abs(dpr - curDpr) < 0.01) return false;

  curW = w; curH = h; curDpr = dpr;

  renderer.setPixelRatio(dpr);
  renderer.setSize(w, h, true);   // true: 同时写死 canvas 样式，不依赖百分比链路

  const aspect = w / h;
  if (isFinite(aspect) && aspect > 0) {
    camera.aspect = aspect;
    camera.updateProjectionMatrix();
  }
  return true;
}

/* 所有可能改变尺寸的信号都接上 */
if (typeof ResizeObserver !== 'undefined') {
  new ResizeObserver(() => resize()).observe(dom.stage);
}
window.addEventListener('resize', () => resize());
window.addEventListener('orientationchange', () => resize(true));
if (window.visualViewport) window.visualViewport.addEventListener('resize', () => resize(true));
document.addEventListener('visibilitychange', () => { if (!document.hidden) { resize(true); forcedRender(); } });

resize(true);

/* ------------------------------------------------------------------ *
 *  WebGL 上下文丢失兜底
 * ------------------------------------------------------------------ */

function toast(msg, ms = 2400) {
  if (!dom.toast) return;
  dom.toast.textContent = msg;
  dom.toast.classList.add('on');
  clearTimeout(toast._t);
  if (ms) toast._t = setTimeout(() => dom.toast.classList.remove('on'), ms);
}

dom.cv.addEventListener('webglcontextlost', (e) => {
  e.preventDefault();
  ctxLost = true;
  toast('显卡上下文丢失，正在恢复…', 0);
}, false);

dom.cv.addEventListener('webglcontextrestored', () => {
  ctxLost = false;
  resize(true);
  if (state.box) setView(state.viewDir, true);
  applyOptions();
  toast('已恢复', 1200);
}, false);

/* ------------------------------------------------------------------ *
 *  渲染循环：自己管 rAF，保证任何异常都不会把循环打死
 * ------------------------------------------------------------------ */

let frameNo = 0;
let loopError = null;

function forcedRender() {
  try { renderer.render(scene, camera); } catch (_) {}
}

function tick() {
  requestAnimationFrame(tick);
  frameNo++;
  try {
    // 每 30 帧对一次尺寸，防止面板大小变化没触发 ResizeObserver
    if ((frameNo & 31) === 0) resize();
    if (ctxLost) return;
    controls.update();
    renderer.render(scene, camera);
    if (loopError) { loopError = null; }
  } catch (err) {
    if (!loopError) {
      loopError = err;
      console.error('[render]', err);
      toast('渲染异常，已自动跳过该帧', 2000);
    }
  }
}
requestAnimationFrame(tick);

/* 调试钩子（浏览器控制台可用） */
window.__viewer = {
  state, scene, camera, controls, setView,
  info() {
    const c = state.box ? state.box.getCenter(new THREE.Vector3()).project(camera) : null;
    return {
      buffer: [renderer.domElement.width, renderer.domElement.height],
      stage: [dom.stage.clientWidth, dom.stage.clientHeight],
      dpr: +curDpr.toFixed(2),
      aspect: +camera.aspect.toFixed(4),
      ctxLost,
      frames: frameNo,
      centerNDC: c ? [+c.x.toFixed(3), +c.y.toFixed(3)] : null,
      camPos: camera.position.toArray().map(n => +n.toFixed(1)),
      models: state.models.length,
    };
  },
};

/* ------------------------------------------------------------------ *
 *  启动：读取目录清单
 * ------------------------------------------------------------------ */

(async function boot() {
  // 先把解析内核预热，省掉第一次点模型的等待
  getOcct().catch(() => {});

  try {
    const res = await fetch('/api/list');
    const data = await res.json();
    dom.srcPath.textContent = data.dir;
    if (!data.ok) {
      dom.list.innerHTML = `<div class="grp">目录不存在：${escapeHtml(data.dir)}</div>`;
      return;
    }
    state.items = data.items;
    renderList();

    if (state.items.length) {
      state.selected.add(state.items[0].path);
      renderList();
      updateSelInfo();
      loadSelection();
    }
  } catch (e) {
    dom.list.innerHTML = `<div class="grp">读取目录失败：${escapeHtml(e.message)}</div>`;
  }
})();
