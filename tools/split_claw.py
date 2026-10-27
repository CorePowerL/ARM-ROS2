#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 part_claw.stl（21 个独立零件的装配体）拆成三块，供 URDF 做可动夹爪：

    claw_body.stl      壳体 + 平行连杆 + 舵机支架
    finger_left.stl    左指（两块 3mm 长夹板）
    finger_right.stl   右指

拆分依据（对 part_claw.stl 实测，单位 m）：
    整体包围盒  X ±0.0297   Y ±0.0110   Z −0.0543..+0.0543
    → 张开方向 = X，厚度 = Y，指长 = Z（第 11 号零件起为壳体一侧）
    四块长夹板（各 16.9×3.0×59.3 mm）就是两根手指，X 中间留 7.5 mm 缝。

分类规则（只认长薄板，避免把连杆误判成手指）：
    sizeZ > 56 mm 且 sizeX < 20 mm 且 sizeY < 6 mm  →  手指板
    质心 X < 2.75 mm（装配体对称面）→ 左指，否则右指
    其余全部归壳体。

用法：
    python tools/split_claw.py k3b_arm_urdf/meshes/part_claw.stl
"""

import struct
import sys
import os
from collections import defaultdict

PLANE_X = 0.00275          # 装配体对称面（由 4 块手指板的镜像关系反推）
FINGER_MIN_Z = 0.056
FINGER_MAX_X = 0.020
FINGER_MAX_Y = 0.006


def read_stl(path):
    """读二进制 STL，返回 (tris, normals)；tris 为 [(v0,v1,v2)]，v 为 3 元组。"""
    data = open(path, "rb").read()
    if len(data) < 84:
        raise ValueError("文件太小，不是二进制 STL")
    n = struct.unpack("<I", data[80:84])[0]
    if len(data) < 84 + n * 50:
        raise ValueError("三角面数量与文件长度不符，可能是 ASCII STL")
    tris, norms = [], []
    for i in range(n):
        o = 84 + i * 50
        v = struct.unpack("<12f", data[o:o + 48])
        norms.append(v[0:3])
        tris.append(tuple(
            tuple(round(c, 6) for c in v[3 + k * 3: 6 + k * 3]) for k in range(3)
        ))
    return tris, norms


def components(tris):
    """按顶点焊接后做并查集，返回 [[三角面索引...], ...]。"""
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
    lo = [1e9] * 3
    hi = [-1e9] * 3
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


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "k3b_arm_urdf/meshes/part_claw.stl"
    outdir = os.path.dirname(src)

    tris, _ = read_stl(src)
    print(f"读入 {src}：{len(tris)} 个三角面")

    comps = components(tris)
    print(f"连通分件：{len(comps)} 个\n")

    body, left, right = [], [], []
    rows = []
    for ci, tlist in enumerate(comps):
        lo, hi = bbox(tris, tlist)
        size = [hi[a] - lo[a] for a in range(3)]
        cx = (lo[0] + hi[0]) / 2
        is_finger = (size[2] > FINGER_MIN_Z and size[0] < FINGER_MAX_X
                     and size[1] < FINGER_MAX_Y)
        if is_finger:
            if cx < PLANE_X:
                left += tlist
                tag = "左指"
            else:
                right += tlist
                tag = "右指"
        else:
            body += tlist
            tag = "壳体"
        rows.append((ci, len(tlist), size, cx, tag))

    rows.sort(key=lambda r: -r[1])
    print(f"{'#':>3} {'面数':>7} {'sizeX':>7} {'sizeY':>7} {'sizeZ':>7} {'质心X':>8}  归属")
    for ci, cnt, size, cx, tag in rows:
        print(f"{ci:>3} {cnt:>7} {size[0]*1000:>7.1f} {size[1]*1000:>7.1f} "
              f"{size[2]*1000:>7.1f} {cx*1000:>8.2f}  {tag}")

    jobs = [("claw_body.stl", body), ("finger_left.stl", left), ("finger_right.stl", right)]
    print()
    for fn, tlist in jobs:
        p = os.path.join(outdir, fn)
        write_stl(p, tris, tlist, fn)
        lo, hi = bbox(tris, tlist)
        print(f"{fn:<18} {len(tlist):>6} 面   "
              f"X {lo[0]*1000:>7.2f}..{hi[0]*1000:>7.2f}  "
              f"Y {lo[1]*1000:>6.2f}..{hi[1]*1000:>6.2f}  "
              f"Z {lo[2]*1000:>7.2f}..{hi[2]*1000:>7.2f}  (mm)")

    if not left or not right:
        print("\n警告：有一侧没有识别到手指板，请检查分类阈值！")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
