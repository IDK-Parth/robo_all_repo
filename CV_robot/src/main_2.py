import cv2
import torch
import serial
import time
import threading
import queue
import json
import os
from datetime import datetime, timedelta
from collections import deque
from ultralytics import YOLO
from enum import Enum
from typing import List, Tuple, Dict
from flask import Flask, Response, render_template_string, jsonify
import pyttsx3
import numpy as np


# ============ CONFIGURATION ============
CONFIG = {
    'model_path': 'yolo11n.pt',
    'camera_id': 0,
    'resolution': (640, 480),
    'conf_threshold': 0.6,
    'danger_zone': (0.33, 0.66),
    'proximity_threshold': 0.15,
    'motor_mode': 'mock',          
    'serial_port': '/dev/ttyUSB0',  
    'web_port': 5000,
    'voice_cooldown': 2,           # Reduced to 2 seconds for more frequent alerts
    'voice_repeat_threshold': 5,   # After 5 seconds, say it more urgently
    'log_file': 'car_log.json',
    'csv_file': 'car_metrics.csv',
    'est_speed_mps': 0.5,          
    'save_interval': 30            
}


# ============ LOGGER CLASS ============
class MetricsLogger:
    def __init__(self):
        self.start_time = time.time()
        self.total_distance = 0.0          
        self.obstacles_detected = 0
        self.avoidance_maneuvers = 0
        self.voice_alerts = 0
        self.frames_processed = 0
        self.current_action = "INIT"
        self.last_position = (0, 0)        
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.obstacle_start_time = None    # Track how long obstacle present
        self.max_obstacle_duration = 0     # Longest continuous obstacle time
        
        self.fps_history = deque(maxlen=30)
        self.last_frame_time = time.time()
        
        self.all_time_stats = self._load_stats()
        self._init_csv()
        
        self.running = True
        self.save_thread = threading.Thread(target=self._auto_save, daemon=True)
        self.save_thread.start()
        
        print(f"[Logger] Session started: {self.session_id}")
    
    def _init_csv(self):
        if not os.path.exists(CONFIG['csv_file']):
            with open(CONFIG['csv_file'], 'w') as f:
                f.write("timestamp,action,distance_m,obstacles,avoidances,avg_fps,obstacle_duration\n")
    
    def _load_stats(self) -> Dict:
        if os.path.exists(CONFIG['log_file']):
            try:
                with open(CONFIG['log_file'], 'r') as f:
                    return json.load(f)
            except:
                return {"total_sessions": 0, "total_distance": 0}
        return {"total_sessions": 0, "total_distance": 0}
    
    def update(self, action: str, obstacle_detected: bool):
        current_time = time.time()
        self.frames_processed += 1
        
        frame_time = current_time - self.last_frame_time
        if frame_time > 0:
            self.fps_history.append(1.0 / frame_time)
        self.last_frame_time = current_time
        
        if action == "FORWARD":
            distance_this_frame = CONFIG['est_speed_mps'] * frame_time
            self.total_distance += distance_this_frame
        
        if obstacle_detected:
            self.obstacles_detected += 1
            if action in ["LEFT", "RIGHT"]:
                self.avoidance_maneuvers += 1
            
            # Track continuous obstacle duration
            if self.obstacle_start_time is None:
                self.obstacle_start_time = current_time
            else:
                duration = current_time - self.obstacle_start_time
                self.max_obstacle_duration = max(self.max_obstacle_duration, duration)
        else:
            self.obstacle_start_time = None
        
        self.current_action = action
    
    def log_voice_alert(self):
        self.voice_alerts += 1
    
    def get_stats(self) -> Dict:
        avg_fps = sum(self.fps_history) / len(self.fps_history) if self.fps_history else 0
        runtime = time.time() - self.start_time
        
        current_obstacle_duration = 0
        if self.obstacle_start_time:
            current_obstacle_duration = time.time() - self.obstacle_start_time
        
        return {
            "session_id": self.session_id,
            "runtime_seconds": round(runtime, 2),
            "runtime_formatted": str(timedelta(seconds=int(runtime))),
            "distance_m": round(self.total_distance, 2),
            "distance_km": round(self.total_distance / 1000, 3),
            "obstacles_detected": self.obstacles_detected,
            "avoidance_maneuvers": self.avoidance_maneuvers,
            "voice_alerts": self.voice_alerts,
            "avg_fps": round(avg_fps, 1),
            "current_action": self.current_action,
            "obstacle_duration": round(current_obstacle_duration, 1),
            "max_obstacle_duration": round(self.max_obstacle_duration, 1),
            "all_time_distance_km": round((self.all_time_stats.get("total_distance", 0) + self.total_distance) / 1000, 3)
        }
    
    def _auto_save(self):
        while self.running:
            time.sleep(CONFIG['save_interval'])
            self.save_to_file()
    
    def save_to_file(self):
        stats = self.get_stats()
        
        self.all_time_stats["total_sessions"] += 1
        self.all_time_stats["total_distance"] = self.all_time_stats.get("total_distance", 0) + self.total_distance
        
        try:
            with open(CONFIG['log_file'], 'w') as f:
                json.dump(self.all_time_stats, f, indent=2)
        except Exception as e:
            print(f"[Logger] Save error: {e}")
        
        try:
            with open(CONFIG['csv_file'], 'a') as f:
                f.write(f"{datetime.now().isoformat()},{stats['current_action']},"
                       f"{stats['distance_m']},{stats['obstacles_detected']},"
                       f"{stats['avoidance_maneuvers']},{stats['avg_fps']},"
                       f"{stats['obstacle_duration']}\n")
        except Exception as e:
            print(f"[Logger] CSV error: {e}")
        
        print(f"[Logger] Saved: {stats['distance_m']:.1f}m, Obs: {stats['obstacles_detected']}, Voice: {stats['voice_alerts']}")
    
    def generate_report(self) -> str:
        stats = self.get_stats()
        report = f"""
=== AUTONOMOUS CAR SESSION REPORT ===
Session ID: {stats['session_id']}
Duration: {stats['runtime_formatted']}
Distance Traveled: {stats['distance_m']:.2f} m ({stats['distance_km']:.3f} km)
Obstacles Detected: {stats['obstacles_detected']}
Avoidance Maneuvers: {stats['avoidance_maneuvers']}
Voice Alerts Given: {stats['voice_alerts']}
Longest Obstacle Duration: {stats['max_obstacle_duration']:.1f}s
Average FPS: {stats['avg_fps']}
All-Time Distance: {stats['all_time_distance_km']:.3f} km
=====================================
        """
        return report
    
    def stop(self):
        self.running = False
        self.save_to_file()
        print(self.generate_report())


# ============ VOICE SYSTEM WITH REPEAT ============
class VoiceController:
    def __init__(self, logger: MetricsLogger):
        self.logger = logger
        self.tts_queue = queue.Queue()
        self.last_speak_time = 0
        self.cooldown = CONFIG['voice_cooldown']
        self.running = True
        self.obstacle_start_time = None  # Track when obstacle first appeared
        self.has_spoken_for_current = False
        
        self.thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.thread.start()
        print(f"[Voice] Cooldown: {self.cooldown}s, will repeat while obstacle persists")
    
    def _tts_worker(self):
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 0.9)
        
        while self.running:
            try:
                text = self.tts_queue.get(timeout=1)
                engine.say(text)
                engine.runAndWait()
            except queue.Empty:
                continue
    
    def update_obstacle_status(self, obstacle_present: bool):
        """
        Call this every frame with current obstacle status.
        Handles continuous alerting while obstacle persists.
        """
        current_time = time.time()
        
        if obstacle_present:
            if self.obstacle_start_time is None:
                # New obstacle detected
                self.obstacle_start_time = current_time
                self._speak_now("Please move aside")
                print("[Voice] New obstacle - alerting")
            else:
                # Obstacle still there - check if we should repeat
                time_since_last = current_time - self.last_speak_time
                duration_present = current_time - self.obstacle_start_time
                
                if time_since_last > self.cooldown:
                    # Repeat alert
                    if duration_present > CONFIG['voice_repeat_threshold']:
                        # Urgent tone for persistent obstacles
                        self._speak_now("Please move aside immediately")
                        print(f"[Voice] Persistent obstacle ({duration_present:.1f}s) - urgent alert")
                    else:
                        self._speak_now("Please move aside")
                        print(f"[Voice] Repeating alert ({duration_present:.1f}s)")
        else:
            # Obstacle cleared
            if self.obstacle_start_time is not None:
                duration = current_time - self.obstacle_start_time
                print(f"[Voice] Obstacle cleared after {duration:.1f}s")
            self.obstacle_start_time = None
    
    def _speak_now(self, text: str):
        """Internal speak that bypasses checks"""
        self.tts_queue.put(text)
        self.last_speak_time = time.time()
        self.logger.log_voice_alert()
    
    def speak(self, text: str):
        """One-off speak (legacy compatibility)"""
        self._speak_now(text)
    
    def alert_obstacle(self):
        """Legacy compatibility"""
        self._speak_now("Please move aside")
    
    def stop(self):
        self.running = False


# ============ VISION SYSTEM ============
class VisionSystem:
    def __init__(self):
        self.model = YOLO(CONFIG['model_path'])
        self.cap = cv2.VideoCapture(CONFIG['camera_id'])
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CONFIG['resolution'][0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CONFIG['resolution'][1])
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        dummy = torch.zeros((1, 3, 640, 480))
        self.model.predict(dummy, verbose=False)
        
        self.frame_width = CONFIG['resolution'][0]
        self.frame_height = CONFIG['resolution'][1]
        self.current_frame = None
        self.current_detections = []
        
        print(f"[Vision] Camera ready at {self.frame_width}x{self.frame_height}")
    
    def update(self):
        ret, frame = self.cap.read()
        if not ret:
            return False
        
        frame = cv2.flip(frame, 1)
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
        
        self.current_frame = self._draw_debug(frame, detections)
        self.current_detections = detections
        return True
    
    def _draw_debug(self, frame, detections):
        h, w = frame.shape[:2]
        dz_start = int(w * CONFIG['danger_zone'][0])
        dz_end = int(w * CONFIG['danger_zone'][1])
        
        # Danger zone
        overlay = frame.copy()
        cv2.rectangle(overlay, (dz_start, 0), (dz_end, h), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        cv2.rectangle(frame, (dz_start, 0), (dz_end, h), (0, 0, 255), 2)
        cv2.putText(frame, "DANGER ZONE", (dz_start + 10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Detections
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cx, cy = map(int, det['center'])
            in_danger = CONFIG['danger_zone'][0] < (cx/w) < CONFIG['danger_zone'][1]
            color = (0, 0, 255) if in_danger else (0, 255, 0)
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, (cx, cy), 5, (255, 0, 0), -1)
            label = f"{det['name']} {det['conf']:.2f}"
            cv2.putText(frame, label, (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return frame
    
    def get_frame_bytes(self):
        if self.current_frame is None:
            return None
        ret, buffer = cv2.imencode('.jpg', self.current_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buffer.tobytes() if ret else None
    
    def release(self):
        self.cap.release()


# ============ NAVIGATION LOGIC (FIXED) ============
class NavigationLogic:
    def __init__(self):
        self.frame_area = CONFIG['resolution'][0] * CONFIG['resolution'][1]
        self.proximity_px = CONFIG['proximity_threshold'] * self.frame_area
        self.last_decision = "FORWARD"
        self.decision_cooldown = 0
    
    def decide(self, detections: List[dict]) -> Tuple[str, bool]:
        """
        Returns: (movement_action, obstacle_actually_present)
        Fixed: Now returns actual obstacle status regardless of cooldown
        """
        # Always calculate if obstacle is present (don't hide behind cooldown)
        obstacle_in_path = False
        largest_area = 0
        
        for det in detections:
            cx = det['center'][0]
            area = det['area']
            norm_x = cx / CONFIG['resolution'][0]
            
            if CONFIG['danger_zone'][0] < norm_x < CONFIG['danger_zone'][1]:
                if area > self.proximity_px:
                    obstacle_in_path = True
                    largest_area = max(largest_area, area)
        
        # Movement decision with cooldown (anti-jitter)
        if self.decision_cooldown > 0:
            self.decision_cooldown -= 1
            movement = self.last_decision
        else:
            if obstacle_in_path:
                movement = "LEFT"
                print(f"[Nav] OBSTACLE DETECTED (area: {largest_area:.0f}px) -> TURN LEFT")
            else:
                movement = "FORWARD"
            
            self.last_decision = movement
            self.decision_cooldown = 3  # Frames before changing direction again
        
        return movement, obstacle_in_path  # Always return true obstacle status!


# ============ MOTOR CONTROLLER ============
class MotorController:
    def __init__(self):
        self.mode = CONFIG['motor_mode']
        self.current_cmd = "STOP"
        
        if self.mode == 'serial':
            try:
                self.ser = serial.Serial(CONFIG['serial_port'], 9600, timeout=1)
                time.sleep(2)
                print(f"[Motor] Serial connected")
            except Exception as e:
                print(f"[Motor] Serial failed: {e}, using MOCK")
                self.mode = 'mock'
        else:
            print("[Motor] MOCK mode")
    
    def command(self, movement: str):
        if movement == self.current_cmd:
            return
        
        self.current_cmd = movement
        cmd_map = {"STOP": b'S', "FORWARD": b'F', "LEFT": b'L', "RIGHT": b'R'}
        byte_cmd = cmd_map.get(movement, b'S')
        
        if self.mode == 'serial':
            try:
                self.ser.write(byte_cmd)
            except Exception as e:
                print(f"[Motor] Error: {e}")
        else:
            print(f"[Motor] Command: {movement}")
    
    def stop(self):
        self.command("STOP")
        if self.mode == 'serial':
            self.ser.close()


# ============ WEB SERVER ============
class WebServer:
    def __init__(self, vision: VisionSystem, logger: MetricsLogger):
        self.app = Flask(__name__)
        self.vision = vision
        self.logger = logger
        
        @self.app.route('/')
        def index():
            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Autonomous Car Dashboard</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial; margin: 0; padding: 20px; background: #111; color: white; }
                    h1 { color: #0f0; text-align: center; font-size: 24px; }
                    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 600px; margin: 0 auto; }
                    .stat { background: #222; padding: 15px; border-radius: 8px; border-left: 4px solid #0f0; }
                    .stat.alert { border-left-color: #f00; background: #331111; }
                    .stat.warning { border-left-color: #ff0; }
                    .label { color: #888; font-size: 12px; }
                    .value { font-size: 20px; font-weight: bold; color: #0f0; }
                    .video { width: 100%; max-width: 640px; display: block; margin: 20px auto; border: 3px solid #0f0; border-radius: 10px; }
                    .action { text-align: center; font-size: 18px; margin: 10px 0; padding: 10px; background: #222; border-radius: 5px; }
                    .speaking { animation: pulse 1s infinite; color: #f00; }
                    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
                </style>
            </head>
            <body>
                <h1>🚗 Autonomous Car Dashboard</h1>
                <div class="action">Current Action: <span id="action">Loading...</span></div>
                <div class="action" id="voice-status" style="display: none; color: #f00; font-weight: bold;">🔊 SPEAKING: Please move aside!</div>
                <img src="/video_feed" class="video">
                <div class="grid">
                    <div class="stat">
                        <div class="label">Distance</div>
                        <div class="value" id="dist">0 m</div>
                    </div>
                    <div class="stat">
                        <div class="label">Runtime</div>
                        <div class="value" id="time">0:00</div>
                    </div>
                    <div class="stat alert">
                        <div class="label">Obstacles Count</div>
                        <div class="value" id="obs" style="color: #f00;">0</div>
                    </div>
                    <div class="stat alert">
                        <div class="label">Avoidances</div>
                        <div class="value" id="avoid" style="color: #f00;">0</div>
                    </div>
                    <div class="stat warning">
                        <div class="label">Current Obstacle Time</div>
                        <div class="value" id="obs-time" style="color: #ff0;">0s</div>
                    </div>
                    <div class="stat">
                        <div class="label">Voice Alerts</div>
                        <div class="value" id="voice">0</div>
                    </div>
                    <div class="stat">
                        <div class="label">FPS</div>
                        <div class="value" id="fps">0</div>
                    </div>
                    <div class="stat">
                        <div class="label">Speed</div>
                        <div class="value">0.5 m/s</div>
                    </div>
                </div>
                <script>
                    let lastVoiceCount = 0;
                    async function updateStats() {
                        try {
                            const res = await fetch('/stats');
                            const data = await res.json();
                            document.getElementById('dist').innerText = data.distance_m + ' m';
                            document.getElementById('time').innerText = data.runtime_formatted;
                            document.getElementById('obs').innerText = data.obstacles_detected;
                            document.getElementById('avoid').innerText = data.avoidance_maneuvers;
                            document.getElementById('voice').innerText = data.voice_alerts;
                            document.getElementById('fps').innerText = data.avg_fps;
                            document.getElementById('action').innerText = data.current_action;
                            document.getElementById('obs-time').innerText = data.obstacle_duration + 's';
                            
                            // Flash when voice alert triggers
                            if (data.voice_alerts > lastVoiceCount) {
                                lastVoiceCount = data.voice_alerts;
                                const vs = document.getElementById('voice-status');
                                vs.style.display = 'block';
                                setTimeout(() => { vs.style.display = 'none'; }, 2000);
                            }
                        } catch(e) {}
                    }
                    setInterval(updateStats, 500);
                    updateStats();
                </script>
            </body>
            </html>
            ''')
        
        @self.app.route('/video_feed')
        def video_feed():
            def generate():
                while True:
                    frame = self.vision.get_frame_bytes()
                    if frame:
                        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    time.sleep(0.033)
            return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
        
        @self.app.route('/stats')
        def stats():
            return jsonify(self.logger.get_stats())
    
    def run(self):
        thread = threading.Thread(
            target=self.app.run,
            kwargs={'host': '0.0.0.0', 'port': CONFIG['web_port'], 'debug': False, 'use_reloader': False},
            daemon=True
        )
        thread.start()
        print(f"[Web] Dashboard: http://localhost:{CONFIG['web_port']}")
        try:
            import socket
            ip = socket.gethostbyname(socket.gethostname())
            print(f"[Web] Mobile: http://{ip}:{CONFIG['web_port']}")
        except:
            pass


# ============ MAIN ============
class AutonomousCar:
    def __init__(self):
        print("=" * 60)
        print("AUTONOMOUS CAR - CONTINUOUS VOICE ALERTS ENABLED")
        print("=" * 60)
        
        self.logger = MetricsLogger()
        self.voice = VoiceController(self.logger)
        self.vision = VisionSystem()
        self.navigator = NavigationLogic()
        self.motors = MotorController()
        self.web = WebServer(self.vision, self.logger)
        
        self.running = False
        self.web.run()
        
        print("[System] Ready! Press 'q' to quit")
        print("[System] Voice will repeat every", CONFIG['voice_cooldown'], "seconds while obstacle present")
        print("=" * 60)
    
    def run(self):
        self.running = True
        
        try:
            while self.running:
                if not self.vision.update():
                    break
                
                detections = self.vision.current_detections
                movement, obstacle_present = self.navigator.decide(detections)
                
                # Update metrics with TRUE obstacle status (not affected by cooldown)
                self.logger.update(movement, obstacle_present)
                
                # Update voice with current obstacle status (repeats if persistent)
                self.voice.update_obstacle_status(obstacle_present)
                
                self.motors.command(movement)
                
                # Display
                frame = self.vision.current_frame.copy()
                stats = self.logger.get_stats()
                
                y_pos = 30
                cv2.putText(frame, f"Dist: {stats['distance_m']:.1f}m | Voice: {stats['voice_alerts']} | ObsTime: {stats['obstacle_duration']:.1f}s", 
                           (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(frame, f"FPS: {stats['avg_fps']:.1f} | Action: {movement}", 
                           (10, y_pos+25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
                if obstacle_present:
                    status = "REPEATING ALERT!" if stats['obstacle_duration'] > CONFIG['voice_cooldown'] else "ALERT"
                    cv2.putText(frame, f"VOICE ({status}): Please move aside!", (10, y_pos+50),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
                cv2.imshow("Autonomous Car (Press 'q' to quit)", frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.logger.save_to_file()
                
        except KeyboardInterrupt:
            print("\n[Main] Interrupted")
        finally:
            self.shutdown()
    
    def shutdown(self):
        print("[System] Shutting down...")
        self.running = False
        self.logger.stop()
        self.voice.stop()
        self.motors.stop()
        self.vision.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    required = ['ultralytics', 'flask', 'pyttsx3']
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"ERROR: Missing packages: {missing}")
        print("Run: pip install -r requirements.txt")
        exit(1)
    
    car = AutonomousCar()
    car.run()