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

会打印每个分件的尺寸与归属，然后写出 `claw_body.stl` / `finger_left.stl` / `finger_right.stl`。
判据写在脚本头部（长薄板 = 指片，其余 = 壳体），换别的爪改那三个阈值即可。

## 从实测反解夹爪装配

```bash
python tools/solve_gripper.py
```

输入是卷尺量到的 4 个数（齿轮中心→爪尖 85/70mm、腕滚转输出→爪尖 110mm、全开内距 55mm），
输出 claw 网格该挂在哪、两指该转多少度、以及 `mimic multiplier` 应该取多少。
两指分别算出的转角比值会打印出来 —— 若接近 `-1` 就说明「一对啮合齿轮」的判断成立。

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
