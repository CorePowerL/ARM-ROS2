# ARM-ROS2 · K3B 六轴机械臂 ROS2 工程

基于 **KICKPI K3B（瑞芯微 RK3562, aarch64）** 主控板 + **STM32F407** 下位机 + **DS3218MG PWM 舵机** 的六轴机械臂 ROS2 控制工程。

> 系统：Ubuntu 24.04 · ROS2 Jazzy · MoveIt2

---

## 硬件架构

```
┌─────────────────────────┐         UART / 串口          ┌──────────────────┐
│  KICKPI K3B (RK3562)    │  ─────────────────────────▶  │  STM32F407       │
│  Ubuntu 24.04 + ROS2    │   /joint_commands (rad)      │  6路PWM输出      │
│  Jazzy + MoveIt2        │ ◀─────────────────────────   │  DS3218MG ×6+2 指 │
└─────────────────────────┘   /joint_states (命令值)     └──────────────────┘
```

| 项 | 规格 |
|---|---|
| 主控板 | KICKPI K3B（RK3562, aarch64） |
| 下位机 | STM32F407 |
| 舵机 | DS3218MG 标准 PWM 舵机 ×6 + 两指夹爪 |
| 舵机参数 | 500–2500μs, 中点 1500μs, 180°, 堵转扭矩 28kg·cm |
| 舵机供电 | 6.8V ≥15A 独立电源（与逻辑共地隔离） |
| ROS 版本 | ROS2 Jazzy（Ubuntu 24.04） |

## 关节结构

| 关节名 | 类型 | 轴 | 作用 | 默认限位 |
|---|---|---|---|---|
| `base_yaw` | revolute | Z | 底座偏航 | ±90° |
| `shoulder_pitch` | revolute | Y | 肩俯仰 | ±90° |
| `elbow_pitch` | revolute | Y | 肘俯仰 | ±90° |
| `wrist_pitch` | revolute | Y | 腕俯仰 | ±90° |
| `wrist_roll` | revolute | Z | 腕滚转 | ±90° |
| `finger_left/right` | revolute | Y | 两指夹爪 | 0–34° |

末端工具坐标系：`tool0`。

## 目录结构

```
ARM-ROS2/
├── README.md                          # 本文件
├── .gitignore
├── ROS2开发路线_K3B机械臂.md           # 六阶段开发路线与硬件配置记录
├── k3b_arm_urdf/                      # URDF 模型（当前已完成）
│   ├── k3b_arm.urdf                   # 展开后可直接加载
│   ├── k3b_arm.urdf.xacro             # 参数化源文件
│   └── README.md                       # 模型说明与校准清单
├── stm32_firmware/                    # [待开发] STM32F407 PWM 驱动
└── ros2_ws/                           # [待开发] colcon workspace
```

## 快速开始

### 1. 预览 URDF 模型（RViz2）

```bash
sudo apt install ros-jazzy-robot-state-publisher ros-jazzy-joint-state-publisher-gui ros-jazzy-rviz2

# 终端 1：发布模型 + TF
ros2 run robot_state_publisher robot_state_publisher \
  --ros-args -p robot_description:="$(cat k3b_arm_urdf/k3b_arm.urdf)"

# 终端 2：拖动关节
ros2 run joint_state_publisher_gui joint_state_publisher_gui

# 终端 3：可视化
rviz2
```

### 2. 用 xacro 重新展开

```bash
xacro k3b_arm_urdf/k3b_arm.urdf.xacro > k3b_arm_urdf/k3b_arm.urdf
```

### 3. MoveIt2 配置

```bash
sudo apt install ros-jazzy-moveit
ros2 run moveit_setup_assistant moveit_setup_assistant
```

导入 `k3b_arm.urdf`，规划组：
- `arm`：5 个转动关节（base_yaw → wrist_roll）
- `gripper`：2 指（finger_left + finger_right）
- 逆解：默认 KDL，效果差换 TRAC-IK

## 开发路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | Linux 环境（Ubuntu 24.04 烧录） | 🔲 |
| 1 | ROS2 Jazzy 基础 | 🔲 |
| 2 | URDF 建模 + RViz 可视化 | ✅ 模型已完成 |
| 3 | MoveIt2 运动规划 | 🔲 |
| 4 | Gazebo 仿真（可选） | 🔲 |
| 5 | Linux ↔ STM32 串口通信 | 🔲 |
| 6 | 实机联调 + 抓取 | 🔲 |

详见 [ROS2开发路线_K3B机械臂.md](ROS2开发路线_K3B机械臂.md)。

## ⚠️ 实机前必须校准

当前 URDF 为按图估算的原理性结构，驱动真实机械臂前必须完成：

1. **杆长实测**：替换 `upper_arm_len`(0.43)、`forearm_len`(0.313)、`wrist_len`(0.09)
2. **关节限位实测**：避免规划到卡死位置
3. **轴朝向核对**：与实物安装方向一致
4. **真实质量/惯量**：Gazebo 物理仿真前必须填写
5. **夹爪开合实测**：调整 `lim_finger` 和指长

## 角度→脉宽映射（STM32 侧）

```
pulse(μs) = 1500 + θ(°) / 180 × 2000
# 0.5ms→0° · 1.5ms→90° · 2.5ms→180°
# PWM 周期 20ms (50Hz)
```

## 参考

- KICKPI K3B 官方文档：https://doc.kickpi.cn/Products/Beginner-Guide/KICKPI-K3B/
- ROS2 Jazzy：https://docs.ros.org/en/jazzy/
- MoveIt2：https://moveit.picknik.ai/main/
