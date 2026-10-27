#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从实测量反解夹爪指片转动量。

输入（用户实测）：
  齿轮中心 -> 爪尖（闭合）   = 85 mm
  腕滚转输出 -> 爪尖          = 110 mm
  两指末端内距（全开）        = 55 mm
CAD 实测（part_claw.stl，claw 系，mm）：
  爪尖 Z = -54.3，爪顶 Z = +54.3，Y 厚 +-11
  指片：左 X -17.9..-1.0，右 X +6.5..+23.4，Z -54.3..+5.0
  对称面 X = +2.75
"""
import math

TIP_Z, TOP_Z = -54.3, 54.3
SYM_X = 2.75
GEAR_Z = TIP_Z + 85.0            # 由「齿轮→爪尖 85mm」反推 = 30.7
# 爪顶(claw Z=+54.3) 落在腕轴上时腕->爪尖 = 108.6，实测 110，故整体再下移 1.4mm
CLAW_ORIGIN_Z = (54.3 - 28.0) + (110.0 - (TOP_Z - TIP_Z))
GAP_CLOSED = 1.0 - (-6.5)        # 左指内缘 +1.0(link) 到右指内缘 -6.5(link)
GAP_OPEN = 55.0

def claw2link(x, z):
    """claw 系 -> gripper_base 系：绕 Y 转 180°，再平移 (0,0,CLAW_ORIGIN_Z)。"""
    return (-x, CLAW_ORIGIN_Z - z)

def solve(pivot_claw, tip_inner_claw, target_inner_claw):
    """绕 pivot 把 tip 转到 target 的 X 位置，返回角度（claw 系绕 +Y，度）。"""
    px, pz = pivot_claw
    vx, vz = tip_inner_claw[0] - px, tip_inner_claw[1] - pz
    r = math.hypot(vx, vz)
    tx = target_inner_claw - px
    if abs(tx) > r:
        raise ValueError('目标超出杆长')
    tz = -math.sqrt(r * r - tx * tx)
    a0, a1 = math.atan2(vz, vx), math.atan2(tz, tx)
    # 归一到 (-180,180]
    d = math.degrees(a1 - a0)
    while d > 180: d -= 360
    while d <= -180: d += 360
    return d, r, (px + tx, pz + tz)

# 指片转轴取在指片自身顶端中心（claw 系）
PIV_L = (-9.45, 5.0)
PIV_R = (14.95, 5.0)
TIP_L = (-1.0, TIP_Z)
TIP_R = (6.5, TIP_Z)

tgt_L = SYM_X - GAP_OPEN / 2      # -24.75
tgt_R = SYM_X + GAP_OPEN / 2      # +30.25

dL, rL, tipL1 = solve(PIV_L, TIP_L, tgt_L)
dR, rR, tipR1 = solve(PIV_R, TIP_R, tgt_R)

print(f'爪长            {TOP_Z - TIP_Z:.1f} mm')
print(f'齿轮中心 claw Z  {GEAR_Z:.1f} mm（爪顶向下一 {TOP_Z - GEAR_Z:.1f}）')
print(f'爪顶到腕轴      {110 - (TOP_Z - TIP_Z):.1f} mm  => claw origin z = {CLAW_ORIGIN_Z:.1f} mm')
print(f'腕轴到齿轮      {110 - 85:.0f} mm（= 110-85）')
print()
print(f'左指 pivot claw {PIV_L}  杆长 {rL:.2f} mm，需转 {dL:+.2f}°')
print(f'右指 pivot claw {PIV_R}  杆长 {rR:.2f} mm，需转 {dR:+.2f}°')
print(f'两指转角比 {dR/dL:+.3f}（mimic multiplier 应该接近 -1）')
print(f'转角 {abs(dL):.2f}° = {math.radians(abs(dL)):.4f} rad')
print()

# 校验：link 系下 pivot / visual origin / 爪尖
pl = claw2link(*PIV_L)
pr = claw2link(*PIV_R)
print(f'左指 pivot link ({pl[0]:+.4f}, 0, {pl[1]:+.4f}) m')
print(f'右指 pivot link ({pr[0]:+.4f}, 0, {pr[1]:+.4f}) m')
print(f'左指 visual origin xyz="{-pl[0]:+.4f} 0 {CLAW_ORIGIN_Z/1000:+.4f}"')
print(f'右指 visual origin xyz="{-pr[0]:+.4f} 0 {CLAW_ORIGIN_Z/1000:+.4f}"')
gz = claw2link(SYM_X, GEAR_Z)
print(f'齿轮中心 link  ({gz[0]:+.4f}, 0, {gz[1]:+.4f}) m')
tp = claw2link(0, TIP_Z)
print(f'爪尖 z(l 从 claw 顶算) = {tp[1]:+.4f} m -> 距腕轴 {(tp[1]+0.028)*1000:.1f} mm')

def tip_after(pivot, tip0, deg):
    px, pz = pivot
    vx, vz = tip0[0]-px, tip0[1]-pz
    a = math.radians(deg)
    return (px + vx*math.cos(a) - vz*math.sin(a), pz + vx*math.sin(a) + vz*math.cos(a))

tl = tip_after(PIV_L, TIP_L, dL)
tr = tip_after(PIV_R, TIP_R, dR)
print(f'闭合 内距 {GAP_CLOSED:.1f} mm   齿轮->爪尖 {math.hypot(TIP_L[0]-SYM_X, TIP_L[1]-GEAR_Z):.1f} mm')
print(f'全开 内距 {tl[0]-tr[0]:.1f} mm   齿轮->爪尖 '
      f'左 {math.hypot(tl[0]-SYM_X, tl[1]-GEAR_Z):.1f} / 右 {math.hypot(tr[0]-SYM_X, tr[1]-GEAR_Z):.1f} mm')
print(f'      左指爪尖 claw ({tl[0]:+.1f}, {tl[1]:+.1f})  右指 ({tr[0]:+.1f}, {tr[1]:+.1f})')
