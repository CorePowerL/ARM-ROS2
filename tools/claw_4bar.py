#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 part_claw.stl 的孔位反解机械爪四连杆，并给出 URDF 用的 mimic 系数。

拓扑（由孔位共点关系确定，见 tools/split_claw.py 的分件输出）：

    机身 #4 ──(G)── 齿轮扇形板 #5+#7 ──(A)── 指片 #0/#1 ──(B)── 平行连杆 #10/#12 ──(R)── 机身 #4

    四连杆：  G(齿轮轴) - A(指根销) - B(指中销) - R(连杆根销)
              rocker1      coupler       rocker2      ground

对称性：左右两指是镜像，两个齿轮扇形板相互啮合，所以右指 = 左指的反向等角（mimic -1）。

用法:
    python tools/claw_4bar.py            # 打印参数表与开合扫描
    python tools/claw_4bar.py --json     # 输出 JSON（供 xacro 脚本消费）
"""
import math
import json
import sys

# ---- 半侧坐标系 (u, v) -------------------------------------------------------
# u = 到对称面 X=2.75mm 的距离（向外为正），v = claw 网格的 Z
# 数值来自 part_claw.stl 的孔位检测（mm）
G = (13.45, 30.0)      # 齿轮扇形板转轴（机身）      #5 中心孔 / #7 中心孔
A = (15.65, 0.1)       # 齿轮臂 -> 指根的销          #7 与 #0 共用孔
B = (10.25, -20.2)     # 指片中部销                  #0 与 #10 共用孔
R = (5.05, 9.3)        # 平行连杆根部销（机身）      #10 与 #4 共用孔
TIP = (3.75, -54.3)    # 爪尖内角（合拢态内缘 u=3.75 -> 两指内距 7.5mm）
GEAR_V = 30.0          # 齿轮中心 v（用户卷尺的 0 点）

# ---- 目标实测值 -------------------------------------------------------------
GAP_CLOSED = 7.5       # mm，合拢时两爪尖内距（卷尺照片 0.7cm）
GAP_OPEN = 51.0        # mm，全开时两爪尖内距（照片重新标定读数，用户卷尺曾报 55）
AX_CLOSED = 85.0       # mm，齿轮中心 -> 爪尖（合拢）
AX_OPEN = 70.0         # mm，齿轮中心 -> 爪尖（全开）
TH_MAX = 80.0          # deg，机构锁死前的最大张角（内距在此最大，80° 后开始回缩），emit_gripper 也用它


def rot(p, c, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    dx, dy = p[0] - c[0], p[1] - c[1]
    return (c[0] + dx * ca - dy * sa, c[1] + dx * sa + dy * ca)


def solve(th1, pick_prev=None):
    """给定齿轮臂转角 th1（rad），解四连杆。

    返回 dict: A / B / tip 的坐标，指片转角 rho，连杆转角 phi。
    解不出来返回 None。
    """
    r1 = math.dist(G, A)
    c = math.dist(A, B)
    r2 = math.dist(R, B)

    A1 = rot(A, G, th1)
    # B 满足 |B-A1|=c 且 |B-R|=r2 -> 两圆交点
    d = math.dist(A1, R)
    if d > c + r2 + 1e-9 or d < abs(c - r2) - 1e-9 or d < 1e-9:
        return None
    a = (c * c - r2 * r2 + d * d) / (2 * d)
    h2 = c * c - a * a
    if h2 < 0:
        return None
    h = math.sqrt(h2)
    ux, uy = (R[0] - A1[0]) / d, (R[1] - A1[1]) / d
    base = (A1[0] + a * ux, A1[1] + a * uy)
    cands = [(base[0] + h * -uy, base[1] + h * ux),
             (base[0] - h * -uy, base[1] - h * ux)]
    if pick_prev is None:
        # 取与合拢位 B 同侧的那个解
        B0 = B
        cands.sort(key=lambda p: math.dist(p, B0))
    else:
        cands.sort(key=lambda p: math.dist(p, pick_prev))
    B1 = cands[0]

    # 指片刚体位姿：(A,B) -> (A1,B1)
    rho = math.atan2(B1[1] - A1[1], B1[0] - A1[0]) - math.atan2(B[1] - A[1], B[0] - A[0])
    rho = (rho + math.pi) % (2 * math.pi) - math.pi
    # 连杆转角
    phi = math.atan2(B1[1] - R[1], B1[0] - R[0]) - math.atan2(B[1] - R[1], B[0] - R[0])
    phi = (phi + math.pi) % (2 * math.pi) - math.pi
    tip1 = rot((TIP[0] - A[0], TIP[1] - A[1]), (0, 0), rho)
    tip1 = (A1[0] + tip1[0], A1[1] + tip1[1])
    # rho 是**绝对**转角；URDF 里 finger 关节的父杆是齿轮臂（已转 th1），
    # 所以关节值应是相对角 rho - th1。phi 的父杆是机身，绝对角即关节值。
    return dict(th1=th1, A=A1, B=B1, tip=tip1, rho=rho, rho_rel=rho - th1, phi=phi)


def report(a):
    r1 = math.dist(G, A); c = math.dist(A, B); r2 = math.dist(R, B); gd = math.dist(G, R)
    print("== 四连杆杆长 (mm) ==")
    print(f"  rocker1  G->A (齿轮臂)   {r1:7.3f}")
    print(f"  coupler  A->B (指片)     {c:7.3f}")
    print(f"  rocker2  R->B (平行连杆) {r2:7.3f}")
    print(f"  ground   G->R (机身)     {gd:7.3f}")
    ss = sorted([r1, c, r2, gd])
    print(f"  最短+最长 {ss[0]+ss[3]:.2f} vs 其余 {ss[1]+ss[2]:.2f} -> "
          f"{'曲柄摇杆' if ss[0]+ss[3] < ss[1]+ss[2] else '双摇杆/非格拉肖夫'}")
    print(f"  最短杆是 {'coupler 指片' if ss[0]==c else ('rocker1' if ss[0]==r1 else '')}"
          f" -> 双摇杆机构，齿轮臂只能摆动 ✓")
    print()

    s0 = solve(0.0)
    print("== 合拢态校验 ==")
    print(f"  爪尖 u={s0['tip'][0]:.2f}  v={s0['tip'][1]:.2f}  内距={2*s0['tip'][0]:.2f}mm"
          f"  齿轮->爪尖={GEAR_V - s0['tip'][1]:.2f}mm   (实测 {GAP_CLOSED} / {AX_CLOSED})")
    print()

    print("== 开合扫描（左指；正角 = 张开）==")
    print(f"{'th1°':>7} {'爪尖u':>7} {'爪尖v':>7} {'内距mm':>8} {'轴向mm':>8} {'指片rho°':>9} {'连杆phi°':>9}")
    target = None
    best = (0.0, 0)
    prev = None
    for i in range(0, 91):
        th = math.radians(i)
        s = solve(th, prev)
        if s is None:
            print(f"  ---- {i}° 处解不出（机构到达极限位置）----")
            break
        prev = s['B']
        gap = 2 * s['tip'][0]
        ax = GEAR_V - s['tip'][1]
        if i % 5 == 0:
            print(f"{i:7d} {s['tip'][0]:7.2f} {s['tip'][1]:7.2f} {gap:8.2f} {ax:8.2f}"
                  f" {math.degrees(s['rho']):9.2f} {math.degrees(s['phi']):9.2f}")
        if gap > best[0]:
            best = (gap, i)
        if target is None and gap >= GAP_OPEN:
            target = (i, s, gap, ax)
    print()
    if target:
        i, s, gap, ax = target
        print(f"== 达到实测全开内距 {GAP_OPEN}mm：th1 = {i}° ==")
        print(f"  内距 {gap:.2f}mm  轴向 {ax:.2f}mm  (实测轴向 {AX_OPEN})")
    else:
        print(f"!! 全角域最大内距 {best[0]:.2f}mm（θ={best[1]}°），达不到 {GAP_OPEN}mm ——")
        print(f"   这套四连杆的天生行程就到这，实测值需另找原因（见 README 校准项）。")

    # S1 行程端点（URDF 的 lim_gear）与 mimic 系数
    th = math.radians(TH_MAX)
    prev = None
    for i in range(int(TH_MAX) + 1):
        s = solve(math.radians(i), prev if i else None)
        prev = s['B']
    print()
    print(f"== URDF 参数（行程取机构锁死角 {TH_MAX}°，此点内距 "
          f"{2*s['tip'][0]:.2f}mm，照片读数 {GAP_OPEN}）==")
    print(f"  lim_gear      = {th:.5f} rad ({TH_MAX}°)")
    print(f"  内距          = {2*s['tip'][0]:.2f} mm")
    print(f"  mimic_finger  = {math.degrees(s['rho_rel'])/TH_MAX:+.5f}"
          f"   (指片相对齿轮臂 {math.degrees(s['rho_rel']):+.2f}°)")
    print(f"  mimic_bar     = {math.degrees(s['phi'])/TH_MAX:+.5f}"
          f"   (平行连杆 {math.degrees(s['phi']):+.2f}°)")


if __name__ == '__main__':
    if '--json' in sys.argv:
        s0 = solve(0.0)
        # 找全开点
        prev, i, s, best = None, 0, s0, None
        for k in range(0, 91):
            t = solve(math.radians(k), prev if k else None)
            if t is None:
                break
            prev = t['B']
            if 2 * t['tip'][0] >= GAP_OPEN:
                i, s = k, t
                best = (k, t)
                break
        if best is None:
            best = (TH_MAX, solve(math.radians(TH_MAX)))
        out = dict(
            links=dict(r1=math.dist(G, A), coupler=math.dist(A, B),
                       r2=math.dist(R, B), ground=math.dist(G, R)),
            closed=dict(gap=2 * s0['tip'][0], axial=GEAR_V - s0['tip'][1]),
            open=dict(th1_deg=best[0], gap=2 * best[1]['tip'][0],
                      axial=GEAR_V - best[1]['tip'][1],
                      rho_deg=math.degrees(best[1]['rho']),
                      phi_deg=math.degrees(best[1]['phi'])),
        )
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        report(None)
