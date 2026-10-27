#!/usr/bin/env python3
"""
K3B 机械臂 · MoveIt 2 demo
=============================================================================
不开实机、不要 Gazebo，纯 RViz 里跑通「设目标 → 规划 → Execute → 臂动」。

起了什么
--------
  robot_state_publisher   URDF（k3b_arm_sim.urdf.xacro，带 ros2_control 接口）
  ros2_control_node       mock_components/GenericSystem —— 把位置指令当成真实状态
  joint_state_broadcaster 把 6 个主动关节的状态发到 /joint_states
  k3b_arm_controller      JointTrajectoryController，5 个臂关节
  k3b_gripper_controller  JointTrajectoryController，夹爪 1 个关节
  move_group              MoveIt 规划节点
  rviz2                   带 MotionPlanning 面板

夹爪那 5 个四连杆从动件不在 ros2_control 里，由 robot_state_publisher 按
URDF 的 <mimic> 推算 TF —— 所以拖夹爪滑块时两指会联动开合。

用法
----
  ros2 launch k3b_arm_moveit_config demo.launch.py

  想手动拖关节看模型（跳过 MoveIt）：
  ros2 launch k3b_arm_moveit_config demo.launch.py use_joint_state_gui:=true

  RViz 里姿势太丑想重开：
  ros2 launch k3b_arm_moveit_config demo.launch.py rviz_config:=/path/to/other.rviz
=============================================================================
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare

from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    pkg_share = get_package_share_directory("k3b_arm_moveit_config")
    urdf_share = get_package_share_directory("k3b_arm_urdf")

    # ROS 侧的 xacro 路径（装到 share/ 之后的位置）
    sim_xacro = os.path.join(urdf_share, "k3b_arm_sim.urdf.xacro")

    # ------------------------------------------------------------------
    # robot_description：走 xacro，不是直接读 .urdf
    # ParameterValue(..., value_type=str) 不能省 —— 否则 ros2 launch 会把
    # 这一大串 XML 当成 YAML 去解析，碰到 ":" 直接炸。
    # ------------------------------------------------------------------
    robot_description = {
        "robot_description": ParameterValue(
            Command(
                [
                    PathJoinSubstitution([FindExecutable(name="xacro")]),
                    " ",
                    sim_xacro,
                ]
            ),
            value_type=str,
        )
    }

    # ------------------------------------------------------------------
    # MoveIt 配置：SRDF / kinematics / joint_limits / ompl / controllers
    # 都按 config/ 下的文件名自动收集，新增 yaml 会自己进来。
    # robot_description 显式指定到 urdf 包里 —— 模型和 MoveIt 配置是两个包。
    # ------------------------------------------------------------------
    moveit_config = (
        MoveItConfigsBuilder("k3b_arm", package_name="k3b_arm_moveit_config")
        .robot_description(file_path=sim_xacro)
        .to_moveit_configs()
    )

    # ------------------------------------------------------------------
    # 启动参数
    # ------------------------------------------------------------------
    rviz_config_arg = DeclareLaunchArgument(
        "rviz_config",
        default_value=os.path.join(pkg_share, "config", "moveit.rviz"),
        description="RViz 配置文件",
    )
    use_rviz_arg = DeclareLaunchArgument(
        "rviz",
        default_value="true",
        description="是否启动 RViz（无头调试时设 false）",
    )
    use_gui_arg = DeclareLaunchArgument(
        "use_joint_state_gui",
        default_value="false",
        description="额外起 joint_state_publisher_gui 手动拖关节（会和 ros2_control 抢 /joint_states，仅在调试模型时用）",
    )
    ros2_control_config_arg = DeclareLaunchArgument(
        "ros2_control_config",
        default_value=os.path.join(pkg_share, "config", "ros2_control_demo.yaml"),
        description="controller_manager 参数文件",
    )

    # ------------------------------------------------------------------
    # 1) 状态发布
    # ------------------------------------------------------------------
    rsp = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[robot_description, {"use_sim_time": False}],
    )

    # ------------------------------------------------------------------
    # 2) mock 硬件 + 控制器
    #    update_rate 在 ros2_control_demo.yaml 里（100Hz）
    # ------------------------------------------------------------------
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        output="screen",
        parameters=[
            robot_description,
            LaunchConfiguration("ros2_control_config"),
        ],
    )

    jsb_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "--controller-manager-timeout", "30"],
        output="screen",
    )

    arm_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["k3b_arm_controller", "--controller-manager-timeout", "30"],
        output="screen",
    )

    gripper_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["k3b_gripper_controller", "--controller-manager-timeout", "30"],
        output="screen",
    )

    # 先起 broadcaster 再起 controller：controller 激活时要靠 /joint_states
    # 把起始位置读进来，顺序反了会先用全 0 起、然后跳一下
    delayed_controllers = TimerAction(
        period=3.0,
        actions=[jsb_spawner, arm_controller_spawner, gripper_controller_spawner],
    )

    # ------------------------------------------------------------------
    # 3) MoveIt
    # ------------------------------------------------------------------
    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {
                # RViz 需要语义描述才能在 MotionPlanning 面板里列出规划组
                "publish_robot_description_semantic": True,
                "allow_trajectory_execution": True,
                "capabilities": "move_group/ExecuteTaskSolutionCapability",
            },
        ],
    )

    # ------------------------------------------------------------------
    # 4) RViz
    #    RViz 必须拿到 robot_description + SRDF + kinematics，
    #    否则 MotionPlanning 面板是灰的
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 5) 可选：手动拖关节（纯看模型用）
    # ------------------------------------------------------------------
    jsp_gui = Node(
        package="joint_state_publisher_gui",
        executable="joint_state_publisher_gui",
        condition=IfCondition(LaunchConfiguration("use_joint_state_gui")),
    )

    return LaunchDescription(
        [
            rviz_config_arg,
            use_rviz_arg,
            use_gui_arg,
            ros2_control_config_arg,
            rsp,
            ros2_control_node,
            delayed_controllers,
            move_group,
            rviz,
            jsp_gui,
        ]
    )
