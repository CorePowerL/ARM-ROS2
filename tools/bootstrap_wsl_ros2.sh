#!/usr/bin/env bash
# ============================================================================
# K3B 六轴舵机机械臂 · WSL2 一键仿真环境
# ============================================================================
# 在 WSL 的 Ubuntu 24.04 里跑这一条，装完 ROS 2 Jazzy + MoveIt + 建好工作空间 +
# 编译。全程幂等：重复跑只会补缺，不会重装。
#
#   bash tools/bootstrap_wsl_ros2.sh            # 只装环境，不启动
#   bash tools/bootstrap_wsl_ros2.sh --launch    # 装完直接起 RViz 仿真
#   bash tools/bootstrap_wsl_ros2.sh --check     # 装完只跑配置自检
#
# 换工作空间位置：K3B_WS=~/my_ws bash tools/bootstrap_wsl_ros2.sh
#
# 为什么需要 Ubuntu 24.04：Jazzy 只发 noble；22.04 上只有 Humble，本包的
# launch / moveit_configs_utils 写法是 Jazzy 的。
# ============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${K3B_WS:-$HOME/k3b_ws}"
PKGS=(k3b_arm_urdf k3b_arm_moveit_config)
MODE="${1:-}"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
ok()   { printf "    \033[1;32m%s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31m[x] %s\033[0m\n" "$*" >&2; exit 1; }

# --- 0. 环境体检 ------------------------------------------------------------
step "0/6 环境体检"

[ -f /etc/os-release ] || die "这不是 Linux"
. /etc/os-release
if [ "${VERSION_CODENAME:-}" != "noble" ]; then
  die "需要 Ubuntu 24.04 (noble)，当前是 ${VERSION_CODENAME:-未知}。
    22.04 只能装 Humble，本包用的是 Jazzy 的 API。请装 Ubuntu-24.04。"
fi
ok "Ubuntu ${VERSION_ID} (${VERSION_CODENAME})"

if [ -d /mnt/wslg ]; then
  ok "WSLg 就绪 —— RViz 窗口会直接弹出来"
else
  warn "没检测到 /mnt/wslg：RViz 可能开不了窗口。
    在 Windows 里执行 wsl --update，然后 wsl --shutdown 重开。"
fi

ARCH="$(dpkg --print-architecture)"
ok "架构 ${ARCH}$( [ "$ARCH" = "arm64" ] && echo ' （ARM64：MoveIt 包更少，装不上就看 README 第九节）' || true )"

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

# --- 1. ROS 2 apt 源 --------------------------------------------------------
step "1/6 配置 ROS 2 apt 源"

if [ -f /usr/share/keyrings/ros-archive-keyring.gpg ]; then
  ok "keyring 已存在，跳过"
else
  $SUDO install -d -m 0755 /usr/share/keyrings
  curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    | $SUDO tee /usr/share/keyrings/ros-archive-keyring.gpg > /dev/null
  ok "已导入 ROS 官方 GPG key"
fi

if [ -f /etc/apt/sources.list.d/ros2.list ]; then
  ok "ros2.list 已存在，跳过"
else
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo "$UBUNTU_CODENAME") main" \
    | $SUDO tee /etc/apt/sources.list.d/ros2.list > /dev/null
  ok "已写入 /etc/apt/sources.list.d/ros2.list"
fi

$SUDO apt-get update -qq

# --- 2. 装包 ----------------------------------------------------------------
step "2/6 安装 ROS 2 Jazzy + MoveIt（约 2 GB，首次约 5–15 分钟）"

PACKAGES=(
  ros-jazzy-desktop                 # 含 RViz2
  ros-jazzy-moveit
  ros-jazzy-ros2-control
  ros-jazzy-ros2-controllers
  ros-jazzy-joint-state-publisher
  ros-jazzy-joint-state-publisher-gui
  ros-dev-tools                     # colcon 等编译工具
  python3-colcon-common-extensions
  python3-numpy python3-yaml        # tools/check_moveit_config.py 要用
)

# 已经装上的就别让 apt 再算一遍
MISSING=()
for p in "${PACKAGES[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p")
done

if [ ${#MISSING[@]} -eq 0 ]; then
  ok "全部已安装，跳过"
else
  printf "    待装 %d 个：%s\n" "${#MISSING[@]}" "${MISSING[*]}"
  $SUDO apt-get install -y "${MISSING[@]}"
  ok "安装完成"
fi

# --- 3. rosdep --------------------------------------------------------------
step "3/6 初始化 rosdep"

$SUDO rosdep init >/dev/null 2>&1 || true
if rosdep update >/dev/null 2>&1; then
  ok "rosdep 就绪"
else
  warn "rosdep update 失败（多半是网络）。本包没有外部依赖，不影响编译。"
fi

# --- 4. 工作空间 ------------------------------------------------------------
step "4/6 建工作空间 ${WS}"

mkdir -p "$WS/src"
for p in "${PKGS[@]}"; do
  if [ ! -d "$REPO/$p" ]; then
    die "找不到包目录：$REPO/$p"
  fi
  ln -sfn "$REPO/$p" "$WS/src/$p"
  ok "软链 $p → $WS/src/$p"
done

if [ ! -f /opt/ros/jazzy/setup.bash ]; then
  die "/opt/ros/jazzy/setup.bash 不存在 —— 上一步装包没成功，看上面的 apt 报错"
fi
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash

# --- 5. 编译 ----------------------------------------------------------------
step "5/6 colcon build"
cd "$WS"
# --symlink-install：install/ 里是指回源码的软链，Windows 侧改 yaml/srdf 后
# 重新 build 只需几秒，不用重编
colcon build --symlink-install
ok "编译完成"

# --- 6. 收尾 ----------------------------------------------------------------
step "6/6 自检"

# shellcheck disable=SC1091
source "$WS/install/setup.bash"

cd "$REPO"
if python3 tools/check_moveit_config.py; then
  ok "MoveIt 配置一致性检查通过"
else
  warn "配置自检报错，先按上面的提示改，再 launch"
fi

MARK="# >>> k3b_arm ros2 >>>"
if ! grep -q "$MARK" "$HOME/.bashrc" 2>/dev/null; then
  {
    echo ""
    echo "$MARK"
    echo "source /opt/ros/jazzy/setup.bash"
    echo "source $WS/install/setup.bash"
    echo "# <<< k3b_arm ros2 <<<"
  } >> "$HOME/.bashrc"
  ok "已把 source 写进 ~/.bashrc（新终端自动生效）"
else
  ok "~/.bashrc 已有 source，跳过"
fi

cat <<EOF

────────────────────────────────────────────────────────────────
  装好了。以后每次开新终端的固定动作就一句：

      ros2 launch k3b_arm_moveit_config demo.launch.py

  RViz 里：左下 MotionPlanning → Planning Group 选 arm
           → Goal State 选 ready → Plan → Execute

  demo 用的是 mock 硬件（位置指令直接当状态回读），
  不接任何实机、不需要 Gazebo，「动」是纯运动学算出来的。
────────────────────────────────────────────────────────────────
EOF

case "$MODE" in
  --launch)
    step "启动 RViz 仿真"
    exec ros2 launch k3b_arm_moveit_config demo.launch.py
    ;;
  --check)
    exit 0
    ;;
  *)
    echo "加 --launch 可以直接起来。"
    ;;
esac
