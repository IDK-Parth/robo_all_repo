from setuptools import setup, find_packages

package_name = 'my_bot'

setup(
    name=package_name,
    version='0.0.0',
    packages=['my_bot'],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/my_bot']),
        ('share/my_bot', ['package.xml']),
        ('share/my_bot/launch', ['launch/display.launch.py']),
        ('share/my_bot/urdf', ['urdf/my_bot.urdf']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='mansha',
    maintainer_email='mansha@example.com',
    description='Delivery bot with voice control',
    license='Apache License 2.0',
    tests_require=['pytest'],
entry_points={
    'console_scripts': [
        'move_robot = my_bot.move_robot:main',
        'imu_odom = my_bot.imu_odom:main',
        'multi_goal_nav = my_bot.multi_goal_nav:main',
        'voice_control = my_bot_voice.main:main',
        'voice_listener = my_bot.voice_listener:main',
    ],
},
)
