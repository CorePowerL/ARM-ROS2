@echo off
chcp 65001 >nul
setlocal
title K3B Arm - MoveIt 2 仿真

set "DISTRO=Ubuntu-24.04"

rem ---- 定位仓库根目录（本文件在 tools\ 下）----
pushd "%~dp0.." 2>nul || (echo 找不到仓库根目录 & pause & exit /b 1)
set "REPO=%CD%"
popd

echo ============================================================
echo   K3B 机械臂 - MoveIt 2 仿真（WSL2 通道）
echo   仓库: %REPO%
echo ============================================================
echo.

rem ---- 检查 WSL 里有没有这个发行版（用 echo 探测，避开 wsl -l 的 UTF-16 输出）----
wsl.exe -d %DISTRO% -- echo probe >nul 2>&1
if errorlevel 1 goto :nodistro

echo [1/2] 正在进入 %DISTRO%（首次会先装环境，约 5-15 分钟）...
echo       装完后 RViz 窗口会自动弹出来。
echo.
wsl.exe -d %DISTRO% --cd "%REPO%" -- bash tools/bootstrap_ros2.sh --launch
if errorlevel 1 (
  echo.
  echo [!] 出错了，往上翻看报错信息。
  pause
)
exit /b 0

:nodistro
echo [!] WSL 里还没有 %DISTRO%。
echo.
echo   ---------------------------------------------------------------
echo   如果你用的是 VMware / VirtualBox 里的 Ubuntu 虚拟机：
echo     本文件用不上。请在虚拟机终端里执行：
echo.
echo         git clone https://github.com/CorePowerL/ARM-ROS2.git ~/ARM-ROS2
echo         bash ~/ARM-ROS2/tools/bootstrap_ros2.sh --launch
echo.
echo   如果你想走 WSL2 通道（不用另外装虚拟机）：
echo     在【管理员 PowerShell】里执行下面这一条，装完重启电脑：
echo.
echo         wsl --install -d Ubuntu-24.04
echo.
echo     重启后先从开始菜单打开一次 Ubuntu，设好 Linux 用户名和密码，
echo     之后再双击本文件，剩余步骤全自动。
echo   ---------------------------------------------------------------
echo.
choice /c YN /m "现在就执行 wsl --install 吗"
if errorlevel 2 exit /b 0

powershell -NoProfile -Command "Start-Process wsl.exe -ArgumentList '--install','-d','Ubuntu-24.04' -Verb RunAs"
echo.
echo 已在新窗口里开始安装。
echo 装完重启电脑 - 打开一次 Ubuntu 设用户名密码 - 再双击本文件。
pause
exit /b 0
