from launch import LaunchDescription
from launch.actions import TimerAction, IncludeLaunchDescription
from launch_ros.actions import Node
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():

    pkg_path = get_package_share_directory('my_bot')

    urdf_path = os.path.join(pkg_path, 'urdf', 'my_bot.urdf')
    world = '/opt/ros/humble/share/turtlebot3_gazebo/worlds/turtlebot3_world.world'

    return LaunchDescription([

  IncludeLaunchDescription(
    PythonLaunchDescriptionSource(
        os.path.join(
            get_package_share_directory('gazebo_ros'),
            'launch',
            'gazebo.launch.py'
        )
    ),
    launch_arguments={
        'world': world,
        'extra_gazebo_args': '-s libgazebo_ros_factory.so'
    }.items(),
),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            arguments=[urdf_path],
            parameters=[{'use_sim_time': True}],
            output='screen'
        ),

        TimerAction(
            period=10.0,
            actions=[
                Node(
                    package='gazebo_ros',
                    executable='spawn_entity.py',
                    arguments=[
                        '-file', urdf_path,
                        '-entity', 'delivery_bot'
                    ],
                    output='screen'
                )
            ]
        ),
    ])
