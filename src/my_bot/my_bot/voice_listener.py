#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import os

FILE_PATH = "/mnt/c/Users/manto/OneDrive/Desktop/command.txt"


class VoiceListener(Node):
    def __init__(self):
        super().__init__('voice_listener')

        self.publisher = self.create_publisher(String, '/voice_command', 10)
        self.last_text = ""

        self.timer = self.create_timer(1.0, self.check_file)

    def check_file(self):
        if os.path.exists(FILE_PATH):
            with open(FILE_PATH, 'r') as f:
                text = f.read().strip().lower()

            # ✅ Only send NEW command
            if text and text != self.last_text:
                msg = String()
                msg.data = text
                self.publisher.publish(msg)

                self.get_logger().info(f"Published: {text}")
                self.last_text = text

                # 🛑 Clear file after sending
                with open(FILE_PATH, 'w') as f:
                    f.write("")


def main():
    rclpy.init()
    node = VoiceListener()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
