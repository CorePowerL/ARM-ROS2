# tools · STEP → URDF 网格转换

把厂商给的 `.stp` 零件转成 URDF / RViz / Gazebo 能用的网格，并顺带做几何分析
（判断舵机输出轴朝哪、孔位在哪）。全程离线，用的是项目里 `viewer3d/vendor` 的
OpenCascade WASM。

## 用法

```bash
# 只看几何（不发文件出去）
node tools/step2mesh.js "D:/.../DS3120 20kg.stp" --analyze --parts

# 转成 URDF 网格（米制，输出轴旋到 +Z、轴心移到原点）
node tools/step2mesh.js "D:/.../某个舵机.stp" \
  --drop SG-JIANRONG --drop LV-DUOBAN \
  --shaft +Y --pivot "10,0,8.8" \
  --out k3b_arm_urdf/meshes/xxx
```

| 选项 | 说明 |
|---|---|
| `--out <前缀>` | 输出 `<前缀>.obj` / `.mtl` / `.stl` |
| `--analyze` | 只分析不导出 |
| `--parts` | 打印每个零件的包围盒（分壳体 / 舵盘 / 支架的关键） |
| `--drop <子串>` | 丢掉名字含该子串的零件（厂商模型常把支架、舵盘、线套一起打包） |
| `--shaft +X/-X/+Y/-Y/+Z/-Z` | 输出轴方向，导出时旋到 +Z |
| `--pivot "x,y,z"` \| `center` | 轴心坐标（mm）；`center` = 包围盒中心（支架类零件用这个） |
| `--scale` | 默认 `0.001`（mm → m） |

输出：OBJ+MTL 给 `visual`（保留 STEP 里的面颜色），STL 给 `collision`。

## 批量看尺寸

```bash
node tools/scan.js "D:/.../最新三维图/支架三维图"
```

一次列出目录下所有 STEP 的包围盒、零件数、三角面数 —— 快速找出「这个支架是不是我要的那个」。

## 把刚性网格拆成可动件

`part_claw.stl` 是 21 个零件叠成的刚性网格，挂到 URDF 上只能看、不能开合。
`split_claw.py` 用顶点焊接 + 并查集找连通分量，再按几何特征分类导出：

```bash
python tools/split_claw.py k3b_arm_urdf/meshes/part_claw.stl
```

会打印 21 个连通分件的尺寸与归属，然后按**运动副**写出 7 个文件：

```
claw_body.stl            8,384 面   背板 + 舵盘夹 + 垫块×9
claw_gear_left.stl       4,396 面   齿轮圆盘 + 带齿臂
claw_gear_right.stl      1,360 面   只有带齿臂（整爪只一片圆盘）
claw_finger_left.stl    14,796 面   长夹板 ×2
claw_finger_right.stl   14,796 面
claw_bar_left.stl        1,416 面   平行连杆 ×2
claw_bar_right.stl       1,416 面
```

分类不用包围盒阈值，而用**三角面数**——同型号零件面数完全相同，比尺寸稳得多。
判据写在脚本头部常量里（`TRI_FINGER` / `TRI_GEAR_DISC` / `TRI_GEAR_ARM` / `TRI_BAR`）。
脚本末尾会校验输出面数之和等于原文件面数（46,564），不等就报错；换别的爪改那几个常量即可。

## 四连杆反解（夹爪）

```bash
python tools/claw_4bar.py          # 打印杆长、Grashof 判定、开合扫描表
python tools/emit_gripper.py       # 把结果写进 k3b_arm.urdf.xacro（幂等，可反复跑）
```

`claw_4bar.py` 干三件事：

1. **读销孔**：对每个分件做「内部孔洞检测」——先 flood fill 外部，再找未被填到的连通域，
   每个域就是一个内孔，取质心即销孔中心。比 `HoughCircles` 稳（透视 + 反光会让圆的
   检测一颗都出不来）。
2. **拼拓扑**：按**孔位共点**判断谁和谁共用一根销：
   `#5∩#7 中心孔 → G`、`#7∩#0 → A`、`#0∩#10 → B`、`#10∩#4 → R`。
   四杆闭合且长度自洽，说明拆件和判断都对。
3. **解运动**：圆-圆交点法。给定输入角 θ → A 点（G 绕转）→ B 点 = `圆(R,rocker2) ∩ 圆(A,coupler)`，
   指片转角由 (A,B) 连线求刚体旋转。扫 0→80° 输出开合曲线，端点拟合出 `<mimic>` 倍率。

实测杆长：`rocker1 29.98 / coupler 21.01 / rocker2 29.96 / ground 22.34 mm`
→ Grashof 判定为**双摇杆**（最短杆是 coupler），齿轮臂只摆动不整圈。

> `emit_gripper.py` 只改 xacro 里的「夹爪参数块 + 夹爪 link/joint 块」，靠多锚点字符串
> 定位，重复运行结果一致。它输出的是**数值字面量**，不是 `${...}` 表达式 ——
> `${-${gear_u}}` 这种嵌套写法 xacro 不会求值，会原样留在 URDF 里。

## 一键装仿真环境

适用 **Ubuntu 24.04** 的任意运行方式：VMware / VirtualBox 虚拟机、WSL2、物理机。
（为什么必须是 Ubuntu：ROS 2 的二进制包只对 Ubuntu 发布，openEuler / CentOS / Debian
只能源码编译整个桌面栈，几十 GB 磁盘加一整天，虚拟机里做不成。）

```bash
# 在 Ubuntu 24.04 里，仓库根目录执行
bash tools/bootstrap_ros2.sh             # 只装环境
bash tools/bootstrap_ros2.sh --launch    # 装完直接起 RViz
bash tools/bootstrap_ros2.sh --check     # 装完只跑配置自检
```

不在仓库里也能跑 —— 脚本会自己找（脚本上级 → `~/ARM-ROS2` → `$PWD`），
都找不到就 `git clone` 一份到 `~/ARM-ROS2`。

Windows 侧双击 `tools/启动仿真.bat` 只对 **WSL2** 通道有效（等价于「进 WSL + `--launch`」）。
用 VMware 的话在虚拟机终端里直接跑上面的命令，bat 会提示这一点。

做的事，按顺序：

| 步 | 内容 | 幂等判据 |
|---|---|---|
| 体检 | ① 发行版必须是 Ubuntu 24.04，否则拒绝并说明原因；② 平台与图形通路（WSLg / VMware / 物理机）；③ 内存 <3.5 GB 警告、<7 GB 提示升到 8 GB；④ 根分区 <6 GB 拒绝、<12 GB 警告；⑤ CPU 核数 | — |
| 3D 自检 | `glxinfo -B` 取 renderer，撞到 `llvmpipe` 就是软件渲染，提示去开 VMware 的「加速 3D 图形」 | — |
| 加源 | `packages.ros.org` 的 keyring + `ros2.list` | 文件已存在就跳过 |
| 装包 | `ros-jazzy-desktop` + `moveit` + `ros2_control` + `colcon` + `numpy/yaml` + `mesa-utils`；VMware 上再补 `open-vm-tools-desktop` | `dpkg -s` 逐个查，只装缺的 |
| 清缓存 | `apt-get clean` | 装了包才执行 |
| rosdep | `init` + `update` | 失败只 warn（本包无外部依赖） |
| 工作空间 | `~/k3b_ws/src` 里软链两个包 | `ln -sfn` 天然幂等 |
| 编译 | `colcon build --symlink-install` | — |
| 自检 | 跑 `check_moveit_config.py` | — |
| 收尾 | 把 source 写进 `~/.bashrc` | 查标记行 |

> 脚本**不在仓库根目录 build**：仓库里两个包和 `viewer3d/`、`assets/` 是平级的，
> 在根目录 `colcon build` 会把 build/install/log 落进仓库，还会把无关目录一起扫。
> 工作空间目录可以用 `K3B_WS=~/my_ws` 改，仓库位置可以用 `K3B_REPO_URL` 换。

> 仓库落在 VMware 共享文件夹（`/mnt/hgfs/...`）或 Windows 挂载盘上时，脚本会额外提醒：
> 前者权限是按挂载参数统一映射的、colcon 偶尔抱怨，后者编译明显变慢。
> 两种情况编译产物都写在 `~/k3b_ws`，不会弄脏仓库。

## 校验 MoveIt 配置

```bash
python tools/check_moveit_config.py
```

MoveIt 最气人的地方是**配置写错时不报错**：只表现为 RViz 里那个面板莫名其妙是灰的、
规划永远红色、点 Execute 毫无反应。所以改完 SRDF / yaml 就跑一次。

它检查的是「错了也不报错、只是行为诡异」的那几类：

| 检查项 | 不检查会怎样 |
|---|---|
| SRDF 引用的 link / joint 是否存在 | 面板灰掉，日志里连 warning 都没有 |
| chain 是否连通、DoF 是否对得上 | 规划组为空，或悄悄多/少一个自由度 |
| `group_state` 的值是否超限位 | 一选那个位姿就报 start state out of bounds |
| mimic 关节有没有混进 group / controller / ros2_control | 静态模型正常，一动就打架 |
| 父子 link 是否都在 `disable_collisions` 里 | 每次规划都报自碰撞，永远红 |
| 夹爪内部（`gripper_base_link` 全部后代）是否两两豁免 | 一张开就自撞 |
| 三处 controller 的关节列表是否一致 | 能规划，点 Execute 没反应 |

另外会打印每个命名位姿的正运动学结果 —— 末端坐标、工具轴方向。数字明显不对
（跑到地面以下、工具轴朝天）就是位姿写错了。

脚本本身做过注入测试：删一条 `disable_collisions`、把 `group_state` 改成超限、
从 controller 里删一个关节、往 ros2_control 里塞 mimic 关节、把 chain 的 tip 写成
不存在的 link —— 五种错误全部能被抓出来。

## 网页截图自检

`msedge --headless --screenshot` 在新版 Edge 上经常不出文件，改用 CDP：

```bash
node tools/shot.js http://127.0.0.1:8777/k3b_arm_urdf/preview.html out.png \
  --js "document.querySelectorAll('#joints input')[5].value=0.01;
        document.querySelectorAll('#joints input')[5].dispatchEvent(new Event('input'))" \
  --wait 4000 --w 1200 --h 800
```

`--js` 里的表达式在页面里执行，返回值会打印出来（配合 `window.__preview` 可以直接量尺寸），
页面 console 与异常也会一起回显。

## 已分析的模型

### DS3120 20kg（`最新三维图/DS3120 20kg.stp`）

里装了 8 个零件，是一个**带 MG996 支架 + 两个舵盘的组合体**，不是光秃秃的舵机：

| # | 名称 | 尺寸 (mm) | 是什么 |
|---|---|---|---|
| 0 | ZK | 39.93 × 19.00 × 20.03 | 中壳 |
| 1 | DG-SZ | 39.94 × 10.95 × 20.04 | 底盖（上） |
| 2 | GE | 17.30 × 15.80 × 17.30 | 齿轮组 + 输出轴 |
| 3 | XIANTAO | 18.30 × 4.50 × 6.80 | 线套（出线处） |
| 4 | SG-JIANRONG-MG996 | 54.38 × 13.91 × 19.90 | 舵机安装支架（MG996 通用） |
| 5 | LV-DUOBAN | 35.47 × 6.10 × 15.00 | 铝制长臂舵盘 |
| 6 | DUOPAN-SG | 19.95 × 4.50 × 19.90 | 塑钢圆盘舵盘 |
| 7 | DG-GAO-CK | 40.04 × 11.05 × 20.14 | 底盖（高，沉孔） |

**几何结论**
- 整体包围盒 65.18 × 48.10 × 20.14 mm（含支架和舵盘）
- **输出轴方向 = +Y**，轴心在 **(X = 10.0, Z = 0.0)**，轴端是 **⌀6 mm** 的 25T 花键
  （+Y 面薄片实测：跨距 5.99 × 5.99，中心 (9.97, 0.01)，与齿轮组中心 X=10 相互印证）
- 机壳本体 40 × 19 × 20，属**矮身**舵机，不是常规 40 × 20 × 40.5 标准舵机

> 注意：`DS3115 / DS3120 / DS3135 / DS3218 / DS3225 / DS3230 / DS3235 / DS3240`
> 这 8 个文件字节数完全一致（4,596,389），是**同一份模型**，只是改了文件名。
> 想按型号区分尺寸的话，这几个都不作数。

### 换一个舵机怎么定参数

1. `--analyze --parts` 看清零件构成 → `--drop` 掉支架 / 舵盘 / 线套
2. 看 `各面外缘薄片分布`：哪个方向出现**半径 3mm 左右的小圆**，那就是输出轴朝向；
   小圆的 `中心` 就是轴心的另外两轴坐标
3. `--shaft` 填该方向，`--pivot` 填 `<轴向坐标>,<轴心>`
