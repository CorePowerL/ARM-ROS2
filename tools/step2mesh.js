#!/usr/bin/env node
/**
 * STEP → URDF 网格（OBJ + MTL + STL）
 *
 * 依赖：viewer3d/vendor/occt/occt-import-js.js（已在项目里，离线可用）
 *
 * 用法：
 *   node tools/step2mesh.js <输入.stp> --out <输出前缀> [选项]
 *
 * 选项：
 *   --out      输出前缀（生成 <前缀>.obj / <前缀>.mtl / <前缀>.stl）
 *   --scale    缩放，默认 0.001（STEP 是 mm，URDF 要 m）
 *   --analyze  只做几何分析，打印包围盒与各面突起，不导出
 *   --shaft    +X|-X|+Y|-Y|+Z|-Z，指定输出轴方向（导出时把它旋到 +Z，轴心移到原点）
 *   --ignore   分析时忽略的网格名子串（如线缆），可重复
 *
 * 说明：URDF 默认按米建模，故默认 --scale 0.001。
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const OCCT = path.join(ROOT, 'viewer3d', 'vendor', 'occt', 'occt-import-js.js');
const occtimportjs = require(OCCT);

/* ---------------- 参数 ---------------- */

function parseArgs(argv) {
  const a = { _: [], ignore: [], drop: [], scale: 0.001, analyze: false };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t === '--analyze') a.analyze = true;
    else if (t === '--out') a.out = argv[++i];
    else if (t === '--scale') a.scale = parseFloat(argv[++i]);
    else if (t === '--shaft') a.shaft = argv[++i].toUpperCase();
    else if (t === '--ignore') a.ignore.push(argv[++i]);
    else if (t === '--parts') a.parts = true;
    else if (t === '--drop') a.drop.push(argv[++i]);
    else if (t === '--pivot') {
      const v = argv[++i];
      a.pivot = v === 'center' ? 'center' : v.split(',').map(Number);
    }
    else a._.push(t);
  }
  return a;
}

const args = parseArgs(process.argv.slice(2));
if (!args._.length) {
  console.error('用法: node tools/step2mesh.js <输入.stp> --out <前缀> [--analyze] [--shaft +Z]');
  process.exit(1);
}

/* ---------------- 几何工具 ---------------- */

function vertexIter(meshes, fn) {
  for (const m of meshes) {
    const p = m.attributes.position.array;
    for (let i = 0; i < p.length; i += 3) fn(p[i], p[i + 1], p[i + 2], m);
  }
}

function bbox(meshes) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  vertexIter(meshes, (x, y, z) => {
    if (x < min[0]) min[0] = x; if (x > max[0]) max[0] = x;
    if (y < min[1]) min[1] = y; if (y > max[1]) max[1] = y;
    if (z < min[2]) min[2] = z; if (z > max[2]) max[2] = z;
  });
  return { min, max, size: [max[0] - min[0], max[1] - min[1], max[2] - min[2]] };
}

/** 沿某个方向看，最外侧一层薄片的顶点分布（用于找输出轴突起） */
function probePlane(meshes, axis, sign, bb) {
  const lo = bb.min[axis], hi = bb.max[axis];
  const depth = (hi - lo) * 0.04 + 0.2;
  const other = [0, 1, 2].filter((i) => i !== axis);

  let n = 0;
  let sx = 0, sy = 0;
  let mn1 = Infinity, mx1 = -Infinity, mn2 = Infinity, mx2 = -Infinity;

  vertexIter(meshes, (x, y, z) => {
    const v = [x, y, z];
    const d = sign > 0 ? hi - v[axis] : v[axis] - lo;
    if (d > depth) return;
    n++;
    sx += v[other[0]]; sy += v[other[1]];
    if (v[other[0]] < mn1) mn1 = v[other[0]];
    if (v[other[0]] > mx1) mx1 = v[other[0]];
    if (v[other[1]] < mn2) mn2 = v[other[1]];
    if (v[other[1]] > mx2) mx2 = v[other[1]];
  });

  if (!n) return null;
  return {
    n,
    center: [sx / n, sy / n],
    span: [mx1 - mn1, mx2 - mn2],
    radius: Math.max(mx1 - mn1, mx2 - mn2) / 2,
  };
}

/* ---------------- 导出 ---------------- */

function colorKey(c) {
  if (!c) return 'cccccc';
  const h = (v) => Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
  return h(c[0]) + h(c[1]) + h(c[2]);
}

function toMeters(v, s) { return v * s; }

/** 输出轴方向 → 把该方向旋到 +Z 的旋转矩阵（行主序 3x3） */
function shaftRotation(dir) {
  const target = [0, 0, 1];
  const from = { '+X': [1, 0, 0], '-X': [-1, 0, 0], '+Y': [0, 1, 0], '-Y': [0, -1, 0], '+Z': [0, 0, 1], '-Z': [0, 0, -1] }[dir];
  if (!from) return null;
  // 求把 from 转到 target 的最小旋转
  const dot = from[0] * target[0] + from[1] * target[1] + from[2] * target[2];
  let axis = [
    from[1] * target[2] - from[2] * target[1],
    from[2] * target[0] - from[0] * target[2],
    from[0] * target[1] - from[1] * target[0],
  ];
  const len = Math.hypot(...axis);
  if (len < 1e-9) {
    // 平行或反平行
    if (dot > 0) return [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
    return [[1, 0, 0], [0, -1, 0], [0, 0, -1]]; // 绕 X 转 180°
  }
  axis = axis.map((v) => v / len);
  const ang = Math.acos(Math.max(-1, Math.min(1, dot)));
  const c = Math.cos(ang), s = Math.sin(ang), t = 1 - c;
  const [x, y, z] = axis;
  return [
    [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
    [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
    [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
  ];
}

function applyM(m, v) {
  return [
    m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
    m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
    m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
  ];
}

function exportOBJ(meshes, prefix, scale, rot, pivot) {
  const lines = [];
  const mtlName = path.basename(prefix) + '.mtl';
  lines.push(`# STEP -> OBJ  (units: meter, from ${path.basename(args._[0])})`);
  lines.push(`mtllib ${mtlName}`);

  const colors = new Map();
  let vBase = 1, nBase = 1;

  for (const m of meshes) {
    const pos = m.attributes.position.array;
    const nrm = m.attributes.normal ? m.attributes.normal.array : null;
    const idx = m.index.array;
    const vertCount = pos.length / 3;

    for (let i = 0; i < vertCount; i++) {
      let v = [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]];
      if (rot) v = applyM(rot, v);
      v = [v[0] - pivot[0], v[1] - pivot[1], v[2] - pivot[2]];
      lines.push(`v ${(v[0] * scale).toFixed(6)} ${(v[1] * scale).toFixed(6)} ${(v[2] * scale).toFixed(6)}`);
    }
    if (nrm) {
      for (let i = 0; i < vertCount; i++) {
        let n = [nrm[i * 3], nrm[i * 3 + 1], nrm[i * 3 + 2]];
        if (rot) n = applyM(rot, n);
        lines.push(`vn ${n[0].toFixed(5)} ${n[1].toFixed(5)} ${n[2].toFixed(5)}`);
      }
    }

    // 按 brep 面着色分组
    const faces = Array.isArray(m.brep_faces) ? m.brep_faces : [];
    const tris = idx.length / 3;
    let t = 0, fi = 0, cur = 'usemtl c' + colorKey(m.color);
    const groups = [];

    while (t < tris && fi <= faces.length) {
      let last, ck;
      if (fi >= faces.length) {
        last = tris;
        ck = 'c' + colorKey(m.color);
      } else if (t < faces[fi].first) {
        last = faces[fi].first;
        ck = 'c' + colorKey(m.color);
      } else {
        const f = faces[fi];
        last = Math.min(f.last + 1, tris);
        ck = 'c' + colorKey(f.color || m.color);
        fi++;
      }
      if (last <= t) { fi++; t++; continue; }
      groups.push({ from: t, to: last, ck });
      t = last;
    }
    if (!groups.length) groups.push({ from: 0, to: tris, ck: 'c' + colorKey(m.color) });

    for (const g of groups) {
      if (!colors.has(g.ck)) colors.set(g.ck, g.ck.slice(1));
      lines.push(`g ${(m.name || 'part').replace(/\s+/g, '_')}_${g.from}`);
      lines.push(`usemtl ${g.ck}`);
      for (let tri = g.from; tri < g.to; tri++) {
        const a = idx[tri * 3] + vBase, b = idx[tri * 3 + 1] + vBase, c = idx[tri * 3 + 2] + vBase;
        if (nrm) {
          const na = idx[tri * 3] + nBase, nb = idx[tri * 3 + 1] + nBase, nc = idx[tri * 3 + 2] + nBase;
          lines.push(`f ${a}//${na} ${b}//${nb} ${c}//${nc}`);
        } else {
          lines.push(`f ${a} ${b} ${c}`);
        }
      }
    }
    vBase += vertCount;
    nBase += nrm ? vertCount : 0;
  }

  fs.writeFileSync(prefix + '.obj', lines.join('\n') + '\n');

  const mtl = ['# 由 STEP 颜色自动生成'];
  for (const [name, hex] of colors) {
    const r = parseInt(hex.slice(0, 2), 16) / 255;
    const g = parseInt(hex.slice(2, 4), 16) / 255;
    const b = parseInt(hex.slice(4, 6), 16) / 255;
    mtl.push(`newmtl ${name}`, `Kd ${r.toFixed(4)} ${g.toFixed(4)} ${b.toFixed(4)}`,
      `Ka 0.1 0.1 0.1`, `Ks 0.22 0.22 0.22`, `Ns 24`, `illum 2`, '');
  }
  fs.writeFileSync(prefix + '.mtl', mtl.join('\n'));
  return { mtlTriColors: colors.size };
}

function exportSTL(meshes, prefix, scale, rot, pivot) {
  let triCount = 0;
  for (const m of meshes) triCount += m.index.array.length / 3;

  const buf = Buffer.alloc(84 + triCount * 50);
  buf.write('K3B arm mesh, generated from STEP', 0, 80, 'ascii');
  buf.writeUInt32LE(triCount, 80);

  const tf = (v) => {
    let p = rot ? applyM(rot, v) : v;
    return [(p[0] - pivot[0]) * scale, (p[1] - pivot[1]) * scale, (p[2] - pivot[2]) * scale];
  };

  let off = 84;
  for (const m of meshes) {
    const pos = m.attributes.position.array;
    const idx = m.index.array;
    for (let t = 0; t < idx.length; t += 3) {
      const a = tf([pos[idx[t] * 3], pos[idx[t] * 3 + 1], pos[idx[t] * 3 + 2]]);
      const b = tf([pos[idx[t + 1] * 3], pos[idx[t + 1] * 3 + 1], pos[idx[t + 1] * 3 + 2]]);
      const c = tf([pos[idx[t + 2] * 3], pos[idx[t + 2] * 3 + 1], pos[idx[t + 2] * 3 + 2]]);
      const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      let n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
      const L = Math.hypot(...n) || 1;
      n = n.map((x) => x / L);
      for (const p of [n, a, b, c]) {
        buf.writeFloatLE(p[0], off); buf.writeFloatLE(p[1], off + 4); buf.writeFloatLE(p[2], off + 8);
        off += 12;
      }
      buf.writeUInt16LE(0, off); off += 2;
    }
  }
  fs.writeFileSync(prefix + '.stl', buf);
  return triCount;
}

/* ---------------- 主流程 ---------------- */

(async () => {
  const input = args._[0];
  if (!fs.existsSync(input)) {
    console.error('找不到文件:', input);
    process.exit(1);
  }

  const occt = await occtimportjs();
  const raw = fs.readFileSync(input);
  const t0 = Date.now();
  const res = occt.ReadStepFile(new Uint8Array(raw), {
    linearUnit: 'millimeter',
    linearDeflectionType: 'bounding_box_ratio',
    linearDeflection: 0.0015,
    angularDeflection: 0.28,
  });
  if (!res.success) { console.error('解析失败'); process.exit(1); }

  const meshes = res.meshes.filter(
    (m) => m.attributes && m.attributes.position && m.attributes.position.array.length >= 9
      && !args.drop.some((d) => (m.name || '').toUpperCase().includes(d.toUpperCase()))
  );
  const bb = bbox(meshes);
  const tris = meshes.reduce((s, m) => s + m.index.array.length / 3, 0);

  console.log('文件      :', path.basename(input));
  console.log('解析耗时  :', (Date.now() - t0) + ' ms');
  console.log('网格数    :', meshes.length, ' 三角面:', tris);
  console.log('包围盒 min:', bb.min.map((v) => v.toFixed(2)).join(', '), ' (mm)');
  console.log('包围盒 max:', bb.max.map((v) => v.toFixed(2)).join(', '), ' (mm)');
  console.log('外形尺寸  :', bb.size.map((v) => v.toFixed(2)).join(' × '), ' mm');
  console.log('');
  console.log('各面外缘薄片分布（找输出轴突起 / 线缆）:');
  const AX = ['X', 'Y', 'Z'];
  for (let ax = 0; ax < 3; ax++) {
    for (const sign of [1, -1]) {
      const p = probePlane(meshes, ax, sign, bb);
      if (!p) continue;
      const dir = (sign > 0 ? '+' : '-') + AX[ax];
      const other = [0, 1, 2].filter((i) => i !== ax).map((i) => AX[i]).join('/');
      console.log(
        `  ${dir}  n=${String(p.n).padStart(5)}  ${other} 跨距=${p.span.map((v) => v.toFixed(2)).join('×').padEnd(14)}` +
        ` 半径=${p.radius.toFixed(2)}  中心=(${p.center.map((v) => v.toFixed(2)).join(', ')})`
      );
    }
  }

  if (args.parts) {
    console.log('\n逐零件包围盒:');
    meshes.forEach((m, i) => {
      const b = bbox([m]);
      const t = m.index.array.length / 3;
      console.log(
        `  [${String(i).padStart(2)}] ${String(m.name || '(未命名)').slice(0, 22).padEnd(23)}` +
        ` tris=${String(t).padStart(6)}  size=${b.size.map((v) => v.toFixed(2)).join(' × ').padEnd(22)}` +
        ` min=(${b.min.map((v) => v.toFixed(1)).join(',')}) max=(${b.max.map((v) => v.toFixed(1)).join(',')})`
      );
    });
  }

  if (args.analyze || !args.out) {
    console.log('\n（未指定 --out，只做分析）');
    return;
  }

  let rot = null;
  let pivot = [0, 0, 0];
  if (args.shaft) {
    rot = shaftRotation(args.shaft);
    if (!rot) { console.error('--shaft 取值无效'); process.exit(1); }
  }
  if (args.pivot === 'center') {
    pivot = [
      (bb.min[0] + bb.max[0]) / 2,
      (bb.min[1] + bb.max[1]) / 2,
      (bb.min[2] + bb.max[2]) / 2,
    ];
  } else if (Array.isArray(args.pivot) && args.pivot.length === 3 && args.pivot.every((v) => isFinite(v))) {
    pivot = args.pivot;
  } else if (args.shaft) {
    // 未给 --pivot 时，取该方向最外层的薄片中心作为轴心
    const axMap = { X: 0, Y: 1, Z: 2 };
    const ax = axMap[args.shaft[1]];
    const sign = args.shaft[0] === '+' ? 1 : -1;
    const p = probePlane(meshes, ax, sign, bb);
    if (p) {
      pivot[ax] = sign > 0 ? bb.max[ax] : bb.min[ax];
      const o = [0, 1, 2].filter((i) => i !== ax);
      pivot[o[0]] = p.center[0];
      pivot[o[1]] = p.center[1];
    }
  }

  const prefix = args.out;
  fs.mkdirSync(path.dirname(prefix), { recursive: true });

  const tfRot = rot;
  const tfPivot = pivot;

  const a = exportOBJ(meshes, prefix, args.scale, tfRot, tfPivot);
  const t = exportSTL(meshes, prefix, args.scale, tfRot, tfPivot);

  const oSize = fs.statSync(prefix + '.obj').size;
  const sSize = fs.statSync(prefix + '.stl').size;
  console.log('\n导出:');
  console.log(`  ${path.basename(prefix)}.obj  ${(oSize / 1024 / 1024).toFixed(2)} MB  (${a.mtlTriColors} 种颜色)`);
  console.log(`  ${path.basename(prefix)}.mtl`);
  console.log(`  ${path.basename(prefix)}.stl  ${(sSize / 1024 / 1024).toFixed(2)} MB  (${t} 面)`);
  if (args.shaft) console.log(`  输出轴 ${args.shaft} 已旋到 +Z，轴心已移至原点`);
})();
