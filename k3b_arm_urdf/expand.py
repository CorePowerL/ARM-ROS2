#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在没装 ROS2 的机器上展开 xacro（Windows 下用）。

装了 ROS2 的机器直接：
    xacro k3b_arm.urdf.xacro > k3b_arm.urdf

这里只是调用同一套 xacro python 库，输出保持一致。
"""
import os
import sys

try:
    import xacro
except ImportError:
    sys.exit("缺少 xacro：pip install xacro")

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "k3b_arm.urdf.xacro")
dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "k3b_arm.urdf")

doc = xacro.process_file(src)
xml = doc.toprettyxml(indent="  ")
xml = "\n".join(line for line in xml.splitlines() if line.strip())

with open(dst, "w", encoding="utf-8") as f:
    f.write(xml + "\n")

print("展开完成:", dst)
