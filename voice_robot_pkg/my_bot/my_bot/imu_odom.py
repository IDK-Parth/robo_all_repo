#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
import tf2_ros
import math

class OdomNode(Node):
    def __init__(self):
        super().__init__('odom_node')

        self.pub = self.create_publisher(Odometry, '/odom', 10)
        self.br = tf2_ros.TransformBroadcaster(self)

        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0

        self.linear_velocity = 0.5

        self.last_time = self.get_clock().now()

        # 🔥 THIS KEEPS NODE ALIVE
        self.timer = self.create_timer(0.1, self.update)

    def update(self):
        current_time = self.get_clock().now()
        dt = (current_time - self.last_time).nanoseconds / 1e9
        self.last_time = current_time

        # simple forward motion
        self.x += self.linear_velocity * math.cos(self.theta) * dt
        self.y += self.linear_velocity * math.sin(self.theta) * dt
        self.theta += 1.5 * dt
        # publish odom
        odom = Odometry()
        odom.header.stamp = current_time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y

        self.pub.publish(odom)

        # publish TF
        t = TransformStamped()
        t.header.stamp = current_time.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'

        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.rotation.w = 1.0

        self.br.sendTransform(t)


def main(args=None):
    rclpy.init(args=args)
    node = OdomNode()
    rclpy.spin(node)   
    node.destroy_node()
    rclpy.shutdown()
    
if __name__ == '__main__':
    main()    
