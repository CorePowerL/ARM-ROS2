cmake_minimum_required(VERSION 3.8)
project(k3b_arm_urdf)

find_package(ament_cmake REQUIRED)

# 模型 / 网格 / 配置文件整体安装，供 package://k3b_arm_urdf/... 解析
install(DIRECTORY meshes launch config
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)
install(FILES k3b_arm.urdf k3b_arm.urdf.xacro
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)

ament_package()
