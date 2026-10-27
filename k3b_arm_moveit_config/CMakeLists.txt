cmake_minimum_required(VERSION 3.8)
project(k3b_arm_moveit_config)

find_package(ament_cmake REQUIRED)

# 纯配置文件包：config / launch 整体安装
install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
