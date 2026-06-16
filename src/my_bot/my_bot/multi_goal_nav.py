#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped
import time


class MultiGoalNavigator(Node):

    def __init__(self):
        super().__init__('multi_goal_navigator')
        self.client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # 🎯 Define delivery points
        self.goals = [
            (37.0, -12.0),   # Point 1
            (37.5, -12.5),   # Point 2
            (36.8, -11.8),   # Point 3
        ]

    def send_goal(self, x, y):
        goal_msg = NavigateToPose.Goal()

        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.orientation.w = 1.0

        self.client.wait_for_server()

        self.get_logger().info(f'🚀 Going to ({x}, {y})')

        future = self.client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, future)

        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().info('❌ Goal rejected')
            return False

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)

        self.get_logger().info('✅ Reached goal!')
        return True

    def run(self):
        for x, y in self.goals:
            success = self.send_goal(x, y)
            if not success:
                break
            time.sleep(2)


def main(args=None):
    rclpy.init(args=args)
    node = MultiGoalNavigator()
    node.run()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
