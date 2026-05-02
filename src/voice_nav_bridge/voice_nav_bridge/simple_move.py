import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist

class Bridge(Node):
    def __init__(self):
        super().__init__('voice_nav_bridge')

        self.sub = self.create_subscription(
            String,
            '/voice_command',
            self.callback,
            10
        )

        self.pub = self.create_publisher(
            Twist,
            '/cmd_vel',
            10
        )

    def callback(self, msg):
        command = msg.data
        twist = Twist()

        if command == "room_101":
            twist.linear.x = 0.3   # move forward

        elif command == "room_102":
            twist.angular.z = 0.5  # turn left

        elif command == "room_103":
            twist.angular.z = -0.5 # turn right

        else:
            self.get_logger().info(f"Unknown command: {command}")
            return

        self.pub.publish(twist)
        self.get_logger().info(f"Executing: {command}")def callback(self, msg):
    command = msg.data
    twist = Twist()

    print(f"Received command: {command}")

    # Handle ANY room
    if "room" in command:
        twist.linear.x = 0.3   # move forward

    elif "medical_station" in command:
        twist.angular.z = 0.5  # turn

    else:
        self.get_logger().info(f"Unknown command: {command}")
        return

    self.pub.publish(twist)
    self.get_logger().info(f"Executing: {command}")
def main():
    rclpy.init()
    node = Bridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

