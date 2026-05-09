import cv2
import torch
import serial
import time
import threading
import queue
from ultralytics import YOLO
from enum import Enum
from typing import List, Tuple, Optional
from flask import Flask, Response, render_template_string
import pyttsx3
import os


# ============ CONFIGURATION ============
CONFIG = {
    'model_path': 'yolo11n.pt',
    'camera_id': 0,
    'resolution': (640, 480),
    'conf_threshold': 0.6,
    'danger_zone': (0.33, 0.66),  # Middle third
    'proximity_threshold': 0.15,   # 15% of frame area
    'motor_mode': 'mock',          # 'mock' or 'serial'
    'serial_port': '/dev/ttyUSB0',  # Linux/Mac: /dev/ttyUSB0, Windows: COM3
    'web_port': 5000,              # Open mobile browser to laptop_ip:5000
    'voice_cooldown': 3            # Seconds between voice alerts
}


# ============ ENUMS ============
class Movement(Enum):
    STOP = "STOP"
    FORWARD = "FORWARD"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


# ============ VOICE SYSTEM ============
class VoiceController:
    def __init__(self):
        self.tts_queue = queue.Queue()
        self.last_speak_time = 0
        self.cooldown = CONFIG['voice_cooldown']
        self.running = True
        
        # Start TTS thread
        self.thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.thread.start()
    
    def _tts_worker(self):
        """Background thread for text-to-speech to avoid blocking"""
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)  # Speed
        engine.setProperty('volume', 0.9)
        
        while self.running:
            try:
                text = self.tts_queue.get(timeout=1)
                engine.say(text)
                engine.runAndWait()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Voice] Error: {e}")
    
    def speak(self, text: str):
        """Thread-safe speak with cooldown"""
        current_time = time.time()
        if current_time - self.last_speak_time > self.cooldown:
            self.tts_queue.put(text)
            self.last_speak_time = current_time
            print(f"[Voice] Queued: '{text}'")
    
    def alert_obstacle(self):
        self.speak("Please move aside")
    
    def stop(self):
        self.running = False


# ============ VISION SYSTEM ============
class VisionSystem:
    def __init__(self):
        self.model = YOLO(CONFIG['model_path'])
        self.cap = cv2.VideoCapture(CONFIG['camera_id'])
        
        # Optimize for performance
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG['resolution'][0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG['resolution'][1])
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # Warm up
        dummy = torch.zeros((1, 3, 640, 480))
        self.model.predict(dummy, verbose=False)
        
        self.frame_width = CONFIG['resolution'][0]
        self.frame_height = CONFIG['resolution'][1]
        self.current_frame = None
        self.current_detections = []
        
        print(f"[Vision] Camera initialized at {self.frame_width}x{self.frame_height}")
    
    def update(self):
        """Single update cycle - call this in main loop"""
        ret, frame = self.cap.read()
        if not ret:
            return False
        
        # Mirror for intuitive control
        frame = cv2.flip(frame, 1)
        
        # Inference
        results = self.model(frame, verbose=False, stream=True)
        
        detections = []
        for result in results:
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf < CONFIG['conf_threshold']:
                    continue
                
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                area = (x2 - x1) * (y2 - y1)
                
                detections.append({
                    'class': int(box.cls[0]),
                    'conf': conf,
                    'bbox': (x1, y1, x2, y2),
                    'center': (cx, cy),
                    'area': area,
                    'name': result.names[int(box.cls[0])]
                })
        
        # Draw debug info
        debug_frame = self._draw_debug(frame, detections)
        self.current_frame = debug_frame
        self.current_detections = detections
        
        return True
    
    def _draw_debug(self, frame, detections):
        """Draw danger zone and bounding boxes"""
        h, w = frame.shape[:2]
        dz_start = int(w * CONFIG['danger_zone'][0])
        dz_end = int(w * CONFIG['danger_zone'][1])
        
        # Danger zone overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (dz_start, 0), (dz_end, h), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        cv2.rectangle(frame, (dz_start, 0), (dz_end, h), (0, 0, 255), 2)
        cv2.putText(frame, "DANGER ZONE", (dz_start + 10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Draw detections
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cx, cy = map(int, det['center'])
            
            # Color: Red if in danger zone, Green if safe
            in_danger = CONFIG['danger_zone'][0] < (cx/w) < CONFIG['danger_zone'][1]
            color = (0, 0, 255) if in_danger else (0, 255, 0)
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
            label = f"{det['name']} {det['conf']:.2f}"
            cv2.putText(frame, label, (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return frame
    
    def get_frame_bytes(self):
        """Encode frame for web streaming"""
        if self.current_frame is None:
            return None
        ret, buffer = cv2.imencode('.jpg', self.current_frame)
        return buffer.tobytes() if ret else None
    
    def release(self):
        self.cap.release()


# ============ NAVIGATION LOGIC ============
class NavigationLogic:
    def __init__(self):
        self.frame_area = CONFIG['resolution'][0] * CONFIG['resolution'][1]
        self.proximity_px = CONFIG['proximity_threshold'] * self.frame_area
        self.last_decision = Movement.FORWARD
        self.decision_cooldown = 0
    
    def decide(self, detections: List[dict]) -> Tuple[Movement, bool]:
        """
        Returns: (Movement, obstacle_detected_bool)
        """
        if self.decision_cooldown > 0:
            self.decision_cooldown -= 1
            return self.last_decision, False
        
        obstacle_in_path = False
        largest_area = 0
        
        for det in detections:
            cx = det['center'][0]
            area = det['area']
            norm_x = cx / CONFIG['resolution'][0]
            
            # Check if in danger zone and close (large)
            if CONFIG['danger_zone'][0] < norm_x < CONFIG['danger_zone'][1]:
                if area > self.proximity_px:
                    obstacle_in_path = True
                    largest_area = max(largest_area, area)
        
        if obstacle_in_path:
            decision = Movement.LEFT  # Avoidance maneuver
            print(f"[Nav] OBSTACLE DETECTED (area: {largest_area:.0f}px) -> TURN LEFT")
        else:
            decision = Movement.FORWARD
            print("[Nav] PATH CLEAR -> FORWARD")
        
        self.last_decision = decision
        self.decision_cooldown = 3  # Smoothing
        return decision, obstacle_in_path


# ============ MOTOR CONTROLLER ============
class MotorController:
    def __init__(self):
        self.mode = CONFIG['motor_mode']
        self.current_cmd = Movement.STOP
        
        if self.mode == 'serial':
            try:
                self.ser = serial.Serial(CONFIG['serial_port'], 9600, timeout=1)
                time.sleep(2)
                print(f"[Motor] Serial connected on {CONFIG['serial_port']}")
            except Exception as e:
                print(f"[Motor] Serial failed: {e}, using MOCK mode")
                self.mode = 'mock'
        else:
            print("[Motor] MOCK mode (printing commands)")
    
    def command(self, movement: Movement):
        if movement == self.current_cmd:
            return
        
        self.current_cmd = movement
        cmd_map = {
            Movement.STOP: b'S',
            Movement.FORWARD: b'F',
            Movement.LEFT: b'L',
            Movement.RIGHT: b'R'
        }
        byte_cmd = cmd_map.get(movement, b'S')
        
        if self.mode == 'serial':
            try:
                self.ser.write(byte_cmd)
            except Exception as e:
                print(f"[Motor] Write error: {e}")
        else:
            print(f"[Motor] Command: {movement.value} ({byte_cmd})")
    
    def stop(self):
        self.command(Movement.STOP)
        if self.mode == 'serial':
            self.ser.close()


# ============ WEB SERVER (FOR MOBILE VIEWING) ============
class WebServer:
    def __init__(self, vision_system):
        self.app = Flask(__name__)
        self.vision = vision_system
        self.last_command = "INIT"
        
        @self.app.route('/')
        def index():
            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Autonomous Car Demo</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial; margin: 0; padding: 20px; background: #111; color: white; text-align: center; }
                    h1 { color: #0f0; }
                    .video { border: 3px solid #0f0; border-radius: 10px; max-width: 100%; }
                    .status { margin-top: 10px; padding: 10px; background: #222; border-radius: 5px; }
                    .danger { color: #f00; font-weight: bold; }
                    .safe { color: #0f0; font-weight: bold; }
                </style>
            </head>
            <body>
                <h1>🚗 Autonomous Car Live Feed</h1>
                <img src="/video_feed" class="video">
                <div class="status" id="status">Initializing...</div>
                <p>Red zone = Danger | Green boxes = Safe objects</p>
            </body>
            </html>
            ''')
        
        @self.app.route('/video_feed')
        def video_feed():
            def generate():
                while True:
                    frame_bytes = self.vision.get_frame_bytes()
                    if frame_bytes:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    time.sleep(0.033)  # ~30 FPS
            return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    
    def run(self):
        # Run Flask in thread so it doesn't block main loop
        thread = threading.Thread(
            target=self.app.run, 
            kwargs={'host': '0.0.0.0', 'port': CONFIG['web_port'], 'debug': False, 'use_reloader': False},
            daemon=True
        )
        thread.start()
        print(f"[Web] Server started! Open browser to:")
        print(f"[Web] http://localhost:{CONFIG['web_port']} (laptop)")
        try:
            import socket
            ip = socket.gethostbyname(socket.gethostname())
            print(f"[Web] http://{ip}:{CONFIG['web_port']} (mobile - same WiFi)")
        except:
            pass


# ============ MAIN CONTROLLER ============
class AutonomousCar:
    def __init__(self):
        print("=" * 50)
        print("AUTONOMOUS CAR SYSTEM STARTING")
        print("=" * 50)
        
        # Initialize all subsystems
        self.voice = VoiceController()
        self.vision = VisionSystem()
        self.navigator = NavigationLogic()
        self.motors = MotorController()
        self.web = WebServer(self.vision)
        
        self.running = False
        self.frame_count = 0
        self.start_time = time.time()
        
        # Start web server for mobile viewing
        self.web.run()
        
        print("[System] Ready! Press 'q' in OpenCV window to stop")
        print("[System] Or Ctrl+C in terminal")
        print("=" * 50)
    
    def run(self):
        self.running = True
        
        try:
            while self.running:
                # 1. Get vision
                if not self.vision.update():
                    break
                
                # 2. Decide movement
                detections = self.vision.current_detections
                movement, obstacle = self.navigator.decide(detections)
                
                # 3. Voice alert if obstacle
                if obstacle:
                    self.voice.alert_obstacle()
                
                # 4. Execute motor command
                self.motors.command(movement)
                
                # 5. Display local window (laptop)
                frame = self.vision.current_frame.copy()
                
                # Add HUD info
                fps = self.frame_count / (time.time() - self.start_time)
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.putText(frame, f"Action: {movement.value}", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if obstacle:
                    cv2.putText(frame, "VOICE: Please move aside!", (10, 90),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                cv2.imshow("Autonomous Car (Laptop View)", frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                self.frame_count += 1
                
        except KeyboardInterrupt:
            print("\n[Main] Stopped by user")
        finally:
            self.shutdown()
    
    def shutdown(self):
        print("[System] Shutting down...")
        self.running = False
        self.voice.stop()
        self.motors.stop()
        self.vision.release()
        cv2.destroyAllWindows()
        print("[System] Shutdown complete")


# ============ ENTRY POINT ============
if __name__ == "__main__":
    # Check dependencies
    try:
        import ultralytics
        import flask
    except ImportError:
        print("ERROR: Missing dependencies!")
        print("Run: pip install ultralytics opencv-python pyttsx3 flask pyserial torch")
        exit(1)
    
    # Check camera
    cap = cv2.VideoCapture(CONFIG['camera_id'])
    if not cap.isOpened():
        print("ERROR: Camera not found!")
        exit(1)
    cap.release()
    
    # Start system
    car = AutonomousCar()
    car.run()