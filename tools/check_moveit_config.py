#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MoveIt 配置一致性检查
=============================================================================
MoveIt 最气人的地方是：配置写错时**不报错**，只是 RViz 里那个面板莫名其妙
是灰的、或者点规划永远红色、或者点 Execute 毫无反应。所以改完配置先跑这个。

用法（在仓库根目录）：
    python tools/check_moveit_config.py

检查内容
--------
  URDF    robots 名、可动关节、mimic、限位
  SRDF    group 引用的 link/joint 是否存在；chain 是否连通、DoF 是否对得上；
          group_state 的关节是否在组内、值是否超出限位；mimic 是否被误列进组；
          disable_collisions 是否漏掉「必须豁免」的对
  YAML    kinematics / joint_limits / moveit_controllers / ompl 里的关节与组名
  ros2_control xacro  声明的关节是否存在、是否误把 mimic 写进去
  交叉    三个地方的 controller 关节列表必须完全一致

另外会把每个命名位姿做一遍正运动学，打印 tool0 的实际位置 —— 数字明显不对
（比如跑到地面以下、或者 z 是负的）就是位姿写错了。

退出码：0 = 全部通过（可能带警告）；1 = 有错误。
=============================================================================
"""

import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_URDF = os.path.join(ROOT, "k3b_arm_urdf", "k3b_arm.urdf")
P_SRDF = os.path.join(ROOT, "k3b_arm_moveit_config", "config", "k3b_arm.srdf")
P_CFG = os.path.join(ROOT, "k3b_arm_moveit_config", "config")
P_RC = os.path.join(ROOT, "k3b_arm_urdf", "ros2_control", "k3b_arm.ros2_control.xacro")

ERRORS = []
WARNS = []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNS.append(msg)


# =============================================================================
# URDF
# =============================================================================
def load_urdf():
    root = ET.parse(P_URDF).getroot()
    links = {}
    for l in root.findall("link"):
        geom = []
        for c in l.findall("collision"):
            g = c.find("geometry")
            if g is None or len(g) == 0:
                continue
            shape = g[0]
            o = c.find("origin")
            xyz = [float(v) for v in (o.get("xyz") if o is not None else "0 0 0").split()]
            rpy = [float(v) for v in (o.get("rpy") if o is not None else "0 0 0").split()]
            if shape.tag == "box":
                half = np.array([float(v) for v in shape.get("size").split()]) / 2.0
            elif shape.tag == "cylinder":
                r = float(shape.get("radius"))
                h = float(shape.get("length")) / 2.0
                half = np.array([r, r, h])
            elif shape.tag == "sphere":
                r = float(shape.get("radius"))
                half = np.array([r, r, r])
            else:
                continue
            geom.append(dict(kind=shape.tag, xyz=xyz, rpy=rpy, half=half))
        links[l.get("name")] = dict(geom=geom)

    joints = {}
    for j in root.findall("joint"):
        lim = j.find("limit")
        mimic = j.find("mimic")
        joints[j.get("name")] = dict(
            type=j.get("type"),
            parent=j.find("parent").get("link"),
            child=j.find("child").get("link"),
            origin=np.array(
                [float(v) for v in ((j.find("origin").get("xyz")) if j.find("origin") is not None else "0 0 0").split()]
            ),
            rpy=[
                float(v)
                for v in ((j.find("origin").get("rpy")) if j.find("origin") is not None else "0 0 0").split()
            ],
            axis=[
                float(v)
                for v in (
                    (j.find("axis").get("xyz")) if j.find("axis") is not None else "0 0 0"
                ).split()
            ],
            limit=(
                dict(
                    lower=float(lim.get("lower", 0.0)),
                    upper=float(lim.get("upper", 0.0)),
                    velocity=float(lim.get("velocity", 0.0)),
                    effort=float(lim.get("effort", 0.0)),
                )
                if lim is not None
                else None
            ),
            mimic=(
                dict(
                    joint=mimic.get("joint"),
                    multiplier=float(mimic.get("multiplier", 1.0)),
                    offset=float(mimic.get("offset", 0.0)),
                )
                if mimic is not None
                else None
            ),
        )
    return root.get("name"), links, joints


def active_joints(joints):
    """能被控制器驱动的关节：可动、且不是 mimic"""
    return {
        n: j
        for n, j in joints.items()
        if j["type"] in ("revolute", "continuous", "prismatic") and j["mimic"] is None
    }


def mimic_joints(joints):
    return {n: j for n, j in joints.items() if j["mimic"] is not None}


def path_joints(joints, base, tip):
    """base -> tip 之间的关节序列（不含无关分支），失败返回 None"""
    child_to_joint = {j["child"]: (n, j) for n, j in joints.items()}
    chain = []
    cur = tip
    guard = 0
    while cur != base:
        guard += 1
        if guard > 200 or cur not in child_to_joint:
            return None
        n, j = child_to_joint[cur]
        chain.append((n, j))
        cur = j["parent"]
    chain.reverse()
    return chain


def descendants(joints, root_link):
    """root_link 及其全部后代 link"""
    out = {root_link}
    changed = True
    while changed:
        changed = False
        for j in joints.values():
            if j["parent"] in out and j["child"] not in out:
                out.add(j["child"])
                changed = True
    return out


# =============================================================================
# 正运动学（只用来打印命名位姿的末端位置，不参与判定）
# =============================================================================
def rpy_to_R(rpy):
    cr, sr = math.cos(rpy[0]), math.sin(rpy[0])
    cp, sp = math.cos(rpy[1]), math.sin(rpy[1])
    cy, sy = math.cos(rpy[2]), math.sin(rpy[2])
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ]
    )


def axis_rot(axis, th):
    a = np.array(axis, dtype=float)
    n = np.linalg.norm(a)
    if n == 0:
        return np.eye(3)
    a = a / n
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def fk(chain, qmap):
    p = np.zeros(3)
    R = np.eye(3)
    for name, j in chain:
        p = p + R @ j["origin"]
        R = R @ rpy_to_R(j["rpy"])
        if j["type"] in ("revolute", "continuous", "prismatic"):
            v = qmap.get(name, 0.0)
            if j["type"] == "prismatic":
                p = p + R @ (np.array(j["axis"], float) * v)
            else:
                R = R @ axis_rot(j["axis"], v)
    return p, R


# =============================================================================
# 主流程
# =============================================================================
def main():
    robot_name, links, joints = load_urdf()
    act = active_joints(joints)
    mim = mimic_joints(joints)

    print("=" * 74)
    print("URDF: %s" % os.path.relpath(P_URDF, ROOT))
    print("  link %d 个，joint %d 个（可动 %d / 主动 %d / mimic %d）"
          % (len(links), len(joints),
             sum(1 for j in joints.values() if j["type"] != "fixed"), len(act), len(mim)))
    print("  主动关节: %s" % ", ".join(act))
    print("=" * 74)

    if not os.path.exists(P_SRDF):
        err("找不到 SRDF: %s" % P_SRDF)
        return report()
    if not os.path.exists(P_RC):
        err("找不到 ros2_control xacro: %s" % P_RC)
        return report()

    srdf = ET.parse(P_SRDF).getroot()
    if srdf.get("name") != robot_name:
        warn("SRDF 的 robot name='%s' 与 URDF 的 '%s' 不一致（MoveIt 不强制，但保持一"
             "致省得以后排查）" % (srdf.get("name"), robot_name))

    groups = {}
    for g in srdf.findall("group"):
        name = g.get("name")
        info = dict(chain=None, joints=[], links=[])
        ch = g.find("chain")
        if ch is not None:
            info["chain"] = (ch.get("base_link"), ch.get("tip_link"))
        for j in g.findall("joint"):
            info["joints"].append(j.get("name"))
        for l in g.findall("link"):
            info["links"].append(l.get("name"))
        groups[name] = info

        # --- group 内容校验 ---
        if info["chain"]:
            b, t = info["chain"]
            if b not in links:
                err("group '%s' 的 chain base_link '%s' 不存在" % (name, b))
            elif t not in links:
                err("group '%s' 的 chain tip_link '%s' 不存在" % (name, t))
            else:
                ch_j = path_joints(joints, b, t)
                if ch_j is None:
                    err("group '%s' 的 chain 不连通：%s → %s" % (name, b, t))
                else:
                    dof = sum(1 for _, j in ch_j if j["type"] != "fixed")
                    info["dof"] = dof
                    info["active"] = [n for n, j in ch_j
                                      if j["type"] != "fixed" and j["mimic"] is None]
                    info["mimic"] = [n for n, j in ch_j if j["mimic"] is not None]
        for jn in info["joints"]:
            if jn not in joints:
                err("group '%s' 引用了不存在的 joint '%s'" % (name, jn))
            elif jn in mim:
                err("group '%s' 把 mimic 关节 '%s' 列进去了 —— MoveIt 会拒绝"
                    % (name, jn))
        if not info["chain"] and info["joints"]:
            info["dof"] = len(info["joints"])
            info["active"] = [j for j in info["joints"] if j in act]
            info["mimic"] = []

    # --- group_state ---
    print("\n命名位姿（已做正运动学校核）")
    print("-" * 74)
    for gs in srdf.findall("group_state"):
        gname = gs.get("group")
        sname = gs.get("name")
        if gname not in groups:
            err("group_state '%s' 指向不存在的 group '%s'" % (sname, gname))
            continue
        qmap = {}
        bad = False
        for j in gs.findall("joint"):
            jn, val = j.get("name"), float(j.get("value"))
            if jn not in joints:
                err("group_state '%s/%s' 引用了不存在的 joint '%s'" % (gname, sname, jn))
                bad = True
                continue
            in_group = (jn in groups[gname].get("active", [])
                        or jn in groups[gname].get("joints", []))
            if not in_group:
                err("group_state '%s/%s' 的关节 '%s' 不在该组里" % (gname, sname, jn))
                bad = True
            lim = joints[jn]["limit"]
            if lim is not None and joints[jn]["type"] == "revolute":
                if not (lim["lower"] - 1e-9 <= val <= lim["upper"] + 1e-9):
                    err("group_state '%s/%s' 的 '%s'=%.4f rad 超出限位 [%.4f, %.4f]"
                        % (gname, sname, jn, val, lim["lower"], lim["upper"]))
                    bad = True
            qmap[jn] = val
        if bad:
            continue
        # 位姿没覆盖组内全部主动关节时 MoveIt 会用 0 补齐 —— 不报错，
        # 但选这个位姿手臂会突然"归零到某个轴上"，很难查
        unset = [jn for jn in groups[gname].get("active", []) if jn not in qmap]
        if unset:
            warn("group_state '%s/%s' 没写 %s，MoveIt 会用 0 补齐"
                 % (gname, sname, ", ".join(unset)))
        ch = groups[gname]["chain"]
        if ch and ch[0] in links and ch[1] in links:
            chain = path_joints(joints, *ch)
            if chain:
                p, R = fk(chain, qmap)
                print("  %-10s %-10s tool0 = (%7.1f, %7.1f, %7.1f) mm   工具轴 z = %s"
                      % (gname, sname, p[0] * 1000, p[1] * 1000, p[2] * 1000,
                         np.array2string(np.round(R[:, 2], 2), separator=",")))
                if p[2] < 0:
                    err("group_state '%s/%s' 的末端 z=%.1fmm 在地面以下"
                        % (gname, sname, p[2] * 1000))
        else:
            print("  %-10s %-10s 非 chain 组，跳过 FK" % (gname, sname))

    # --- end_effector ---
    for ee in srdf.findall("end_effector"):
        ename, plink, eg = ee.get("name"), ee.get("parent_link"), ee.get("group")
        if plink and plink not in links:
            err("end_effector '%s' 的 parent_link '%s' 不存在" % (ename, plink))
        if eg and eg not in groups:
            err("end_effector '%s' 的 group '%s' 不在 SRDF 里" % (ename, eg))
        if eg in groups and plink:
            owners = {joints[jn]["parent"] for jn in groups[eg].get("active", [])
                      if jn in joints}
            if owners and plink not in owners:
                warn("end_effector '%s' 的 parent_link 是 '%s'，但 group '%s' 的关节挂在 "
                     "%s 上 —— 抓取生成时 ik 链可能接不上"
                     % (ename, plink, eg, "/".join(sorted(owners))))

    # --- disable_collisions ---
    disabled = set()
    for dc in srdf.findall("disable_collisions"):
        a, b = dc.get("link1"), dc.get("link2")
        if a not in links:
            err("disable_collisions 引用了不存在的 link '%s'" % a)
        if b not in links:
            err("disable_collisions 引用了不存在的 link '%s'" % b)
        key = tuple(sorted((a, b)))
        if key in disabled:
            warn("disable_collisions 重复：%s ↔ %s" % (a, b))
        disabled.add(key)

    # 1) URDF 里所有直接父子对（两端都有碰撞体）必须豁免
    need = []
    for n, j in joints.items():
        a, b = j["parent"], j["child"]
        if links.get(a, {}).get("geom") and links.get(b, {}).get("geom"):
            need.append(tuple(sorted((a, b))))
    missing = [p for p in need if p not in disabled]
    for a, b in missing:
        err("父子对 %s ↔ %s 没有 disable_collisions —— 这两个 link 在任意位姿下都"
            "贴着，不豁免会让每次规划都报碰撞" % (a, b))

    # 2) 夹爪内部（gripper_base_link 的所有后代）两两必须豁免。
    #    夹爪是铰接装配体，内部本来就要允许接触；不豁免的话张开时必然自撞。
    if "gripper_base_link" in links:
        claw = descendants(joints, "gripper_base_link")
        claw_geom = sorted(x for x in claw if links.get(x, {}).get("geom"))
        claw_missing = []
        for i in range(len(claw_geom)):
            for k in range(i + 1, len(claw_geom)):
                if tuple(sorted((claw_geom[i], claw_geom[k]))) not in disabled:
                    claw_missing.append((claw_geom[i], claw_geom[k]))
        for a, b in claw_missing:
            err("夹爪内部 %s ↔ %s 没有豁免 —— 张开时会自碰撞" % (a, b))
        print("\n夹爪内部 %d 个带碰撞体的 link，两两 %d 对已全部豁免"
              % (len(claw_geom), len(claw_geom) * (len(claw_geom) - 1) // 2)
              if not claw_missing else "")

    # =========================================================================
    # YAML
    # =========================================================================
    def load_yaml(name, required=True):
        p = os.path.join(P_CFG, name)
        if not os.path.exists(p):
            if required:
                err("缺少配置文件 %s" % name)
            return {}
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    kin = load_yaml("kinematics.yaml")
    jl = load_yaml("joint_limits.yaml")
    mctrl = load_yaml("moveit_controllers.yaml")
    ompl = load_yaml("ompl_planning.yaml")

    # kinematics
    for gname in groups:
        if gname not in kin:
            warn("kinematics.yaml 里没有 group '%s'（MoveIt 会刷警告）" % gname)
    for gname in kin:
        if gname not in groups:
            warn("kinematics.yaml 里的 '%s' 不是 SRDF 中的 group" % gname)
        else:
            solver = (kin[gname] or {}).get("kinematics_solver")
            if not solver:
                err("kinematics.yaml 的 '%s' 缺 kinematics_solver" % gname)

    # joint_limits
    jl_joints = (jl.get("joint_limits") or {})
    for jn in jl_joints:
        if jn not in joints:
            err("joint_limits.yaml 里的 '%s' 不存在于 URDF" % jn)
        elif jn in mim:
            warn("joint_limits.yaml 给 mimic 关节 '%s' 设了限制 —— 它不参与规划，"
                 "写了也没用" % jn)
    for gname, g in groups.items():
        for jn in g.get("active", []):
            if jn not in jl_joints:
                warn("joint_limits.yaml 缺 '%s'（属于 group '%s'）—— MoveIt 会用"
                     "默认速度，可能快得离谱" % (jn, gname))
            elif not (jl_joints[jn] or {}).get("has_velocity_limits"):
                warn("'%s' 没有 has_velocity_limits" % jn)

    # moveit_controllers
    mcm = mctrl.get("moveit_simple_controller_manager") or {}
    ctrl_names = mcm.get("controller_names") or []
    ctrl_joints = {}
    for cn in ctrl_names:
        body = mcm.get(cn) or {}
        js = body.get("joints") or []
        ctrl_joints[cn] = js
        for jn in js:
            if jn not in joints:
                err("moveit_controllers.yaml 的 '%s' 引用了不存在的关节 '%s'" % (cn, jn))
            elif jn in mim:
                err("moveit_controllers.yaml 的 '%s' 里写了 mimic 关节 '%s' —— "
                    "控制器只驱动主动关节" % (cn, jn))
        if not body.get("type"):
            err("moveit_controllers.yaml 的 '%s' 缺 type" % cn)
    for gname, g in groups.items():
        ga = sorted(g.get("active", []))
        matched = None
        for cn, js in ctrl_joints.items():
            if sorted(js) == ga:
                matched = cn
                break
        if matched is None:
            err("group '%s' 的主动关节 %s 找不到关节列表完全一致的 controller —— "
                "点 Execute 会报 no controller found（现有：%s）"
                % (gname, ga, {k: sorted(v) for k, v in ctrl_joints.items()}))

    # ompl
    planning_plugins = ompl.get("planning_plugins") or (
        [ompl["planning_plugin"]] if "planning_plugin" in ompl else []
    )
    if not planning_plugins:
        warn("ompl_planning.yaml 没有 planning_plugins（Jazzy 用复数键）")
    for gname in groups:
        if gname not in ompl:
            warn("ompl_planning.yaml 里没有 group '%s'" % gname)

    # =========================================================================
    # ros2_control
    # =========================================================================
    rc = ET.parse(P_RC).getroot()
    rc_joints = []
    for j in rc.iter("joint"):
        nm = j.get("name")
        if nm is None:
            continue
        rc_joints.append(nm)
        if nm not in joints:
            err("ros2_control 声明的关节 '%s' 不存在于 URDF" % nm)
        elif nm in mim:
            err("ros2_control 声明了 mimic 关节 '%s' —— ros2_control 不认 <mimic>，"
                "它和主动关节指令会打架" % nm)
        if j.find("command_interface[@name='position']") is None:
            warn("ros2_control 的 '%s' 没有 position 命令接口" % nm)
    for cn, js in ctrl_joints.items():
        for jn in js:
            if jn not in rc_joints:
                err("controller '%s' 要驱动 '%s'，但 ros2_control 里没声明这个关节"
                    % (cn, jn))
    for jn in rc_joints:
        if jn not in [x for js in ctrl_joints.values() for x in js]:
            warn("ros2_control 声明了 '%s'，但没有 controller 驱动它" % jn)

    return report()


def report():
    print("\n" + "=" * 74)
    if WARNS:
        print("警告 %d 条：" % len(WARNS))
        for w in WARNS:
            print("  ! " + w)
    if ERRORS:
        print("错误 %d 条：" % len(ERRORS))
        for e in ERRORS:
            print("  x " + e)
        print("\n结果：不通过")
        return 1
    print("结果：全部通过 ✓" + ("（有 %d 条警告）" % len(WARNS) if WARNS else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
