# ARM-ROS2 · K3B 机械臂 ROS2 工程

基于 **KICKPI K3B（瑞芯微 RK3562, aarch64）** 主控板 + **STM32F407** 下位机 + **WHEELTEC S20F PWM 舵机** 的六自由度机械臂 ROS2 控制工程。

> 系统：Ubuntu 24.04 · ROS2 Jazzy · MoveIt2

---

## 硬件架构

```
┌─────────────────────────┐         UART / 串口          ┌──────────────────┐
│  KICKPI K3B (RK3562)    │  ─────────────────────────▶  │  STM32F407       │
│  Ubuntu 24.04 + ROS2    │   /joint_commands (rad)      │  5路PWM(位置)+1路 │
│  Jazzy + MoveIt2        │ ◀─────────────────────────   │  PWM(速度舵机)   │
└─────────────────────────┘   /joint_states (命令值)     └──────────────────┘
```

| 项 | 规格 |
|---|---|
| 主控板 | KICKPI K3B（RK3562, aarch64） |
| 下位机 | STM32F407 |
| 位置舵机 | WHEELTEC S20F ×5（180°×2 + 270°×3） |
| 速度舵机 | 360° 连续旋转舵机 ×1（夹爪旋转） |
| 夹爪 | 单舵机驱动两指联动（STL 外形已建模） |
| 控制信号 | PWM 50Hz（周期 20ms） |
| 舵机供电 | 独立电源 ≥15A，与逻辑共地 |
| ROS 版本 | ROS2 Jazzy（Ubuntu 24.04） |

## 舵机编号 ↔ 关节映射（实测 2026-10-25）

| 舵机 | 类型 | 脉宽范围(μs) | 上电初始 | URDF 关节名 | 作用 | 限位(相对直立位) |
|---|---|---|---|---|---|---|
| S1 | 180° 位置 | 850–1500 | 850 | `finger_left_joint` | 夹爪开合 | 0 ~ 58.5° |
| S2 | 180° 位置 | 500–2500 | 1500 | `base_yaw` | 底座偏航 | ±90° |
| S3 | 270° 位置 | 500–2000 | 2000 | `shoulder_pitch` | 肩俯仰 | ±101° |
| S4 | 270° 位置 | 500–2500 | 500 | `elbow_pitch` | 肘俯仰 | ±135° |
| S5 | 270° 位置 | 600–2500 | 1500 | `wrist_pitch` | 腕俯仰 | ±128° |
| 速度舵机 | 360° 连续 | — | — | `wrist_roll` | 夹爪旋转 | 无限位(continuous) |

> `finger_right_joint` 通过 `<mimic joint="finger_left_joint" multiplier="-1"/>` 跟随左指，不单独接舵机。
> `wrist_roll` 是速度舵机，无位置反馈，URDF 中为 `continuous` 类型，不参与 MoveIt 逆解。

## 关节结构

| 关节名 | 类型 | 轴 | 舵机 | 说明 |
|---|---|---|---|---|
| `base_yaw` | revolute | Z | S2 | 底座偏航 |
| `shoulder_pitch` | revolute | Y | S3 | 肩俯仰 |
| `elbow_pitch` | revolute | Y | S4 | 肘俯仰 |
| `wrist_pitch` | revolute | Y | S5 | 腕俯仰 |
| `wrist_roll` | continuous | Z | 速度舵机 | 夹爪旋转，控速不控位 |
| `finger_left_joint` | revolute | Y | S1 | 夹爪开合驱动 |
| `finger_right_joint` | revolute | Y | (mimic) | 夹爪右指，跟随左指 |

末端工具坐标系：`tool0`。

## 目录结构

```
ARM-ROS2/
├── README.md                          # 本文件
├── .gitignore
├── ROS2开发路线_K3B机械臂.md           # 六阶段开发路线
├── k3b_arm_preview.html               # 浏览器 3D 预览（双击打开）
├── assets/                            # 预览页资源
│   └── gripper_data.js                # 夹爪 STL (base64)
├── k3b_arm_urdf/                      # URDF 模型
│   ├── k3b_arm.urdf                   # 展开后可直接加载
│   ├── k3b_arm.urdf.xacro             # 参数化源文件
│   └── README.md                       # 模型说明与校准清单
├── stm32_firmware/                    # [待开发] STM32F407 PWM 驱动
└── ros2_ws/                           # [待开发] colcon workspace
```

## 快速开始

### 0. 浏览器预览（无需 ROS）

双击 `k3b_arm_preview.html`，可拖动关节滑块、旋转视角查看机械臂。

### 1. RViz2 预览

```bash
sudo apt install ros-jazzy-robot_state_publisher ros-jazzy-joint-state-publisher-gui ros-jazzy-rviz2

# 终端 1：发布模型 + TF
ros2 run robot_state_publisher robot_state_publisher \
  --ros-args -p robot_description:="$(cat k3b_arm_urdf/k3b_arm.urdf)"

# 终端 2：拖动关节
ros2 run joint_state_publisher_gui joint_state_publisher_gui

# 终端 3：可视化（Fixed Frame 选 world）
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
- `arm`：**4 个位置关节**（`base_yaw` + `shoulder_pitch` + `elbow_pitch` + `wrist_pitch`）
  - **不要把 `wrist_roll` 加入规划组**——它是 360° 速度舵机，无位置反馈，不做逆解
- `gripper`：`finger_left_joint`（右指 mimic，自动跟随）
- 逆解：默认 KDL，效果差换 TRAC-IK

## 开发路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | Linux 环境（Ubuntu 24.04 烧录） | 🔲 |
| 1 | ROS2 Jazzy 基础 | 🔲 |
| 2 | URDF 建模 + 可视化 | ✅ 模型完成，夹爪已用真实 STL |
| 3 | MoveIt2 运动规划 | 🔲 |
| 4 | Gazebo 仿真（可选） | 🔲 |
| 5 | Linux ↔ STM32 串口通信 | 🔲 |
| 6 | 实机联调 + 抓取 | 🔲 |

详见 [ROS2开发路线_K3B机械臂.md](ROS2开发路线_K3B机械臂.md)。

## ⚠️ 实机前必须校准

当前 URDF 的杆长为按图估算，驱动真实机械臂前必须完成：

1. **杆长实测**：替换 `upper_arm_len`(0.43)、`forearm_len`(0.313)、`wrist_len`(0.09)
2. **直立位偏置**：当前假设"脉宽中点 = 臂直立位"，实机上电后若关节 0 位不直，调 xacro 顶部 `lim_should`/`lim_elbow`/`lim_wpitch`
3. **轴朝向核对**：与实物安装方向一致
4. **真实质量/惯量**：Gazebo 物理仿真前必须填写
5. **夹爪开合量**：确认 `lim_finger`(58.5°) 与实际工件尺寸匹配

## 角度→脉宽映射（STM32 侧）

不同舵机角度量程不同，**不能用统一公式**。设关节角 θ 为相对直立位的弧度，直立位对应脉宽 `pulse_mid`：

```
180° 舵机 (S1, S2):  pulse = pulse_mid + θ(rad) / π × 2000
270° 舵机 (S3,S4,S5): pulse = pulse_mid + θ(rad) / (1.5π) × 2000
```

各舵机 `pulse_mid`（直立位对应脉宽，需实物标定）：

| 舵机 | pulse_mid(μs) | 说明 |
|---|---|---|
| S1 | 夹爪中点 | 0=闭合(1500μs)，开=850μs |
| S2 | 1500 | 中点即直立位 |
| S3 | 1250 | 500~2000μs 中点 |
| S4 | 1500 | 500~2500μs 中点 |
| S5 | 1550 | 600~2500μs 中点 |

> 360° 速度舵机不做角度映射，直接输出占空比控制转速（方向由脉宽 >1500 或 <1500 决定）。
> PWM 周期统一 20ms (50Hz)。

## 参考

- KICKPI K3B 官方文档：https://doc.kickpi.cn/Products/Beginner-Guide/KICKPI-K3B/
- ROS2 Jazzy：https://docs.ros.org/en/jazzy/
- MoveIt2：https://moveit.picknik.ai/main/
