from setuptools import setup
import os
from glob import glob

package_name = 'my_bot'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/urdf', glob('urdf/*')),
        ('share/' + package_name + '/worlds', glob('worlds/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='tanvi',
    maintainer_email='tanvi@example.com',
    description='Delivery bot',
    license='Apache License 2.0',
    entry_points={
        'console_scripts': [
            'move_robot = my_bot.move_robot:main',
            'imu_odom = my_bot.imu_odom:main',
            'multi_goal_nav = my_bot.multi_goal_nav:main',
        ],
    },
)
