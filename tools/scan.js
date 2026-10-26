#!/usr/bin/env node
/**
 * 批量扫描目录里的 STEP，输出尺寸清单（不导出网格）
 *   node tools/scan.js <目录> [--filter 关键字]
 */
const fs = require('fs');
const path = require('path');
const occtimportjs = require(path.resolve(__dirname, '..', 'viewer3d', 'vendor', 'occt', 'occt-import-js.js'));

const dir = process.argv[2];
const filterIdx = process.argv.indexOf('--filter');
const filter = filterIdx > 0 ? process.argv[filterIdx + 1] : null;

function walk(d, base = d, out = []) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p, base, out);
    else if (/\.(stp|step)$/i.test(e.name)) out.push(p);
  }
  return out;
}

const bboxOf = (meshes) => {
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const m of meshes) {
    const a = m.attributes.position.array;
    for (let i = 0; i < a.length; i += 3) {
      for (let k = 0; k < 3; k++) {
        if (a[i + k] < min[k]) min[k] = a[i + k];
        if (a[i + k] > max[k]) max[k] = a[i + k];
      }
    }
  }
  return { min, max, size: [max[0] - min[0], max[1] - min[1], max[2] - min[2]] };
};

(async () => {
  const occt = await occtimportjs();
  let files = walk(dir).sort();
  if (filter) files = files.filter((f) => f.includes(filter));

  console.log('尺寸(mm)              X       Y       Z     零件 三角   文件名');
  console.log('='.repeat(96));
  for (const f of files) {
    try {
      const r = occt.ReadStepFile(new Uint8Array(fs.readFileSync(f)), {
        linearUnit: 'millimeter', linearDeflectionType: 'bounding_box_ratio',
        linearDeflection: 0.003, angularDeflection: 0.4,
      });
      if (!r.success) { console.log('  [解析失败]', path.basename(f)); continue; }
      const m = r.meshes.filter((x) => x.attributes?.position?.array.length >= 9);
      if (!m.length) continue;
      const b = bboxOf(m);
      const tris = m.reduce((s, x) => s + x.index.array.length / 3, 0);
      console.log(
        (b.size.map((v) => v.toFixed(2).padStart(7)).join(' ')) +
        String(m.length).padStart(6) + String(tris).padStart(8) + '   ' + path.basename(f)
      );
    } catch (e) {
      console.log('  [错误]', path.basename(f), e.message);
    }
  }
})();
