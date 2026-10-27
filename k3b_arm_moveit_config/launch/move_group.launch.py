#!/usr/bin/env python3
"""
K3B 机械臂 · 只起 MoveIt（不带任何控制器）
=============================================================================
什么时候用这个而不是 demo.launch.py：
  · 已经自己起好了控制器（实机驱动、另一个 launch、外部仿真），
    只要 MoveIt 的规划 + 执行能力
  · 只想看规划、不想让 mock 硬件参与

它起的东西：
  robot_state_publisher  纯模型版 URDF（k3b_arm.urdf.xacro，不带 ros2_control 标签）
  move_group             规划 + 接收轨迹投递
  rviz2                  MotionPlanning 面板（可关）

⚠ 前提：环境里必须已经有 /joint_states 发布者，且 moveit_controllers.yaml
  里配置的 controller（k3b_arm_controller / k3b_gripper_controller）已经在跑，
  否则 MoveIt 能规划但点 Execute 会报 "no controller found"。

接实机的典型用法（阶段 5 之后的架构）：
  终端 1：你自己的硬件接口（ros2_control SystemInterface 或串口节点）
  终端 2：ros2 launch k3b_arm_moveit_config move_group.launch.py
=============================================================================
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    pkg_share = get_package_share_directory("k3b_arm_moveit_config")
    urdf_share = get_package_share_directory("k3b_arm_urdf")

    # 默认用纯模型版；要带 ros2_control 接口就传 urdf:=<另一条 xacro 路径>
    default_urdf = os.path.join(urdf_share, "k3b_arm.urdf.xacro")

    urdf_arg = DeclareLaunchArgument(
        "urdf",
        default_value=default_urdf,
        description="URDF / xacro 路径（默认纯模型版，不带 ros2_control）",
    )
    rviz_arg = DeclareLaunchArgument(
        "rviz",
        default_value="true",
        description="是否启动 RViz",
    )
    rviz_config_arg = DeclareLaunchArgument(
        "rviz_config",
        default_value=os.path.join(pkg_share, "config", "moveit.rviz"),
        description="RViz 配置文件",
    )

    # xacro 路径来自 launch 参数，所以这里不能用 MoveItConfigsBuilder 的
    # 自动收集，要显式把 robot_description 换掉
    robot_description = {
        "robot_description": ParameterValue(
            Command(
                [
                    PathJoinSubstitution([FindExecutable(name="xacro")]),
                    " ",
                    LaunchConfiguration("urdf"),
                ]
            ),
            value_type=str,
        )
    }

    moveit_config = (
        MoveItConfigsBuilder("k3b_arm", package_name="k3b_arm_moveit_config")
        .robot_description(file_path=default_urdf)
        .to_moveit_configs()
    )

    rsp = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[robot_description],
    )

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {
                "publish_robot_description_semantic": True,
                "allow_trajectory_execution": True,
                "capabilities": "move_group/ExecuteTaskSolutionCapability",
            },
        ],
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", LaunchConfiguration("rviz_config")],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
        ],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    return LaunchDescription([urdf_arg, rviz_arg, rviz_config_arg, rsp, move_group, rviz])
