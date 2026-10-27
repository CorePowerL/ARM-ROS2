cmake_minimum_required(VERSION 3.8)
project(k3b_arm_urdf)

find_package(ament_cmake REQUIRED)

# 模型 / 网格 / 配置文件整体安装，供 package://k3b_arm_urdf/... 解析
install(DIRECTORY meshes launch config ros2_control
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)
# k3b_arm_sim.urdf.xacro 用相对路径 include 同目录的 k3b_arm.urdf.xacro
# 与 ros2_control/ 下的文件，所以三者必须装到同一层，不能分开
install(FILES k3b_arm.urdf k3b_arm.urdf.xacro k3b_arm_sim.urdf.xacro
  DESTINATION share/${PROJECT_NAME}
  OPTIONAL
)

ament_package()
