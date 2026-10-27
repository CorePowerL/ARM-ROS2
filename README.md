# ARM-ROS2 · K3B 机械臂 ROS2 工程

基于 **KICKPI K3B（瑞芯微 RK3562, aarch64）** 主控板 + **STM32F407** 下位机 + **WHEELTEC S20F / PM15S / DS3120 舵机** 的六轴机械臂 ROS2 控制工程。

> 系统：Ubuntu 24.04 · ROS2 Jazzy · MoveIt2

---

## 硬件架构

```
┌─────────────────────────┐         UART / 串口          ┌──────────────────┐
│  KICKPI K3B (RK3562)    │  ─────────────────────────▶  │  STM32F407       │
│  Ubuntu 24.04 + ROS2    │   /joint_commands (rad)      │  6路PWM输出      │
│  Jazzy + MoveIt2        │ ◀─────────────────────────   │  S20F×4+PM15S+DS3120│
└─────────────────────────┘   /joint_states (命令值)     └──────────────────┘
```

| 项 | 规格 |
|---|---|
| 主控板 | KICKPI K3B（RK3562, aarch64） |
| 下位机 | STM32F407 |
| 舵机 | WHEELTEC **S20F** ×4（S1/S2 180°、S3/S4 270°）+ **PM15S** ×1（S5）+ **DS3120** ×1（360° 速度舵机） |
| 舵机供电 | 6.8V ≥15A 独立电源（与逻辑共地隔离） |
| ROS 版本 | ROS2 Jazzy（Ubuntu 24.04） |

## 舵机编号 ↔ 关节映射（实测 2026-10-25）

| 舵机 | 类型 | 脉宽范围(μs) | 上电初始 | URDF 关节名 | 作用 | 限位(相对直立位) |
|---|---|---|---|---|---|---|
| S1 | 180° 位置 | 850–1500 | 850 | `finger_left_gear_joint` | 夹爪开合（输出轴带齿轮） | 0 ~ 80° |
| S2 | 180° 位置 | 500–2500 | 1500 | `base_yaw` | 底座偏航 | ±90° |
| S3 | 270° 位置 | 500–2000 | 2000 | `shoulder_pitch` | 肩俯仰 | ±101° |
| S4 | 270° 位置 | 500–2500 | 500 | `elbow_pitch` | 肘俯仰 | ±135° |
| S5 | 270° 位置 | 600–2500 | 1500 | `wrist_pitch` | 腕俯仰 | ±128° |
| 速度舵机 | 360° 连续 | — | — | `wrist_roll` | 夹爪旋转 | 无限位(continuous) |

> 夹爪是四连杆，只有 `finger_left_gear_joint` 接 S1，其余 5 个关节由 `<mimic>` 按反解倍率带动。
> `wrist_roll` 是速度舵机，无位置反馈，URDF 中为 `continuous` 类型，不参与 MoveIt 逆解。

## 关节结构

| 关节名 | 类型 | 轴 | 舵机 | 作用 | 默认限位 |
|---|---|---|---|---|---|
| `base_yaw` | revolute | Z | S2 | 底座偏航 | ±90° |
| `shoulder_pitch` | revolute | Y | S3 | 肩俯仰 | ±101° |
| `elbow_pitch` | revolute | Y | S4 | 肘俯仰 | ±135° |
| `wrist_pitch` | revolute | Y | S5 | 腕俯仰 | ±128° |
| `wrist_roll` | **continuous** | Z | DS3120 | 腕滚转（速度舵机） | 无限位 |
| `finger_*_gear_joint` | revolute | ±Y | **S1**(左) | 齿轮扇形板（输入杆 / 啮合侧镜像） | 0–80° |
| `finger_*_joint` | revolute | ±Y | mimic −1.10533 | 指片 coupler | 0 ~ −88.4° |
| `finger_*_bar_joint` | revolute | ±Y | mimic +0.96141 | 平行连杆 rocker2 | 0 ~ +76.9° |

末端工具坐标系：`tool0`。**全关节为 0 = 直臂垂直 + 夹爪合拢**，限位均相对该位姿定义。

> **夹爪机构**：S1 输出轴带一只齿轮，与对称侧的齿轮扇形板啮合 —— 一对齿轮转向相反，
> 所以右指整条链取 `axis=(0 −1 0)`，倍率与左指相同。逆时针（CCW）张开、顺时针（CW）闭合。
> 每侧四杆闭合：`机身—G—齿轮臂—A—指片—B—平行连杆—R—机身`，
> 杆长 **29.98 / 21.01 / 29.96 / 22.34 mm**（由 STL 销孔坐标反解，非卷尺量）。
> Grashof 判定为**双摇杆**，齿轮臂只摆动不整圈。
> 内距：合拢 **7.5mm** → 全开 **47.1mm**（照片标定约 50）；齿轮中心 → 爪尖 84.3 → 55.1mm。
> 详细反解过程见 [`k3b_arm_urdf/README.md`](k3b_arm_urdf/README.md)。

## 目录结构

```
ARM-ROS2/
├── README.md                          # 本文件
├── .gitignore
├── ROS2开发路线_K3B机械臂.md           # 六阶段开发路线与硬件配置记录
├── k3b_arm_urdf/                      # URDF 模型（含真实舵机网格）
│   ├── k3b_arm.urdf.xacro             # 参数化源文件（改这个）
│   ├── k3b_arm.urdf                   # 展开后可直接加载
│   ├── meshes/                        # 舵机 + 支架/舵盘/铝爪 STL（米制，已对齐）
│   ├── preview.html                   # 浏览器里看装配 + 拖滑块动关节
│   ├── expand.py                      # 没装 ROS 时展开 xacro
│   ├── package.xml / CMakeLists.txt   # 让 package:// 能解析
│   └── README.md                      # 舵机映射表 / 限位 / 校准清单
├── tools/                             # STEP → URDF 网格转换工具
│   ├── step2mesh.js                   # 输出轴自动探测 + OBJ/STL 导出
│   └── README.md
├── viewer3d/                          # STEP 三维图浏览器预览（本地 HTTP 服务）
│   ├── 启动预览.bat                   # 双击即可看 D:\BaiduNetdiskDownload\最新三维图
│   └── serve.py                       # 模型目录托管 + 清单接口 + URDF 预览路由
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
- `gripper`：**只放 `finger_left_gear_joint`**（revolute 0~1.39626 rad）；其余 5 个从动关节都是
  mimic，不要重复加进组，否则会被当成独立自由度
- 逆解：默认 KDL，效果差换 TRAC-IK

## 开发路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | Linux 环境（Ubuntu 24.04 烧录） | 🔲 |
| 1 | ROS2 Jazzy 基础 | 🔲 |
| 2 | URDF 建模 + RViz 可视化 | ✅ 已完成（含真实舵机网格） |
| 3 | MoveIt2 运动规划 | 🔲 |
| 4 | Gazebo 仿真（可选） | 🔲 |
| 5 | Linux ↔ STM32 串口通信 | 🔲 |
| 6 | 实机联调 + 抓取 | 🔲 |

详见 [ROS2开发路线_K3B机械臂.md](ROS2开发路线_K3B机械臂.md)。

## ⚠️ 实机前必须校准

当前 URDF 的杆长为按图估算，驱动真实机械臂前必须完成：

1. **杆长**：`upper_arm_len`(0.105)、`forearm_len`(0.145) 已按实测螺栓孔心距填入；`wrist_len`(0.040)、`base_height`(0.095) 仍为估算
2. **关节限位实测**：避免规划到卡死位置
3. **轴朝向核对**：与实物安装方向一致
4. **真实质量/惯量**：Gazebo 物理仿真前必须填写
5. **夹爪 `lim_gear` 实机标定**：模型在机构锁死角 80° 时内距 47.07mm，照片标定约 50mm。
   把 S1 打到两端实测爪距，回查 `tools/claw_4bar.py` 的扫描表定角，改 `TH_MAX` 重跑
   `emit_gripper.py --write`。详见 `k3b_arm_urdf/README.md` 的「用实拍照片反标定开度」。
6. **`<mimic>` 是线性近似**：倍率按 80° 端点精确拟合，中段与真四连杆有 ≤2mm 残差；
   要精确就用 `ros2_control` 自定义 controller 直接调 `tools/claw_4bar.py` 的 `solve()`。

## 角度→脉宽映射（STM32 侧）

每路舵机量程不同，**不能用一条公式套全部**，按关节分别标定：

```
pulse(μs) = b + a × θ(°)

a = (p_max − p_min) / θ_travel    # μs 每度
b = 直立位（θ=0）对应的脉宽        # 需实测
```

已知的量程与上电值：

| 舵机 | 脉宽 p_min–p_max | 上电初始 | 关节 |
|---|---|---|---|
| S1 | 850–1500 | 850 | finger_left_gear（850=合拢，1500=全开，**CCW 张开 / CW 闭合**） |
| S2 | 500–2500 | 1500 | base_yaw |
| S3 | 500–2000 | 2000 | shoulder_pitch |
| S4 | 500–2500 | 500 | elbow_pitch |
| S5 | 600–2500 | 1500 | wrist_pitch |

> ⚠ 还缺「直立位脉宽 `b`」这一项：上电值不等于直立值（例如 S3 上电 2000 是量程上端）。
> 上实机前逐路把关节摆到直立位、读回脉宽记进表里，否则角度和实际姿态对不上。
> PWM 周期 20ms（50Hz）。
>
> **S1 的方向**：舵盘逆时针（CCW）转 → 齿轮带指片张开；顺时针（CW）→ 闭合。
> 上电 850 落在合拢端，是安全位（不会一上电就张爪）。
> 两指靠一对啮合齿轮同步，所以**只有一个自由度**，另一指不用单独接线。

## 参考

- KICKPI K3B 官方文档：https://doc.kickpi.cn/Products/Beginner-Guide/KICKPI-K3B/
- ROS2 Jazzy：https://docs.ros.org/en/jazzy/
- MoveIt2：https://moveit.picknik.ai/main/
