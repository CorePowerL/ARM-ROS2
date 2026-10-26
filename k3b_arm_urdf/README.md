# K3B 机械臂 URDF

依据淘宝在售「6 自由度舵机机械臂 DIY 套件」实物结构 + 各舵机厂商三维图建模。

## 执行器映射（实测 2026-10-25）

| 舵机 | 型号 | 类型 | 脉宽范围(μs) | 上电初始 | URDF 关节 | 作用 | 限位(相对直立位) |
|---|---|---|---|---|---|---|---|
| S1 | S20F | 180° 位置 | 850–1500 | 850 | `finger_left_joint` | 夹爪开合 | 0 ~ 58.5° |
| S2 | S20F | 180° 位置 | 500–2500 | 1500 | `base_yaw` | 底座偏航 | ±90° |
| S3 | S20F | 270° 位置 | 500–2000 | 2000 | `shoulder_pitch` | 肩俯仰 | ±101° |
| S4 | S20F | 270° 位置 | 500–2500 | 500 | `elbow_pitch` | 肘俯仰 | ±135° |
| S5 | PM15S | 270° 位置 | 600–2500 | 1500 | `wrist_pitch` | 腕俯仰 | ±128° |
| — | DS3120 | 360° 连续 | — | — | `wrist_roll` | 夹爪旋转 | 无限位(continuous) |

- `finger_right_joint` 通过 `<mimic joint="finger_left_joint" multiplier="-1"/>` 跟随左指，不单独接舵机。
- `wrist_roll` 是速度舵机，无位置反馈，URDF 中为 `continuous`，**MoveIt 规划时要 disable 该关节**。
- **S5（PM15S）三维图暂缺**，当前以其 S20F 270° 版代替，待实测后替换网格与限位。

## 关节结构

| 关节名 | 类型 | 轴 | 舵机 | 说明 |
|---|---|---|---|---|
| `base_yaw` | revolute | Z | S2 | 底座偏航 |
| `shoulder_pitch` | revolute | Y | S3 | 肩俯仰 |
| `elbow_pitch` | revolute | Y | S4 | 肘俯仰 |
| `wrist_pitch` | revolute | Y | S5 | 腕俯仰 |
| `wrist_roll` | continuous | Z | DS3120 | 夹爪旋转，控速不控位 |
| `finger_left_joint` | revolute | Y | S1 | 夹爪开合驱动 |
| `finger_right_joint` | revolute | Y | (mimic) | 夹爪右指，跟随左指 |

末端工具坐标系：`tool0`。

**全关节为 0 = 直臂垂直**，上表限位均相对该位姿定义。

## 网格清单

`meshes/` 下是厂商三维图转出来的 STL（米制），全部已按关节轴/装配基准对齐：

### 舵机

| 文件 | 来源 | 面数 | 对齐方式 |
|---|---|---|---|
| `s20f.stl` | `舵机WHEELTECS20F/舵机_S20F.stp` | 2,678 | 输出轴 +Z、轴心在原点，机身沿 −Z |
| `ds3120.stl` | `最新三维图/DS3120 20kg.stp`（剔除支架/舵盘/线套） | 37,078 | 同上 |

### 结构件（按实拍装配）

| 文件 | 库中名称 | 尺寸 mm | 面数 | 装在哪 |
|---|---|---|---|---|
| `part_horn25t.stl` | 25t主舵盘 | ⌀20 × 4.5 | 6,380 | `base_yaw_link`，压在 S2 输出轴上当转台 |
| `part_u_long.stl` | 单轴长U支架 | 56 × 62.5 × 25.5 | 4,248 | 肩、肘关节，绕 Z 转 90° 夹舵机 |
| `part_u_short.stl` | 单轴短U支架 | 56 × 44.7 × 25.5 | 3,872 | 腕俯仰关节 |
| `part_claw.stl` | 新款机械爪 | 59.4 × 22.0 × 108.5 | 46,564 | `gripper_base_link`，绕 Y 转 180° |

厂商原始几何由 `tools/step2mesh.js` 自动探测，关键数据：

- **S20F**：54.40 × 20.00 × 45.92 mm，输出轴 +Z 位于 (X=+10.03, Y=0)，⌀5.8 的 25T 花键
- **DS3120**：本体 40.02 × 45.50 × 20.14 mm，输出轴 +Y 位于 (X=10.0, Z=0)，⌀6.0 花键
- **单轴长/短U支架**：两片侧板在 X=±28（内间距 ≈50mm，正好夹住标准舵机的安装法兰），
  U 口朝 +Y，底座在 Y=0
- **新款机械爪**：21 个零件的平行连杆机构，开口沿 X、伸出方向 −Z、驱动轴沿 Y

每个 link 里，**驱动该关节的舵机身挂在上一个 link 上**（物理正确：壳体固定、舵盘跟动），
所以转关节时舵机不会跟着乱转。

## 装配的简化与已知差异

| 部位 | 实拍 | 本模型 | 说明 |
|---|---|---|---|
| 大臂 | 两片黑色平行侧板 | 两片 26 × 4mm 侧板（Y=±13） | ✅ 已按实拍改 |
| 前臂 | 银色铝圆管 | ø22 圆柱，金属色 | ✅ 一致 |
| 底座 | 上下两块 90×84 板夹方箱 | 参数化板件 + 方箱 | 库里 `单轴脚板` 是 63.5×123.5，尺寸对不上，故参数化 |
| 夹爪 | 平行连杆，双指联动 | **整体刚性挂载**，不联动 | 连杆需解算，暂不做 |
| S5 | PM15S | S20F 270° 代替 | 三维图暂缺 |
| 腕部到夹爪 | 舵机 → 短连接 → 夹爪舵机 → 铝爪 | 铝爪下缘与腕滚转柱重叠约 1.4cm | 模拟爪安装板包住舵机的实际装配 |
| 腕部到夹爪 | 舵机 → 短连接 → 夹爪舵机 → 铝爪 | 铝爪下缘与腕滚转柱重叠约 1.4cm | 模拟爪安装板包住舵机的实际装配 |

## 尺寸依据（厂商规格图）

| 项目 | 厂商值 | 本模型 | 备注 |
|---|---|---|---|
| 整机高度 | 50.5 cm（用户实测约 55） | **55.7 cm** | 全零姿态（直臂垂直） |
| 底座板 | 9 × 8.4 cm | 90 × 84 mm | ✅ |
| 机械爪 | 98 × 109 mm | 59.4 × 108.5 mm（闭合态） | 长度吻合，98 是张开跨度 |
| 舵机 | 40.9 × 20.5 × 39.5 | S20F 54.4 × 20 × 45.9（含法兰） | ✅ 同一规格族 |

> ⚠ 早前把规格图上的 **43 cm / 31.3 cm** 当成了两段连杆长度，导致模型总高做到 119 cm（实际两倍）。
> 那其实是整臂展开尺寸。

## 杆长（部分已实测）

| 参数 | 值 | 来源 |
|---|---|---|
| `upper_arm_len` | **0.105** | ✅ 实测 S3 → S4 螺栓孔心距 10.5 cm |
| `forearm_len` | **0.145** | ✅ 实测 S4 → S5 螺栓孔心距 14.5 cm |
| `wrist_len` | 0.040 | 估算（腕俯仰轴 → 腕滚转轴的竖直段） |
| `base_height` | 0.095 | 估算（地面 → 偏航轴） |

两段实测值代回去，全零总高 **55.7 cm**，与用户卷尺量到的「约 55 cm」自洽 ✓

## 文件

```
k3b_arm_urdf/
├── k3b_arm.urdf.xacro    参数化源文件（改这个）
├── k3b_arm.urdf          展开结果（RViz / MoveIt 用这个）
├── expand.py             没装 ROS 的机器上展开 xacro
├── preview.html          浏览器里看装配、拖滑块动关节
├── package.xml           让 package:// 能解析（需 colcon 安装）
├── CMakeLists.txt
└── meshes/               舵机 + 结构件 STL（见上方清单）
```

## 使用

```bash
# 若改过 xacro，先重新展开
xacro k3b_arm.urdf.xacro > k3b_arm.urdf

# 装进工作空间（package:// 才能解析到 meshes/）
cp -r k3b_arm_urdf ~/ros2_ws/src/ && cd ~/ros2_ws && colcon build

# 预览
ros2 run robot_state_publisher robot_state_publisher \
  --ros-args -p robot_description:="$(xacro k3b_arm_urdf/k3b_arm.urdf.xacro)"
ros2 run joint_state_publisher_gui joint_state_publisher_gui
rviz2
```

**不想开 RViz** 时，用网页预览（模型热、带关节滑块）：

```bash
cd viewer3d && python serve.py     # 或双击 启动预览.bat
# 打开 http://127.0.0.1:8777/k3b_arm_urdf/preview.html
```

## MoveIt2

```bash
ros2 run moveit_setup_assistant moveit_setup_assistant
```

导入 `k3b_arm.urdf`，规划组：

- `arm`：5 个转动关节（base_yaw → wrist_roll）
- `gripper`：`finger_left_joint`（右指是 mimic，会自动跟随）

**注意**：`wrist_roll` 是速度舵机、无位置反馈，逆解时把它设为 **passive/disable**，
否则解算器会分配自由度给它，实机却执行不了。

## ⚠️ 实机前仍需校准

1. **杆长**：`upper_arm_len` / `forearm_len` 已实测填入；还需补 `wrist_len` 与 `base_height`
2. **直立位对应脉宽**：上表给的是量程和上电值，还缺「直立时各舵机的脉宽」——这是下位机做
   `脉宽 → 关节角` 标定的关键，务必实测记录
3. **真实质量/惯量**：Gazebo 物理仿真前必须填写
4. **S5 / PM15S**：拿到三维图后替换网格，并按实测修正 `lim_wpitch`
5. **夹爪开合**：实测张开角与工件尺寸，调整 `lim_finger` 和指长
