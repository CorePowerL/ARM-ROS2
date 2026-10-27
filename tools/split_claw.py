#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 part_claw.stl（21 个独立零件的刚性装配体）按**运动副**拆成 7 块，供 URDF 做真四连杆夹爪：

    claw_body.stl          机身：背板 + 舵机支架 + 4 个垫块 + 3 个小垫块
    claw_gear_left.stl     左齿轮扇形板（圆盘 + 带齿臂）
    claw_gear_right.stl    右齿轮扇形板
    claw_bar_left.stl      左平行连杆（两片，Y 正反各一）
    claw_bar_right.stl     右平行连杆（两片）
    claw_finger_left.stl   左指片（两片 3mm 夹板）
    claw_finger_right.stl  右指片（两片）

拆分依据 —— 对装配体做顶点焊接 + 并查集得到的 21 个连通分件，
再用「面数 + 质心 X」分类（比纯包围盒稳，因为同型号零件面数完全相同）：

    面数 7398 × 4            → 指片（16.9 × 3.0 × 59.3 mm）
    面数 3036 × 1            → 左齿轮的圆盘（整爪只有一片圆盘）
    面数 1360 × 2            → 左/右齿轮的带齿臂
    面数  708 × 4            → 平行连杆（12.2 × 3.0 × 36.5 mm）
    面数 3040 × 1            → 机身背板（57.0 × 2.0 × 48.0 mm）
    面数 1112 × 2            → 舵盘夹（19.0 × 10.0 × 10.0 mm）
    面数  504 × 4            → 大垫块（6.0 × 10.0 × 6.0 mm）
    面数  368 × 3            → 小垫块（6.0 × 3.0 × 6.0 mm）

质心 X < 2.75 mm（装配体对称面）判为左，否则右。

四连杆拓扑（孔位共点推出，详见 tools/claw_4bar.py）：

    机身 ──G── 齿轮臂 ──A── 指片 ──B── 平行连杆 ──R── 机身

用法：
    python tools/split_claw.py k3b_arm_urdf/meshes/part_claw.stl
"""

import os
import struct
import sys
from collections import defaultdict

PLANE_X = 0.00275          # 装配体对称面（m）
TRI_FINGER = 7398
TRI_GEAR_DISC = 3036
TRI_GEAR_ARM = 1360
TRI_BAR = 708


def read_stl(path):
    data = open(path, "rb").read()
    if len(data) < 84:
        raise ValueError("文件太小，不是二进制 STL")
    n = struct.unpack("<I", data[80:84])[0]
    if len(data) < 84 + n * 50:
        raise ValueError("三角面数量与文件长度不符，可能是 ASCII STL")
    tris = []
    for i in range(n):
        o = 84 + i * 50
        v = struct.unpack("<12f", data[o:o + 48])
        tris.append(tuple(
            tuple(round(c, 6) for c in v[3 + k * 3: 6 + k * 3]) for k in range(3)
        ))
    return tris


def components(tris):
    """顶点焊接后并查集，返回 [[三角面索引...], ...]。"""
    vmap, idx = {}, []
    for t in tris:
        ids = []
        for v in t:
            if v not in vmap:
                vmap[v] = len(vmap)
            ids.append(vmap[v])
        idx.append(ids)

    parent = list(range(len(vmap)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for ids in idx:
        union(ids[0], ids[1])
        union(ids[1], ids[2])

    comp = defaultdict(list)
    for i, ids in enumerate(idx):
        comp[find(ids[0])].append(i)
    return list(comp.values())


def bbox(tris, tlist):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for ti in tlist:
        for v in tris[ti]:
            for a in range(3):
                lo[a] = min(lo[a], v[a])
                hi[a] = max(hi[a], v[a])
    return lo, hi


def write_stl(path, tris, tlist, name="part"):
    header = str(name).encode("ascii", "replace")[:80].ljust(80, b" ")
    with open(path, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(tlist)))
        for ti in tlist:
            a, b, c = tris[ti]
            u = [b[i] - a[i] for i in range(3)]
            w = [c[i] - a[i] for i in range(3)]
            nx = u[1] * w[2] - u[2] * w[1]
            ny = u[2] * w[0] - u[0] * w[2]
            nz = u[0] * w[1] - u[1] * w[0]
            ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
            f.write(struct.pack("<3f", nx / ln, ny / ln, nz / ln))
            f.write(struct.pack("<9f", *(a + b + c)))
            f.write(struct.pack("<H", 0))


def classify(cnt, cx):
    """(面数, 质心X) -> (归属键, 中文名)。"""
    side = "left" if cx < PLANE_X else "right"
    zh = "左" if side == "left" else "右"
    if cnt == TRI_FINGER:
        return f"claw_finger_{side}.stl", f"{zh}指片"
    if cnt in (TRI_GEAR_DISC, TRI_GEAR_ARM):
        return f"claw_gear_{side}.stl", f"{zh}齿轮扇形板"
    if cnt == TRI_BAR:
        return f"claw_bar_{side}.stl", f"{zh}平行连杆"
    return "claw_body.stl", "机身"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "k3b_arm_urdf/meshes/part_claw.stl"
    outdir = os.path.dirname(src)

    tris = read_stl(src)
    print(f"读入 {src}：{len(tris)} 个三角面")
    comps = components(tris)
    print(f"连通分件：{len(comps)} 个\n")

    buckets = defaultdict(list)
    rows = []
    for tlist in comps:
        lo, hi = bbox(tris, tlist)
        size = [(hi[a] - lo[a]) * 1000 for a in range(3)]
        cx = (lo[0] + hi[0]) / 2
        fn, tag = classify(len(tlist), cx)
        buckets[fn] += tlist
        rows.append((len(tlist), size, cx, tag, fn))

    rows.sort(key=lambda r: (-r[0], r[2]))
    print(f"{'面数':>7} {'sizeX':>7} {'sizeY':>7} {'sizeZ':>7} {'质心X':>8}  归属")
    for cnt, size, cx, tag, fn in rows:
        print(f"{cnt:>7} {size[0]:>7.1f} {size[1]:>7.1f} {size[2]:>7.1f} "
              f"{cx*1000:>8.2f}  {tag}  -> {fn}")

    print()
    total = 0
    for fn in sorted(buckets):
        tlist = buckets[fn]
        p = os.path.join(outdir, fn)
        write_stl(p, tris, tlist, fn)
        lo, hi = bbox(tris, tlist)
        total += len(tlist)
        print(f"{fn:<24} {len(tlist):>6} 面   "
              f"X {lo[0]*1000:>7.2f}..{hi[0]*1000:>7.2f}  "
              f"Y {lo[1]*1000:>6.2f}..{hi[1]*1000:>6.2f}  "
              f"Z {lo[2]*1000:>7.2f}..{hi[2]*1000:>7.2f}  (mm)")

    print(f"\n合计 {total} 面（原 {len(tris)}）", end="")
    if total != len(tris):
        print("  !! 面数对不上，有零件被漏掉")
        return 1
    print("  ✓")
    if len(buckets) != 7:
        print(f"警告：只生成 {len(buckets)} 个文件，预期 7 个")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
