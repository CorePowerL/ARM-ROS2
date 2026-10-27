#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 tools/claw_4bar.py 反解出的四连杆参数写进 k3b_arm.urdf.xacro 的夹爪段。

只做两件事：
  1. 替换「夹爪参数」属性块
  2. 替换「夹爪」link/joint 块（机身 + 4 杆 + 2 指 + 2 连杆根，全部 revolute + mimic）

坐标约定（为了整臂左右对称、tool0 落在对称面上）：
    claw 网格系 (Xc, Yc, Zc)  --rpy "0 π 0"-->  gripper_base 系 (Xg, Yg, Zg)
    Xg = claw_x - Xc,  Zg = claw_z - Zc,  claw_x = 2.75mm, claw_z = 27.7mm
    于是 claw 的对称面 Xc=2.75 正好落在 Xg=0。

用法: python tools/emit_gripper.py [--write]
"""

import io
import os
import math
import sys

import claw_4bar as M

CLAW_X = 0.00275          # m，claw 网格对称面
CLAW_Z = 0.0277           # m，claw 网格原点 -> gripper_base
TH_MAX = M.TH_MAX        # deg，机构最大张角（内距在此最大），与 claw_4bar 保持同一来源


def _fit(pts, key):
    """mimic 系数 = 端点值 / 端点角。

    URDF 的 <mimic> 只能线性，而四连杆是三次曲线，中段必然有残差。
    取「端点精确」而不是最小二乘：夹爪只有合拢/张开两个姿态需要与实测对齐，
    中段姿态肉眼不可辨。端点精确后 55° 处的开度/轴向与反解完全一致。
    """
    th_max, p_max = pts[-1]
    return math.degrees(p_max[key]) / th_max


def _scan():
    prev, pts = None, []
    for i in range(int(TH_MAX) + 1):
        s = M.solve(math.radians(i), prev if i else None)
        prev = s['B']
        pts.append((i, s))
    return pts


_PTS = _scan()
# finger 关节的父杆是齿轮臂（已转 th1），关节值 = 相对角 rho-th1
MIMIC_F = _fit(_PTS, 'rho_rel')
# bar 关节的父杆是机身，关节值 = 绝对角 phi
MIMIC_B = _fit(_PTS, 'phi')

# 孔位（半侧 u = 到对称面距离, v = claw Z），m
GEAR = (M.G[0] / 1000, M.G[1] / 1000)
BAR = (M.R[0] / 1000, M.R[1] / 1000)
A_OFF = ((M.A[0] - M.G[0]) / 1000, -(M.A[1] - M.G[1]) / 1000)   # A 相对齿轮轴
# claw 网格里各零件的 (u, v) 原点，用于算 visual 偏移
V_GEAR = M.G[1] / 1000
V_BAR = M.R[1] / 1000
V_A = M.A[1] / 1000


def mm(x):
    return f"{x:.5f}"


def props_xml():
    return f"""  <!-- ===== 夹爪：真四连杆（孔位反解，见 tools/claw_4bar.py） =====
       part_claw.stl 的 21 个连通分件按「孔位共点」关系，确定是一条四连杆链：

           机身 ──G── 齿轮臂 ──A── 指片 ──B── 平行连杆 ──R── 机身
          (ground)  rocker1   coupler   rocker2        (ground)
          杆长 30.0          21.0        30.0          22.3  mm

       S1 输出轴带一只齿轮扇形板，与另一只扇形板啮合，两者转向相反 ——
       所以左右两指严格镜像；右指全部 mimic 左指，轴取 (0 -1 0)。

       本块所有坐标都在 gripper_base 系，对称面 = X=0、爪轴 = +Z
       （claw 网格 Xc=2.75 / Zc=+27.7 映射到原点，见 claw_x / claw_z）。 -->
  <xacro:property name="claw_x" value="{mm(CLAW_X)}"/>   <!-- claw 网格对称面 -->
  <xacro:property name="claw_z" value="{mm(CLAW_Z)}"/>   <!-- claw 网格 -> gripper_base -->

  <!-- G 齿轮轴心 -->
  <xacro:property name="gear_u" value="{mm(GEAR[0])}"/>
  <xacro:property name="gear_z" value="{mm(CLAW_Z - GEAR[1])}"/>
  <xacro:property name="gear_v" value="{mm(GEAR[1])}"/>
  <!-- R 平行连杆根部销 -->
  <xacro:property name="bar_u"  value="{mm(BAR[0])}"/>
  <xacro:property name="bar_z"  value="{mm(CLAW_Z - BAR[1])}"/>
  <xacro:property name="bar_v"  value="{mm(BAR[1])}"/>
  <!-- A 指根销（相对齿轮轴） -->
  <xacro:property name="pa_u"   value="{mm(A_OFF[0])}"/>
  <xacro:property name="pa_z"   value="{mm(A_OFF[1])}"/>
  <xacro:property name="pa_v"   value="{mm(V_A)}"/>

  <!-- S1：输出轴落在齿轮轴心上，机身向 +Y 外挂 -->
  <xacro:property name="s1_x" value="{mm(-GEAR[0] - 0.01003)}"/>
  <xacro:property name="s1_y" value="0.012"/>

  <!-- 行程：齿轮臂 0~80°。80° 是机构锁死角（内距最大 47.1mm，再大就回缩），
       所以 URDF 允许走满全行程，S1 的实际脉宽子区间由实机标定后再收窄。 -->
  <xacro:property name="lim_gear" value="{mm(math.radians(TH_MAX))}"/>
  <!-- 从动件 mimic 系数：按 55° 端点匹配（URDF mimic 只能线性，中段为近似） -->
  <xacro:property name="mimic_finger" value="{MIMIC_F:.5f}"/>
  <xacro:property name="mimic_bar"    value="{MIMIC_B:.5f}"/>
  <!-- 各杆碰撞盒（粗） -->
  <xacro:property name="finger_half_w" value="0.00845"/>
  <xacro:property name="finger_len" value="0.0593"/>
"""


def limbs_xml():
    L = []
    a = L.append
    a("  <!-- ================= 夹爪机身（固定，含 S1） ================= -->")
    a("  <link name=\"gripper_base_link\">")
    a("    <!-- S1：输出轴对准齿轮轴心，机身从爪体 +Y 面外挂 -->")
    a("    <visual>")
    a("      <geometry><mesh filename=\"${mesh_dir}s20f.stl\"/></geometry>")
    a("      <origin xyz=\"${s1_x} ${s1_y} ${gear_z}\" rpy=\"${pi/2} 0 0\"/>")
    a("      <material name=\"servo_mat\"/>")
    a("    </visual>")
    a("    <!-- 机械爪壳体：背板 + 舵机支架 + 垫块（齿轮扇形板与连杆已拆成独立杆件） -->")
    a("    <visual>")
    a("      <geometry><mesh filename=\"${mesh_dir}claw_body.stl\"/></geometry>")
    a("      <origin xyz=\"${claw_x} 0 ${claw_z}\" rpy=\"0 ${pi} 0\"/>")
    a("      <material name=\"metal_mat\"/>")
    a("    </visual>")
    a("    <collision>")
    a("      <geometry><box size=\"0.060 0.024 0.050\"/></geometry>")
    a("      <origin xyz=\"0 0 0.025\" rpy=\"0 0 0\"/>")
    a("    </collision>")
    a("    <inertial>")
    a("      <mass value=\"0.12\"/>")
    a("      <inertia ixx=\"0.0001\" ixy=\"0.0\" ixz=\"0.0\" iyy=\"0.0001\" iyz=\"0.0\" izz=\"0.0001\"/>")
    a("    </inertial>")
    a("  </link>")
    a("  <joint name=\"gripper_base_joint\" type=\"fixed\">")
    a("    <parent link=\"wrist_roll_link\"/>")
    a("    <child link=\"gripper_base_link\"/>")
    a("    <origin xyz=\"0 0 0.028\" rpy=\"0 0 0\"/>")
    a("  </joint>")
    a("")
    a("  <!-- 末端工具坐标系：两爪尖正中间 -->")
    a("  <link name=\"tool0\"/>")
    a("  <joint name=\"tool0_joint\" type=\"fixed\">")
    a("    <parent link=\"gripper_base_link\"/>")
    a("    <child link=\"tool0\"/>")
    a("    <origin xyz=\"0 0 0.082\" rpy=\"0 0 0\"/>")
    a("  </joint>")

    for side in ("left", "right"):
        zh = "左" if side == "left" else "右"
        sg = 1.0 if side == "left" else -1.0
        # 关节 X 取 ±u；右指用 axis (0 -1 0) 做镜像
        gx = mm(sg * GEAR[0])
        bx = mm(sg * BAR[0])
        axx = mm(sg * A_OFF[0])
        # visual 原点（link 系）= claw_x - 该杆的关节 X
        vis_g = mm(CLAW_X - sg * GEAR[0])
        vis_b = mm(CLAW_X - sg * BAR[0])
        vis_f = mm(CLAW_X - sg * (GEAR[0] + A_OFF[0]))
        axis = "0 1 0" if side == "left" else "0 -1 0"

        a("")
        a(f"  <!-- ================= {zh}齿轮扇形板（S1 侧 / 啮合侧） ================= -->")
        if side == "left":
            a("  <!-- 输入杆：S1 直接驱动。正向 = 张开（逆时针） -->")
        else:
            a("  <!-- 与左齿轮啮合，转向相反 -> axis 取 -Y，mimic 系数 +1 即为镜像 -->")
        a(f"  <link name=\"finger_{side}_gear_link\">")
        a("    <visual>")
        a(f"      <geometry><mesh filename=\"${{mesh_dir}}claw_gear_{side}.stl\"/></geometry>")
        a(f"      <origin xyz=\"{vis_g} 0 ${{gear_v}}\" rpy=\"0 ${{pi}} 0\"/>")
        a("      <material name=\"metal_mat\"/>")
        a("    </visual>")
        a("    <collision>")
        a("      <geometry><box size=\"0.028 0.006 0.050\"/></geometry>")
        a("      <origin xyz=\"0 0 0.015\" rpy=\"0 0 0\"/>")
        a("    </collision>")
        a("    <inertial>")
        a("      <mass value=\"0.03\"/>")
        a("      <inertia ixx=\"0.00001\" ixy=\"0.0\" ixz=\"0.0\" iyy=\"0.00001\" iyz=\"0.0\" izz=\"0.00001\"/>")
        a("    </inertial>")
        a("  </link>")
        a(f"  <joint name=\"finger_{side}_gear_joint\" type=\"revolute\">")
        a("    <parent link=\"gripper_base_link\"/>")
        a(f"    <child link=\"finger_{side}_gear_link\"/>")
        a(f"    <origin xyz=\"{gx} 0 ${{gear_z}}\" rpy=\"0 0 0\"/>")
        a(f"    <axis xyz=\"{axis}\"/>")
        if side == "left":
            a("    <limit lower=\"0\" upper=\"${lim_gear}\" effort=\"12.0\" velocity=\"2.0\"/>")
        else:
            a("    <limit lower=\"0\" upper=\"${lim_gear}\" effort=\"12.0\" velocity=\"2.0\"/>")
            a("    <mimic joint=\"finger_left_gear_joint\" multiplier=\"1\" offset=\"0\"/>")
        a("    <dynamics damping=\"0.5\" friction=\"0.1\"/>")
        a("  </joint>")

        a("")
        a(f"  <!-- ================= {zh}指片（连杆 coupler） ================= -->")
        a(f"  <link name=\"finger_{side}_link\">")
        a("    <visual>")
        a(f"      <geometry><mesh filename=\"${{mesh_dir}}claw_finger_{side}.stl\"/></geometry>")
        a(f"      <origin xyz=\"{vis_f} 0 ${{pa_v}}\" rpy=\"0 ${{pi}} 0\"/>")
        a("      <material name=\"link_mat\"/>")
        a("    </visual>")
        a("    <collision>")
        a(f"      <geometry><box size=\"${{finger_half_w*2}} 0.005 ${{finger_len}}\"/></geometry>")
        a("      <origin xyz=\"-0.0035 -0.0015 0.0247\" rpy=\"0 0 0\"/>")
        a("    </collision>")
        a("    <inertial>")
        a("      <mass value=\"0.03\"/>")
        a("      <inertia ixx=\"0.00002\" ixy=\"0.0\" ixz=\"0.0\" iyy=\"0.00002\" iyz=\"0.0\" izz=\"0.00001\"/>")
        a("    </inertial>")
        a("  </link>")
        a(f"  <joint name=\"finger_{side}_joint\" type=\"revolute\">")
        a(f"    <parent link=\"finger_{side}_gear_link\"/>")
        a(f"    <child link=\"finger_{side}_link\"/>")
        a(f"    <origin xyz=\"{axx} 0 ${{pa_z}}\" rpy=\"0 0 0\"/>")
        a(f"    <axis xyz=\"{axis}\"/>")
        a("    <limit lower=\"${mimic_finger*lim_gear}\" upper=\"0\" effort=\"8.0\" velocity=\"1.5\"/>")
        a("    <mimic joint=\"finger_left_gear_joint\" "
          f"multiplier=\"${{mimic_finger}}\" offset=\"0\"/>")
        a("    <dynamics damping=\"1.0\" friction=\"0.2\"/>")
        a("  </joint>")

        a("")
        a(f"  <!-- ================= {zh}平行连杆（rocker2） ================= -->")
        a(f"  <link name=\"finger_{side}_bar_link\">")
        a("    <visual>")
        a(f"      <geometry><mesh filename=\"${{mesh_dir}}claw_bar_{side}.stl\"/></geometry>")
        a(f"      <origin xyz=\"{vis_b} 0 ${{bar_v}}\" rpy=\"0 ${{pi}} 0\"/>")
        a("      <material name=\"metal_mat\"/>")
        a("    </visual>")
        a("    <collision>")
        a("      <geometry><box size=\"0.010 0.011 0.030\"/></geometry>")
        a("      <origin xyz=\"-0.0026 0 -0.0052\" rpy=\"0 0 0\"/>")
        a("    </collision>")
        a("    <inertial>")
        a("      <mass value=\"0.015\"/>")
        a("      <inertia ixx=\"0.000005\" ixy=\"0.0\" ixz=\"0.0\" iyy=\"0.000005\" iyz=\"0.0\" izz=\"0.000005\"/>")
        a("    </inertial>")
        a(f"  </link>")
        a(f"  <joint name=\"finger_{side}_bar_joint\" type=\"revolute\">")
        a("    <parent link=\"gripper_base_link\"/>")
        a(f"    <child link=\"finger_{side}_bar_link\"/>")
        a(f"    <origin xyz=\"{bx} 0 ${{bar_z}}\" rpy=\"0 0 0\"/>")
        a(f"    <axis xyz=\"{axis}\"/>")
        a("    <limit lower=\"0\" upper=\"${mimic_bar*lim_gear}\" effort=\"8.0\" velocity=\"1.5\"/>")
        a("    <mimic joint=\"finger_left_gear_joint\" "
          f"multiplier=\"${{mimic_bar}}\" offset=\"0\"/>")
        a("    <dynamics damping=\"1.0\" friction=\"0.2\"/>")
        a("  </joint>")
    return "\n".join(L) + "\n"


def main():
    write = "--write" in sys.argv
    # 相对仓库根定位，cwd 在哪都能跑
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "k3b_arm_urdf", "k3b_arm.urdf.xacro")
    s = io.open(p, encoding="utf-8").read()

    def idx(*cands):
        for c in cands:
            k = s.find(c)
            if k >= 0:
                return k
        raise ValueError("找不到锚点: " + " / ".join(cands))

    # 幂等：老版本与本脚本都认
    i0 = idx("  <!-- ===== 夹爪")
    i1 = s.index("  <!-- ================= 网格 ================= -->")
    j0 = idx("  <!-- ================= 夹爪机身",
             "  <!-- ================= 夹爪 ================= -->")
    j1 = s.index("  <!-- ================= 世界坐标系 ================= -->")
    assert i0 < i1 < j0 < j1, f"锚点顺序异常 {i0} {i1} {j0} {j1}"

    new = s[:i0] + props_xml() + "\n" + s[i1:j0] + limbs_xml() + "\n" + s[j1:]
    if not write:
        print("=== 属性块 ===")
        print(props_xml())
        print("=== 杆件块（前 40 行）===")
        print("\n".join(limbs_xml().splitlines()[:40]))
        print("...")
        return
    io.open(p, "w", encoding="utf-8").write(new)
    print("已写入", p)


if __name__ == "__main__":
    main()
