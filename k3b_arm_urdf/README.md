# K3B 机械臂 URDF

依据实测舵机参数 + 商家提供的夹爪 STL 模型建模。

## 舵机 ↔ 关节映射

| URDF 关节 | 舵机 | 类型 | 脉宽范围(μs) | 限位 |
|---|---|---|---|---|
| `base_yaw` | S2 | 180° 位置 | 500–2500 | ±90° |
| `shoulder_pitch` | S3 | 270° 位置 | 500–2000 | ±101° |
| `elbow_pitch` | S4 | 270° 位置 | 500–2500 | ±135° |
| `wrist_pitch` | S5 | 270° 位置 | 600–2500 | ±128° |
| `wrist_roll` | 360° 速度舵机 | continuous | — | 无限位 |
| `finger_left_joint` | S1 | 180° 位置 | 850–1500 | 0 ~ 58.5° |
| `finger_right_joint` | — | mimic S1 | — | 自动跟随 |

> 末端工具坐标系：`tool0`。

## 文件

- `k3b_arm.urdf` —— 已展开，可直接加载
- `k3b_arm.urdf.xacro` —— 参数化源文件（改参数后重新展开）
- `README.md` —— 本说明

## 关键设计说明

### wrist_roll 是 continuous joint

该关节由 360° 连续旋转速度舵机驱动，无位置反馈。URDF 中 `type="continuous"`，只有 effort/velocity 没有 lower/upper。**MoveIt 规划组不要包含此关节**，它只在实机/仿真里做转速控制。

### 夹爪是单舵机 + mimic

S1 一个舵机通过连杆驱动两指同步开合。`finger_left_joint` 是驱动关节，`finger_right_joint` 通过 `<mimic multiplier="-1"/>` 对称跟随。

### 角度换算

```
180° 舵机: angle_deg = (pulse_us - 500) × 180 / 2000
270° 舵机: angle_deg = (pulse_us - 500) × 270 / 2000
```

当前 xacro 里关节限位按"脉宽中点 = 机械臂直立位"对称设置，实物标定后微调。

## 使用

```bash
# RViz 预览
ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:="$(cat k3b_arm.urdf)"

# xacro 重新展开
xacro k3b_arm.urdf.xacro > k3b_arm.urdf
```

## ⚠️ 实机前必须校准

1. **杆长实测**：替换 `upper_arm_len`(0.43)、`forearm_len`(0.313)、`wrist_len`(0.09)
2. **直立位偏置**：确认每个舵机中点脉宽对应臂直立姿态
3. **轴朝向**：若某关节安装方向不同，改对应 `<axis>`
4. **惯量/质量**：当前为占位值，Gazebo 物理仿真前填真实值
5. **夹爪开合**：确认 `lim_finger`(58.5°) 与实际夹爪行程一致
