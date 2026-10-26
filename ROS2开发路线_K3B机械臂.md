# K3B 六轴机械臂 · ROS2 开发项目思路与路线

> 项目根：`D:\stm32_project\ROS`
> 模型文件：`k3b_arm_urdf/`（含 `k3b_arm.urdf`、`k3b_arm.urdf.xacro`、`README.md`）
> 记录时间：2026-10-22

---

## 一、硬件与主控信息（已确认）

| 项 | 内容 |
|---|---|
| 主控开发板 | **KICKPI K3B**（瑞芯微 **RK3562** 芯片，**aarch64/arm64** 架构） |
| 默认系统 | eMMC 预装 Android，可烧 Ubuntu 20.04 / Ubuntu 24.04 / Debian 11 |
| 官方默认账号 | Ubuntu：`kickpi/kickpi`、`root/root`；Debian11：`linaro/linaro`、`root/root` |
| 供电 | Type-C 5V/2A（基准 2A） |
| 显示 | MIPI_LVDS（最大 1080P@60Hz） |
| 无屏开发 | SSH 远程访问（`ifconfig eth0` 查 IP） |
| 串口调试 | DEBUG 引脚 + USB-TTL，MobaXterm，Speed 1500000 |
| 烧录工具 | USB：DriverAssitant + RKDevTool（LOADER/MASKROM 模式）；SD 卡：SDDiskTool |
| 下位机 | STM32（待确认通信方式） |
| 舵机类型 | 待确认（PWM 舵机 / 带反馈位置闭环舵机） |
| 官方文档 | https://doc.kickpi.cn/Products/Beginner-Guide/KICKPI-K3B/ |

---

## 二、ROS 版本决策（重要修正）

> ⚠️ README 原假设 ROS2 Humble（对应 Ubuntu 22.04），但 K3B 官方**没有 22.04 镜像**，必须改选：

| 系统镜像 | ROS 版本 | 结论 |
|---|---|---|
| 官方 **Ubuntu 24.04** | **ROS2 Jazzy** | ✅ **推荐**（LTS 主流，aarch64 包齐全） |
| 官方 Ubuntu 20.04 | ROS2 Foxy | 偏老，新项目不建议 |
| 官方无 22.04 | Humble | 需自行移植，绕开 |

**路线锁定：Ubuntu 24.04 + ROS2 Jazzy。**

---

## 三、K3B 配置五步（上手实操）

1. **准备镜像与工具**：百度网盘下载 `RK3562-K3B/Ubuntu2004` 镜像；装 DriverAssitant（驱动）+ RKDevTool（烧录）；或用 SDDiskTool 做 SD 启动卡。
2. **烧录进 eMMC**：断电长按 `RECOVERY/MASKROM` → 上电 + 插 USB 烧录线 → RKDevTool 识别设备 → `Upgrade Firmware` 选镜像烧录。
3. **首次启动**：接屏进桌面；无屏看 LED（绿常亮 + 蓝闪烁 = 正常）。默认账号 `kickpi/kickpi`。
4. **SSH 远程接入**：`ifconfig eth0` 拿 IP → `ssh kickpi@<IP>`，进入无屏开发模式。
5. **装 ROS2（aarch64）**：

```bash
sudo apt update && sudo apt install software-properties-common
sudo add-apt-repository universe
sudo apt install ros-jazzy-desktop python3-colcon-common-extensions
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
ros2 run turtlesim turtlesim_node   # 验证
```

---

## 四、六阶段开发路线（每阶段一个绿灯里程碑）

| 阶段 | 内容 | 关键工具/命令 | 绿灯里程碑 |
|---|---|---|---|
| 0 | Linux 环境 | Ubuntu 24.04 双系统/烧录，终端/权限/换源 | `sudo apt update` 顺利执行 |
| 1 | ROS2 Jazzy 基础 | 节点/话题/服务/动作，colcon | turtlesim 键盘控制 |
| 2 | 机械臂建模（已有一半） | 读懂 `k3b_arm.urdf`，robot_state_publisher + RViz2 | RViz 显示 6 轴模型可拖动 |
| 3 | MoveIt2 运动规划 | Setup Assistant，规划组 arm(5)+gripper(2)，KDL/TRAC-IK | RViz 逆解 + 轨迹动画 |
| 4 | Gazebo 仿真（可选） | 补真实质量/惯量，ros2_control | 仿真关节按指令动、模拟抓取 |
| 5 | 实机通信架构 | Linux 主控 ↔ STM32，串口/micro-ROS/serial node | `/joint_states` 收到实机反馈 |
| 6 | 实机开发联调 | 校准杆长/限位/轴，驱动节点，MoveIt→实机 | 实机按规划轨迹抓取 |

### 阶段 2 关键命令（URDF 可视化）
```bash
sudo apt install ros-jazzy-robot-state-publisher ros-jazzy-joint-state-publisher ros-jazzy-rviz2
# 终端1：发布模型+TF
ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:="$(cat k3b_arm.urdf)"
# 终端2：拖动关节
ros2 run joint_state_publisher_gui joint_state_publisher_gui
# 终端3：可视化
rviz2
```

### 阶段 3 关键命令（MoveIt）
```bash
sudo apt install ros-jazzy-moveit
ros2 run moveit_setup_assistant moveit_setup_assistant   # 导入 k3b_arm.urdf
```
规划组：`arm`（5 个转动关节）+ `gripper`（2 指）；逆解默认 KDL，效果差换 TRAC-IK。

---

## 五、实机前必须校准（README 原话强调）

1. **杆长**：实测各关节轴到轴直线距离，替换 `upper_arm_len`(0.43)、`forearm_len`(0.313)、`wrist_len`(0.09)。
2. **关节限位**：实测每个舵机机械限位角，避免规划到卡死位置。
3. **轴朝向**：若某关节安装方向不同，改对应 `<axis>`。
4. **惯量/质量**：当前为占位估算值，做 Gazebo 物理抓取前填真实质量与惯量。
5. **夹爪开合**：实测夹爪张开角度与工件尺寸，调整 `lim_finger` 和指长 0.09。

> 模型为按图估算的原理性结构，驱动真实机械臂前务必完成实测校准。

---

## 六、已确认项

- [x] 主控板卡 = KICKPI K3B（RK3562）
- [x] 舵机类型 = WHEELTEC S20F（180°×2 + 270°×3）+ 360° 速度舵机 ×1
- [x] 舵机编号↔关节映射 = S1夹爪 / S2 base_yaw / S3 shoulder / S4 elbow / S5 wrist_pitch / 速度舵机 wrist_roll
- [x] 通信方式 = UART 串口（STM32 PWM 输出，ROS 侧发 rad 目标角）

## 七、待确认项（进入阶段 5 前需要）

- [ ] STM32 与 K3B 的串口接线（TX/RX/共地，用哪组 UART）
- [ ] 直立位实际脉宽偏置（实机上电后标定）
