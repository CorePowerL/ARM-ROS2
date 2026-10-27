# k3b_arm_moveit_config · MoveIt 2 配置

K3B 六轴舵机机械臂的 MoveIt 2 配置包。不开实机、不要 Gazebo，在 RViz 里就能跑通
「设目标 → 规划 → Execute → 手臂动起来」。

- `arm` 组：5 个转动关节，末端 `tool0`（两爪尖正中间）
- `gripper` 组：1 个主动关节，四连杆的 5 个从动件由 URDF 的 `<mimic>` 自动带动

> 这个包**没有**用 MoveIt Setup Assistant 生成。SA 需要图形界面、要在一台装好 ROS 的
> 机器上点几十下，而且生成完还是得手改。这里直接写配置，加上
> `tools/check_moveit_config.py` 做一致性校验 —— 改错会当场报出来，不用等到 RViz 里
> 看那个莫名其妙灰色的面板。

---

## 零、我该怎么打开？（从 Windows 到看到机器人）

**没有 exe 可以双击。** MoveIt 是 ROS 2 的节点集合，只能在 Linux 上跑。按你现在想干啥分两条路。

### A. 只想看看模型长什么样 → 现在就能开（不用 ROS）

双击仓库里的 `viewer3d/启动预览.bat`，它起一个本地服务并自动开浏览器。直接访问装配预览：

```
http://127.0.0.1:8777/k3b_arm_urdf/preview.html
```

首页是 `最新三维图` 的 STEP/IGES 模型清单，装配预览要走上面这个具体地址。

> 不能直接双击 `preview.html` —— 它用绝对路径引 `three`（`/viewer3d/vendor/...`），
> `file://` 下会被浏览器拦。必须走上面那个本地服务。

### B. 要真的规划、Execute、看手臂动 → 需要 Linux

三选一，按推荐顺序：

| 方案 | 代价 | 适合 |
|---|---|---|
| **WSL2 + Ubuntu 24.04** | 装一次，半小时 | **先用这个**，就在这台 Windows 上，Win11 自带图形转发（WSLg），RViz 能直接弹窗 |
| 一台 Ubuntu 24.04 物理机 / 双系统 | 另一台机器 | 长期主力开发，跑 Gazebo 也够力 |
| K3B 板子上原生跑 | ARM64 装 MoveIt 依赖多、算力紧 | 只做最后实机联调，不建议拿它当开发机 |

#### WSL2 全程命令（管理员 PowerShell）

```powershell
wsl --install -d Ubuntu-24.04      # 装完重启，按提示设 Linux 用户名密码
wsl --set-default-version 2
```

然后进 Ubuntu（开始菜单搜 Ubuntu，或 `wsl`），装 ROS 2 Jazzy：

```bash
# 1) 把 ROS 2 的 apt 源加上（不做这步 apt 里根本没有 ros-jazzy-*）
sudo apt update && sudo apt install -y curl gnupg lsb-release
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
     -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# 2) 装桌面版（含 RViz）+ 编译工具
sudo apt update
sudo apt install -y ros-jazzy-desktop ros-dev-tools

# 3) 让每个新终端自动 source
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc && source ~/.bashrc

# 4) 初始化 rosdep（colcon 装系统依赖时要用）
sudo rosdep init 2>/dev/null; rosdep update
```

`Ubuntu 24.04` 对应的发行版就是 **Jazzy**，版本别装错 —— 22.04 只能装 Humble，
本包的 launch 用的是 Jazzy 的 API。

#### 把仓库挂进 colcon 工作空间

仓库里两个包都在根目录，没有 `src/`。**不要直接在仓库根目录 `colcon build`**
（会在仓库里生成 build/install/log，还会把 `viewer3d`、`assets` 一起扫进来）。
用符号链接挂出去，仓库保持干净：

```bash
REPO="/mnt/c/Users/丁锐/WorkBuddy/Worktrees/ARM-ROS2model/main-e47949fe"   # 按你自己机器改
mkdir -p ~/k3b_ws/src
ln -sfn "$REPO/k3b_arm_urdf"            ~/k3b_ws/src/
ln -sfn "$REPO/k3b_arm_moveit_config"   ~/k3b_ws/src/
cd ~/k3b_ws && colcon build --symlink-install
source install/setup.bash
ros2 launch k3b_arm_moveit_config demo.launch.py
```

> `/mnt/c` 上编译慢一些。嫌慢就把两个包 `cp -r` 到 `~/k3b_ws/src`，
> 改完再同步回去 —— 但**别反过来**用 Windows 那边编辑 `~/` 里的文件，WSL 内文件
> 从 Windows 侧写容易乱权限。

`--symlink-install` 的好处：之后在 Windows 里（比如用 VSCode）改 yaml / srdf，
重新 `colcon build` 是秒级，不用重编。

#### 第一眼该看什么

RViz 起来后左下 **MotionPlanning** 面板 → Planning Group 选 `arm` →
Goal State 选 `ready` → **Plan**。轨迹动画出现就说明配置全对。
然后 **Execute**，模型会照轨迹走一段 —— demo 用的是 mock 硬件，动是"算出来的"，
不接任何实机。

面板如果是灰的、或 Plan 一直红，跳到第七节那张故障对照表。

---

## 一、装依赖

```bash
sudo apt install ros-jazzy-moveit \
                 ros-jazzy-ros2-control ros-jazzy-ros2-controllers \
                 ros-jazzy-joint-state-publisher ros-jazzy-joint-state-publisher-gui
```

想换更好的逆解器（强烈建议，见第五节）：

```bash
sudo apt install ros-jazzy-pick-ik
```

## 二、跑起来

```bash
# 工作空间根目录
colcon build --symlink-install
source install/setup.bash

ros2 launch k3b_arm_moveit_config demo.launch.py
```

RViz 起来后：

1. 左下 **MotionPlanning** 面板 → **Planning Group** 选 `arm`
2. **Goal State** 下拉里选 `forward` 或 `ready`（这两个位姿做过正运动学校核）
3. 点 **Plan** → 轨迹动画出来 → 点 **Execute** → 模型真的动
4. 夹爪：Planning Group 切到 `gripper`，Goal State 选 `open` / `closed`，同样 Plan + Execute

`demo.launch.py` 起的是 **mock 硬件**（`mock_components/GenericSystem`）：位置指令直接
当成状态回读，所以 Execute 是"假的动"，但没有 Gazebo 的启动开销和物理参数依赖。
将来接实机只换 hardware plugin，MoveIt 这层一行不用改。

其他跑法：

```bash
# 不起 RViz（远程调试 / 只看日志）
ros2 launch k3b_arm_moveit_config demo.launch.py rviz:=false

# 额外起 joint_state_publisher_gui 手动拖关节（纯看模型用，会和 ros2_control 抢 /joint_states）
ros2 launch k3b_arm_moveit_config demo.launch.py use_joint_state_gui:=true

# 已经有自己的控制器在跑，只要 MoveIt
ros2 launch k3b_arm_moveit_config move_group.launch.py
```

## 三、目录

```
k3b_arm_moveit_config/
├── config/
│   ├── k3b_arm.srdf              # 规划组 / 命名位姿 / 自碰撞豁免
│   ├── kinematics.yaml           # 逆解器（KDL 兜底，注释里给了 pick_ik / TRAC-IK）
│   ├── joint_limits.yaml         # 速度与加速度上限（位置限位在 URDF 里）
│   ├── moveit_controllers.yaml   # MoveIt → controller 的桥
│   ├── ros2_control_demo.yaml    # controller_manager 参数（给 ros2_control 看的）
│   ├── ompl_planning.yaml        # 规划器与采样密度
│   └── moveit.rviz               # RViz 布局（Fixed Frame = world）
├── launch/
│   ├── demo.launch.py            # 全套：mock 硬件 + 控制器 + move_group + RViz
│   └── move_group.launch.py      # 只 MoveIt，控制器自己起
└── package.xml / CMakeLists.txt
```

模型在隔壁 `k3b_arm_urdf` 包里：

- `k3b_arm.urdf.xacro` —— 纯模型，RViz 预览 / URDF 检查用
- `k3b_arm_sim.urdf.xacro` —— 纯模型 + ros2_control 接口，`demo.launch.py` 用这个
  （靠 xacro include 把 `<robot>` 拆开拼接，主 URDF 不用改一行）
- `ros2_control/k3b_arm.ros2_control.xacro` —— 6 个主动关节的 command/state 接口

---

## 四、5 DoF 意味着什么（设目标前必读）

「六轴」指的是**六个舵机**，不是六个臂轴：

```
S2 base_yaw(Z) ─ S3 shoulder(Y) ─ S4 elbow(Y) ─ S5 wrist_pitch(Y) ─ DS3120 wrist_roll(Z)
                                                                      ↑ 臂只有 5 DoF
S1 finger_left_gear_joint                                              ← 夹爪 1 DoF，算第 6 轴
```

三个 pitch 关节全部在 `base_yaw` 转出来的那个**竖直平面**里，所以工具轴永远困在这个
平面内 —— 它指向哪个方位角，`base_yaw` 就必须转到哪个方位角。6 维位姿目标里有一维是
这个构型给不出来的。

实际影响：**任意拖一个 Pose 目标，大约一半无解**（RViz 里表现为 Plan 一直失败、目标
标记变红）。设目标时守两条：

1. 先让 `base_yaw` 对准目标的方位角
2. 工具轴不要要求"撇开"臂所在平面（顶抓、正前方侧抓都没问题）

嫌麻烦就把 `config/kinematics.yaml` 里 `position_only_ik` 改成 `true` —— 只解位置，
姿态由 IK 自己挑，几乎必解出来，代价是爪的朝向不可控。

## 五、逆解器

默认 KDL，因为随 `ros-jazzy-moveit` 一起装，开箱即跑。但这个臂**没有球形手腕**
（最后三个轴不交于一点），KDL 的牛顿迭代在这种构型上收敛率一般，再叠加 5 DoF 的
欠定，成功率不理想。

真想用得舒服，换 `pick_ik`：

```bash
sudo apt install ros-jazzy-pick-ik
```

然后把 `config/kinematics.yaml` 的 `arm:` 段整体替换成（文件注释里也有这段）：

```yaml
arm:
  kinematics_solver: pick_ik/PickIkPlugin
  kinematics_solver_timeout: 0.05
  kinematics_solver_attempts: 3
  mode: global
  stopping_scale: 0.001
  position_threshold: 0.001     # 1mm
  orientation_threshold: 0.01   # rad
  cost_threshold: 0.001
  minimal_displacement_weight: 0.0
```

## 六、改配置时注意

改完**一定**跑一遍校验：

```bash
python tools/check_moveit_config.py
```

它检查的是那些"错了也不报错、只是行为诡异"的地方：

| 检查项 | 不检查会怎样 |
|---|---|
| SRDF 引用的 link / joint 是否存在 | 面板灰掉，日志里一行 warning 都没有 |
| chain 是否连通、DoF 是否对得上 | 规划组为空，或者悄悄多/少一个自由度 |
| `group_state` 的值是否超限位 | 一选那个位姿就报 "start state out of bounds" |
| mimic 关节有没有被写进 group / controller / ros2_control | 静态模型正常，一动就打架 |
| 父子 link 是否都在 `disable_collisions` 里 | 每次规划都报自碰撞，永远红 |
| 三个地方的 controller 关节列表是否一致 | 能规划、点 Execute 却没反应 |

它会打印每个命名位姿的正运动学结果（末端在哪个位置、工具轴指向哪），数字明显不对
就是位姿写错了。

### 关于夹爪的自碰撞豁免

`gripper_base_link` 下面 7 个带碰撞体的零件（壳体 + 齿扇×2 + 指片×2 + 连杆×2）
两两 21 对**全部**标了 `disable_collisions`。

这不是偷懒：它们本来就是铰接在一起的装配体，任何位姿下都互相贴合；而且夹爪存在的
意义就是夹住东西，内部本来就要允许"接触"。不豁免的话张开时必然自撞。
指片与**场景物体**（规划场景里的 box / cylinder）仍然正常检测。

### 关于没有 virtual_joint

URDF 里已经有真实的 `world` link + `world_joint`（fixed），底座是接地的。
再加一个 virtual joint 会让 MoveIt 认为底座是浮空的，和 fixed joint 冲突。

## 七、点 Execute 没反应？按这张表查

```bash
# 1. 控制器起了吗
ros2 control list_controllers
#    期望 3 个 active：joint_state_broadcaster / k3b_arm_controller / k3b_gripper_controller

# 2. action server 在吗（MoveIt 就是往这里投轨迹）
ros2 action list | grep follow_joint_trajectory
#    期望 /k3b_arm_controller/follow_joint_trajectory

# 3. 关节状态有吗
ros2 topic echo /joint_states --once
#    期望 6 个关节，含 finger_left_gear_joint

# 4. MoveIt 认到的 controller 列表
ros2 param get /move_group moveit_controller_manager
```

| 现象 | 大概率原因 |
|---|---|
| MotionPlanning 面板整块是灰的 | RViz 没拿到 SRDF —— 检查 launch 里 rviz 的 `parameters` 是否带了 `robot_description_semantic` |
| Plan 一直失败、目标标记变红 | 5 DoF 目标不可达（第四节）；或起点本身就在碰撞里（面板勾上 Query Start State 看） |
| 能 Plan，点 Execute 毫无反应 | `moveit_controllers.yaml` 的 controller 名 / 关节列表与实跑的对不上（第七节 1、2 步） |
| 手臂动了，夹爪不动 | `k3b_gripper_controller` 没起，或它的 joints 写成了带 mimic 的 |
| 模型张牙舞爪 / 关节全 0 | `/joint_states` 没来，或关节名与 URDF 对不上 |
| 两片指片不动，只有齿扇动 | `robot_state_publisher` 没在跑 —— mimic 是它算的，不是 ros2_control |
| RViz 里 TF 报 "No transform from [world]" | Fixed Frame 设成了别的，或 rsp 挂了 |

## 八、接实机（阶段 5 之后）

架构不变，只换硬件层：

1. 在 `k3b_arm_urdf/ros2_control/k3b_arm.ros2_control.xacro` 里把

   ```xml
   <plugin>mock_components/GenericSystem</plugin>
   ```

   换成你自己的 `SystemInterface` 插件（K3B 侧读串口、STM32 侧出 PWM）：

   ```xml
   <plugin>k3b_arm_hardware/K3bArmSystem</plugin>
   <param name="serial_port">/dev/ttyS3</param>
   <param name="baudrate">115200</param>
   ```

2. `launch/move_group.launch.py` 照常用，`moveit_controllers.yaml` 不用动
3. **先把 `joint_limits.yaml` 的速度/加速度再往下降**（0.3 → 0.1），确认动作方向和
   限位都对，再往上加

### `wrist_roll` 这个速度舵机怎么办

它是 DS3120 360° 连续舵机，**没有位置反馈**，严格说做不了位置控制。三个选择：

| 做法 | 改什么 | 适合 |
|---|---|---|
| **保 5 DoF，下位机做速度闭环**（推荐） | 什么都不用改，STM32 侧收到目标角后按「目标 − 当前」算误差给 PWM | 想保留绕工具轴自转的能力 |
| 降成 4 DoF | SRDF 里把 `<chain .../>` 换成 5 个 `<joint>`，去掉 `wrist_roll`；`kinematics.yaml` 打开 `position_only_ik: true` | 只要位置，不要姿态 |
| 原地锁死 | 规划前给它加一个等于当前值的 joint constraint | 这个轴暂时不用 |

降成 4 DoF 的 SRDF 写法：

```xml
<group name="arm">
  <joint name="base_yaw"/>
  <joint name="shoulder_pitch"/>
  <joint name="elbow_pitch"/>
  <joint name="wrist_pitch"/>
</group>
```

改完记得同步 `moveit_controllers.yaml` / `ros2_control_demo.yaml` 里
`k3b_arm_controller` 的关节列表，然后跑一次校验脚本。

## 九、还没做的

- **Gazebo / Ignition 仿真**：需要真实质量与惯量（现在 URDF 里是占位估算值）
- **抓取（Grasp）**：SRDF 里 `end_effector` 已经写了，但还没配抓取生成器。
  注意它的 `parent_link` 取的是 `gripper_base_link` 而不是 `tool0` —— 夹爪的驱动关节
  挂在 `gripper_base_link` 上，`tool0` 只是它下方 82mm 的一个参考点
- **MoveIt Task Constructor**：多阶段任务（先接近、再夹、再抬起）才需要
