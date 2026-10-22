# K3B 六轴机械臂 URDF

依据淘宝在售「6 自由度舵机机械臂 DIY 套件」实物结构图建模。

## 关节结构（自上而下）

| 关节名 | 类型 | 轴 | 作用 | 默认限位 |
|---|---|---|---|---|
| base_yaw | revolute | Z | 底座偏航 | ±90° |
| shoulder_pitch | revolute | Y | 肩俯仰 | ±90° |
| elbow_pitch | revolute | Y | 肘俯仰 | ±90° |
| wrist_pitch | revolute | Y | 腕俯仰 | ±90° |
| wrist_roll | revolute | Z | 腕滚转 | ±90° |
| finger_left / finger_right | revolute | Y | 两指夹爪 | 0–34° |

> 执行器为 **DS3218MG 标准 PWM 舵机**（500–2500μs、中点 1500μs、默认 180°）。
> 关节量程按舵机 ±90° 设定，实际机械限位以实测为准（舵机如为 270° 版可放宽）。

## DS3218MG PWM 控制（下位机 STM32F407）

- 控制方式：**PWM**（非串行总线）。STM32 用定时器输出 6 路 PWM，周期 20ms（50Hz）。
- 角度→脉宽映射（线性）：`pulse(μs) = 1500 + θ(°) / 180 × 2000`（0.5ms→0°、1.5ms→90°、2.5ms→180°）。
- STM32 接收上位机 ROS 下发的关节目标角(rad)，换算成每路脉宽并输出；`/joint_states` 回显**命令值**（该舵机无位置反馈，属开环）。
- 舵机参数：工作电压 5–6.8V，堵转扭矩 28kg·cm@6.8V，堵转电流 2.9A@6.8V。
- **供电**：6 只舵机峰值电流可能接近 17A，需独立 **6.8V 大电流电源（建议 ≥15A 或按裕量）**，与逻辑/上位机电源隔离、共地。

末端工具坐标系：`tool0`（抓取参考点）。

## 文件

- `k3b_arm.urdf` —— 已展开，可直接加载
- `k3b_arm.urdf.xacro` —— 参数化源文件（改参数后重新展开）
- `README.md` —— 本说明

## 使用（ROS2 Humble / MoveIt2）

```bash
# 预览（RViz）
rviz2 -d <your_moveit_config>/launch/...   # 或直接 urdf 模型
ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:="$(cat k3b_arm.urdf)"

# 用 xacro 重新展开
xacro k3b_arm.urdf.xacro > k3b_arm.urdf
```

进 MoveIt 前，用 **MoveIt Setup Assistant** 生成规划配置：
```bash
ros2 run moveit_setup_assistant moveit_setup_assistant
```
导入 `k3b_arm.urdf`，规划组 `arm`（5 关节）+ `gripper`（2 指），即可做逆解/规划/抓取模拟。

## ⚠️ 实机前必须校准（图片无法精确给出）

1. **杆长**：实测各关节轴到轴的直线距离，替换 `upper_arm_len`(0.43)、`forearm_len`(0.313)、`wrist_len`(0.09)。
2. **关节限位**：实测每个舵机的机械限位角，避免规划到卡死位置。
3. **轴朝向**：本模型按常见正装结构取 Z/Y 轴；若你的套件某关节安装方向不同，改对应 `<axis>`。
4. **惯量/质量**：当前为占位估算值，仅够规划仿真；做 Gazebo 物理抓取前填真实质量与惯量。
5. **夹爪开合**：实测夹爪张开角度与工件尺寸，调整 `lim_finger` 和指长 `0.09`。

> 模型为按图估算的**原理性结构**，用于仿真演示；驱动真实机械臂前务必完成上述实测校准。
