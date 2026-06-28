from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

import os

from ament_index_python.packages import get_package_share_directory

def generate_launch_description():

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    return LaunchDescription([

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
            ),
            launch_arguments={
                'slam': 'False',
                'use_sim_time': 'True',
                'map': '/home/manshacan/automated-delivery-bot/src/my_bot/maps/delivery_map.yaml',
                'params_file': '/home/manshacan/automated-delivery-bot/src/my_bot/config/nav2_params.yaml'
            }.items()
        )

    ])
