#!/usr/bin/env bash
# ============================================================================
# K3B 六轴舵机机械臂 · 一键仿真环境（Ubuntu 24.04，任意平台）
# ============================================================================
# 在 Ubuntu 24.04 里跑这一条，装完 ROS 2 Jazzy + MoveIt + 建好工作空间 + 编译。
# 全程幂等：重复跑只会补缺，不会重装。
#
#   bash tools/bootstrap_ros2.sh            # 只装环境，不启动
#   bash tools/bootstrap_ros2.sh --launch    # 装完直接起 RViz 仿真
#   bash tools/bootstrap_ros2.sh --check     # 装完只跑配置自检
#
# 换工作空间位置：K3B_WS=~/my_ws bash tools/bootstrap_ros2.sh
#
# 适用平台：VMware / VirtualBox / WSL2 / 物理机 —— 只要发行版是 Ubuntu 24.04。
# 为什么必须 24.04：Jazzy 只发 noble；22.04 只有 Humble，本包 launch 与
# moveit_configs_utils 的写法是 Jazzy 的。
#
# 为什么不能用 openEuler / CentOS / Debian：
#   它们没有 ros-jazzy-* 的 apt 包，只能源码编译整个桌面栈 + MoveIt。
#   源码编译 ROS 2 Desktop 光 build 目录就要 15 GB 以上，MoveIt 再翻倍，
#   在 4 GB 内存 / 20 GB 磁盘的虚拟机上不可能完成。请换 Ubuntu 24.04。
# ============================================================================
set -euo pipefail

WS="${K3B_WS:-$HOME/k3b_ws}"
PKGS=(k3b_arm_urdf k3b_arm_moveit_config)
REPO_URL="${K3B_REPO_URL:-https://github.com/CorePowerL/ARM-ROS2.git}"
MODE="${1:-}"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
ok()   { printf "    \033[1;32m%s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m[!] %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31m[x] %s\033[0m\n" "$*" >&2; exit 1; }

# --- 0. 环境体检 ------------------------------------------------------------
step "0/7 环境体检"

[ -f /etc/os-release ] || die "这不是 Linux"
. /etc/os-release

# ID 必须转小写：openEuler 的 ID 就是字面量 "openEuler"（大写 E），
# 而 case 是大小写敏感的，直接用 ${ID} 会漏判成「未识别的发行版」。
ID_LC="$(printf '%s' "${ID:-}" | tr '[:upper:]' '[:lower:]')"
IDLIKE_LC="$(printf '%s' "${ID_LIKE:-}" | tr '[:upper:]' '[:lower:]')"
CODENAME="${VERSION_CODENAME:-}"

if [ "$ID_LC" = "ubuntu" ] && { [ "$CODENAME" = "noble" ] || [ "${VERSION_ID:-}" = "24.04" ]; }; then
  ok "Ubuntu ${VERSION_ID} (${CODENAME:-noble}) ✓ 正是 Jazzy 的目标平台"
elif [ "$ID_LC" = "ubuntu" ]; then
  die "需要 Ubuntu 24.04 (noble)，当前是 Ubuntu ${VERSION_ID} (${CODENAME:-?})。
    Jazzy 只发布 noble 的二进制包；${VERSION_ID} 上只有别的 ROS 版本，
    本包的 launch 与 moveit_configs_utils 写法是 Jazzy 的，直接跑会 import 失败。
    请装 Ubuntu 24.04 虚拟机（见 k3b_arm_moveit_config/README.md 第零节）。"
elif [ "$ID_LC" = "debian" ]; then
  die "当前是 ${PRETTY_NAME:-Debian}。Debian 没有 ros-jazzy-*（ROS 2 只对 Ubuntu 出二进制包），
    只能源码编译，桌面栈 build 目录 15 GB 起、几小时起步。
    正确做法：新建一台 Ubuntu 24.04 虚拟机。"
else
  case "$ID_LC $IDLIKE_LC" in
    *openeuler*|*centos*|*rhel*|*rocky*|*almalinux*|*fedora*)
      die "当前是 ${PRETTY_NAME:-$ID_LC}，没有 ros-jazzy-* 的二进制包。
    这是 RHEL 系发行版（用 dnf，不是 apt），ROS 2 Jazzy 只能从源码编译：
    桌面栈 build 目录 15 GB 起，MoveIt 再翻一倍，还要几小时到一整天 ——
    在虚拟机上基本不可行，而且 glibc/gcc 版本与 noble 有差异，坑很多。
    正确做法：新建一台 Ubuntu 24.04 虚拟机。
    见 k3b_arm_moveit_config/README.md 第零节的「A. VMware 新建 Ubuntu」。"
      ;;
    *)
      die "未识别的发行版：${PRETTY_NAME:-${ID_LC:-未知}}。需要 Ubuntu 24.04 (noble)。"
      ;;
  esac
fi

# 虚拟化平台 + 图形通路
VIRT="$(systemd-detect-virt 2>/dev/null || echo none)"
if [ -d /mnt/wslg ]; then
  PLATFORM="WSL2"; ok "平台 WSL2，WSLg 就绪 —— RViz 窗口会直接弹出"
elif [ "$VIRT" = "vmware" ]; then
  PLATFORM="VMware"; ok "平台 VMware 虚拟机"
elif [ "$VIRT" = "oracle" ]; then
  PLATFORM="VirtualBox"; ok "平台 VirtualBox 虚拟机"
else
  PLATFORM="bare-metal"; ok "平台 ${VIRT}（物理机或未知）"
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ ! -d /mnt/wslg ]; then
  warn "没有图形会话（DISPLAY / WAYLAND_DISPLAY 都为空）。
    现在能装能编译，但 RViz 起不来。请从桌面终端里跑，而不是 ssh 进来。"
fi

# 内存 —— move_group + RViz + 桌面 ≈ 2.5~3.5 GB，4 GB 会开始 swap
MEM_MB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
if   [ "$MEM_MB" -lt 3500 ]; then
  warn "内存只有 ${MEM_MB} MB，低于 3.5 GB。装包能过，但 RViz + move_group 会疯狂 swap。
    虚拟机请先关机（不是挂起），在设置里把内存调到 8 GB 再继续。"
elif [ "$MEM_MB" -lt 7000 ]; then
  warn "内存 ${MEM_MB} MB，偏紧但能跑。想让 RViz 流畅，建议调到 8 GB。
    改法：虚拟机必须【关机】（挂起状态改不了），设置 → 内存 → 8192 MB。"
else
  ok "内存 ${MEM_MB} MB，足够"
fi

# 磁盘 —— ROS 2 desktop + MoveIt 装完约 3 GB，apt 缓存峰值再 +1.5 GB
AVAIL_MB=$(df -Pm / | awk 'NR==2{print $4}')
if [ "$AVAIL_MB" -lt 6000 ]; then
  die "根分区只剩 $((AVAIL_MB/1024)) GB 可用，装不下。
    ROS 2 desktop + MoveIt 需要约 3 GB，加上 apt 缓存峰值共约 5 GB。
    请先扩容虚拟磁盘（VMware：设置 → 硬盘 → 扩展；20 GB 太小，建议 60 GB）。"
elif [ "$AVAIL_MB" -lt 12000 ]; then
  warn "根分区只剩 $((AVAIL_MB/1024)) GB。装完会剩约 $((AVAIL_MB/1024-4)) GB，够但不宽裕。
    脚本结束会自动 apt clean 清缓存。以后别在这台机器上装 Gazebo。"
else
  ok "磁盘剩余 $((AVAIL_MB/1024)) GB，充裕"
fi

CPU_N=$(nproc)
ok "CPU ${CPU_N} 核$( [ "$CPU_N" -lt 4 ] && echo '（编译会久一点，可提到 4 核）' || true )"

SUDO=""
# 不能写成 [ "$(id -u)" -ne 0 ] && SUDO="sudo" —— 在 root 下这条返回 1，
# set -e 会让脚本当场静默退出。必须用 if。
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

# --- 1. ROS 2 apt 源 --------------------------------------------------------
step "1/7 配置 ROS 2 apt 源"

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
step "2/7 安装 ROS 2 Jazzy + MoveIt（约 2 GB，首次约 5–15 分钟）"

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
  mesa-utils                        # glxinfo：确认 3D 加速真的生效
)

# VMware 虚拟机补 open-vm-tools-desktop：没它共享文件夹挂不上、分辨率不自适应；
# 已经在 Tools 停掉的状态下，RViz 的 OpenGL 也可能退化到软件渲染。
if [ "$PLATFORM" = "VMware" ]; then
  if dpkg -s open-vm-tools-desktop >/dev/null 2>&1; then
    ok "open-vm-tools-desktop 已装"
  else
    warn "VMware 客户机缺 open-vm-tools-desktop（宿主机日志显示 noTools）。
    这次一并装上：共享文件夹、分辨率自适应、剪贴板都靠它。"
    PACKAGES+=(open-vm-tools-desktop)
  fi
fi

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
  # 2 GB 的 deb 缓存在 20 GB 磁盘上不是小数目
  $SUDO apt-get clean
  ok "已清理 apt 缓存"
fi

# 3D 加速自检：llvmpipe 意味着软件渲染，RViz 会卡到不能用
if command -v glxinfo >/dev/null 2>&1; then
  RENDERER="$(glxinfo -B 2>/dev/null | awk -F': ' '/OpenGL renderer/{print $2; exit}')"
  if [ -n "${RENDERER:-}" ]; then
    case "$RENDERER" in
      *llvmpipe*|*softpipe*)
        warn "OpenGL 用的是软件渲染（$RENDERER），RViz 会很卡。
    VMware：虚拟机设置 → 显示器 → 勾上【加速 3D 图形】。
    WSL2：一般是显卡驱动没装好，或 wsl --update 到最新。" ;;
      *) ok "OpenGL renderer: $RENDERER" ;;
    esac
  fi
fi

# --- 3. rosdep --------------------------------------------------------------
step "3/7 初始化 rosdep"

$SUDO rosdep init >/dev/null 2>&1 || true
if rosdep update >/dev/null 2>&1; then
  ok "rosdep 就绪"
else
  warn "rosdep update 失败（多半是网络）。本包没有外部依赖，不影响编译。"
fi

# --- 4. 找仓库 --------------------------------------------------------------
step "4/7 定位仓库"

find_repo() {
  local d
  # 脚本自己在仓库里（tools/ 的上一级）
  d="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
  if [ -d "$d/k3b_arm_urdf" ]; then echo "$d"; return 0; fi
  # 常见位置
  for d in "$HOME/ARM-ROS2" "$HOME/k3b_ws/src/ARM-ROS2" "$PWD"; do
    if [ -d "$d/k3b_arm_urdf" ]; then echo "$d"; return 0; fi
  done
  return 1
}

if REPO="$(find_repo)"; then
  ok "仓库：$REPO"
else
  warn "当前目录不是这个仓库，自动 clone 一份到 $HOME/ARM-ROS2"
  git clone "$REPO_URL" "$HOME/ARM-ROS2"
  REPO="$HOME/ARM-ROS2"
  ok "已 clone"
fi

# 共享文件夹上的仓库：能读能编，但 hgfs 的权限语义和 ext4 不同，
# cmake 偶尔会抱怨，而且编译产物仍写在 ws 里，不会污染 Windows 侧。
case "$REPO" in
  /mnt/hgfs/*)
    warn "仓库在 VMware 共享文件夹上（$REPO）。
    可以编译，但文件权限是按挂载参数统一映射的。若 colcon 报权限错，
    改在 VM 里 clone 一份：git clone $REPO_URL ~/ARM-ROS2" ;;
  /mnt/[a-z]/*)
    warn "仓库在 Windows 挂载盘上（$REPO），编译会明显变慢。
    这只是 src 的软链源，编译产物写在 $WS，不会弄脏仓库。" ;;
esac

# --- 5. 工作空间 ------------------------------------------------------------
step "5/7 建工作空间 ${WS}"

mkdir -p "$WS/src"
for p in "${PKGS[@]}"; do
  [ -d "$REPO/$p" ] || die "找不到包目录：$REPO/$p（仓库不完整？）"
  ln -sfn "$REPO/$p" "$WS/src/$p"
  ok "软链 $p → $WS/src/$p"
done

[ -f /opt/ros/jazzy/setup.bash ] || die "/opt/ros/jazzy/setup.bash 不存在 —— 第 2 步装包没成功，看上面的 apt 报错"
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash

# --- 6. 编译 ----------------------------------------------------------------
step "6/7 colcon build"

cd "$WS"
# --symlink-install：install/ 里是指回源码的软链，改 yaml/srdf 后重新 build
# 只需几秒，不用重编
colcon build --symlink-install
ok "编译完成"

# --- 7. 收尾 ----------------------------------------------------------------
step "7/7 自检"

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
