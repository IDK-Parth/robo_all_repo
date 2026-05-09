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
    'danger_zone': (0.33, 0.66),  # Middle third is danger
    'proximity_threshold': 0.15,
    'motor_mode': 'mock',
    'serial_port': '/dev/ttyUSB0',
    'web_port': 5000,
    'voice_cooldown': 1.5,         # Shorter cooldown for more responsive voice
    'voice_repeat_threshold': 4,   # Urgent after 4 seconds
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
        self.avoidance_left = 0
        self.avoidance_right = 0
        self.voice_alerts = 0
        self.frames_processed = 0
        self.current_action = "INIT"
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.obstacle_start_time = None
        self.max_obstacle_duration = 0
        self.last_obstacle_side = "NONE"  # Track which side was last blocked
        
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
                f.write("timestamp,action,distance_m,obstacles,left_turns,right_turns,avg_fps,obstacle_duration,side\n")
    
    def _load_stats(self) -> Dict:
        if os.path.exists(CONFIG['log_file']):
            try:
                with open(CONFIG['log_file'], 'r') as f:
                    return json.load(f)
            except:
                return {"total_sessions": 0, "total_distance": 0}
        return {"total_sessions": 0, "total_distance": 0}
    
    def update(self, action: str, obstacle_detected: bool, side: str = "NONE"):
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
            if action == "LEFT":
                self.avoidance_left += 1
            elif action == "RIGHT":
                self.avoidance_right += 1
            
            if self.obstacle_start_time is None:
                self.obstacle_start_time = current_time
                self.last_obstacle_side = side
            else:
                duration = current_time - self.obstacle_start_time
                self.max_obstacle_duration = max(self.max_obstacle_duration, duration)
        else:
            self.obstacle_start_time = None
            self.last_obstacle_side = "NONE"
        
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
            "avoidance_left": self.avoidance_left,
            "avoidance_right": self.avoidance_right,
            "voice_alerts": self.voice_alerts,
            "avg_fps": round(avg_fps, 1),
            "current_action": self.current_action,
            "obstacle_duration": round(current_obstacle_duration, 1),
            "max_obstacle_duration": round(self.max_obstacle_duration, 1),
            "last_side": self.last_obstacle_side,
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
                       f"{stats['avoidance_left']},{stats['avoidance_right']},"
                       f"{stats['avg_fps']},{stats['obstacle_duration']},{stats['last_side']}\n")
        except Exception as e:
            print(f"[Logger] CSV error: {e}")
        
        print(f"[Logger] Saved: {stats['distance_m']:.1f}m, L:{stats['avoidance_left']} R:{stats['avoidance_right']}")
    
    def generate_report(self) -> str:
        stats = self.get_stats()
        report = f"""
=== AUTONOMOUS CAR SESSION REPORT ===
Session ID: {stats['session_id']}
Duration: {stats['runtime_formatted']}
Distance: {stats['distance_m']:.2f} m ({stats['distance_km']:.3f} km)
Obstacles: {stats['obstacles_detected']}
Left Turns: {stats['avoidance_left']} | Right Turns: {stats['avoidance_right']}
Voice Alerts: {stats['voice_alerts']}
Max Obstacle Time: {stats['max_obstacle_duration']:.1f}s
Avg FPS: {stats['avg_fps']}
=====================================
        """
        return report
    
    def stop(self):
        self.running = False
        self.save_to_file()
        print(self.generate_report())


# ============ VOICE CONTROLLER (FIXED FOR CONTINUOUS ALERTS) ============
class VoiceController:
    def __init__(self, logger: MetricsLogger):
        self.logger = logger
        self.tts_queue = queue.Queue()
        self.last_speak_time = 0
        self.cooldown = CONFIG['voice_cooldown']
        self.running = True
        self.obstacle_active = False
        self.obstacle_start_time = None
        self.last_side = "NONE"
        self.consecutive_alerts = 0  # Count how many times we've repeated
        
        self.thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.thread.start()
        print(f"[Voice] Cooldown: {self.cooldown}s, continuous mode enabled")
    
    def _tts_worker(self):
        engine = pyttsx3.init()
        engine.setProperty('rate', 155)
        engine.setProperty('volume', 0.9)
        
        while self.running:
            try:
                text = self.tts_queue.get(timeout=0.5)
                engine.say(text)
                engine.runAndWait()
            except queue.Empty:
                continue
    
    def update(self, obstacle_present: bool, side: str, action: str):
        """
        Call every frame with current state.
        FIXED: Properly tracks continuous obstacles and repeats voice.
        """
        current_time = time.time()
        
        if obstacle_present:
            # Obstacle is currently in view
            if not self.obstacle_active:
                # Just appeared - reset tracking
                self.obstacle_active = True
                self.obstacle_start_time = current_time
                self.consecutive_alerts = 0
                self._speak(f"Please move to the {side}", side, urgent=False)
                print(f"[Voice] NEW obstacle on {side} - first alert")
            
            else:
                # Still there - check if we should repeat
                time_since_last = current_time - self.last_speak_time
                duration_present = current_time - self.obstacle_start_time
                
                if time_since_last >= self.cooldown:
                    # Time to repeat!
                    self.consecutive_alerts += 1
                    urgent = duration_present > CONFIG['voice_repeat_threshold']
                    
                    # Vary the message based on repetition count
                    if self.consecutive_alerts >= 3 and urgent:
                        self._speak(f"Move {side} now", side, urgent=True)
                    else:
                        self._speak(f"Please move to the {side}", side, urgent=False)
                    
                    print(f"[Voice] REPEAT #{self.consecutive_alerts} ({duration_present:.1f}s on {side})")
                
                # Also speak immediately if side changes
                if side != self.last_side and self.last_side != "NONE":
                    self._speak(f"Now move to the {side}", side, urgent=False)
                    print(f"[Voice] SIDE CHANGED from {self.last_side} to {side}")
            
            self.last_side = side
            
        else:
            # No obstacle - reset everything
            if self.obstacle_active:
                duration = current_time - self.obstacle_start_time if self.obstacle_start_time else 0
                print(f"[Voice] Obstacle cleared after {duration:.1f}s, alerts given: {self.consecutive_alerts + 1}")
            
            self.obstacle_active = False
            self.obstacle_start_time = None
            self.last_side = "NONE"
            self.consecutive_alerts = 0
    
    def _speak(self, text: str, side: str, urgent: bool = False):
        """Queue speech and log it"""
        if urgent:
            text = "Warning! " + text
        
        self.tts_queue.put(text)
        self.last_speak_time = time.time()
        self.logger.log_voice_alert()
        self.last_side = side
    
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
        self.center_x = self.frame_width // 2
        self.current_frame = None
        self.current_detections = []
        
        print(f"[Vision] Camera ready at {self.frame_width}x{self.frame_height}, center at x={self.center_x}")
    
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
        center_x = w // 2
        
        # Draw center line (blue, thick) - THE MIDDLE LINE YOU WANTED
        cv2.line(frame, (center_x, 0), (center_x, h), (255, 0, 0), 3)
        cv2.putText(frame, "CENTER", (center_x - 30, 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        
        # Danger zones (left and right of center)
        dz_left = int(w * CONFIG['danger_zone'][0])
        dz_right = int(w * CONFIG['danger_zone'][1])
        
        # Left danger zone (red tint)
        overlay = frame.copy()
        cv2.rectangle(overlay, (dz_left, 0), (center_x, h), (0, 0, 255), -1)
        # Right danger zone (red tint)
        cv2.rectangle(overlay, (center_x, 0), (dz_right, h), (0, 0, 255), -1)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        
        # Danger zone borders
        cv2.rectangle(frame, (dz_left, 0), (dz_right, h), (0, 0, 255), 2)
        cv2.putText(frame, "DANGER ZONE", (dz_left + 10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        # Draw detections
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cx, cy = map(int, det['center'])
            norm_x = cx / w
            
            # Determine color based on position relative to center
            in_danger = CONFIG['danger_zone'][0] < norm_x < CONFIG['danger_zone'][1]
            if in_danger:
                # Left or right of center line?
                if cx < center_x:
                    color = (0, 165, 255)  # Orange for left side
                    side_text = "L"
                else:
                    color = (255, 0, 255)  # Purple for right side
                    side_text = "R"
            else:
                color = (0, 255, 0)  # Green for safe
                side_text = "SAFE"
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, (cx, cy), 5, (255, 255, 0), -1)
            
            # Draw line from object to center line
            if in_danger:
                cv2.line(frame, (cx, cy), (center_x, cy), color, 1)
            
            label = f"{det['name']} {det['conf']:.2f} [{side_text}]"
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


# ============ NAVIGATION LOGIC (FIXED FOR LEFT/RIGHT DECISIONS) ============
class NavigationLogic:
    def __init__(self):
        self.frame_area = CONFIG['resolution'][0] * CONFIG['resolution'][1]
        self.proximity_px = CONFIG['proximity_threshold'] * self.frame_area
        self.center_x = CONFIG['resolution'][0] // 2
        self.last_decision = "FORWARD"
        self.decision_cooldown = 0
    
    def decide(self, detections: List[dict]) -> Tuple[str, bool, str]:
        """
        FIXED: Returns (movement, obstacle_present, side)
        side = "LEFT", "RIGHT", or "NONE"
        """
        # Find the most threatening obstacle in danger zone
        best_obstacle = None
        best_score = 0  # Higher = more threatening
        
        for det in detections:
            cx = det['center'][0]
            area = det['area']
            norm_x = cx / CONFIG['resolution'][0]
            
            # Must be in danger zone
            if not (CONFIG['danger_zone'][0] < norm_x < CONFIG['danger_zone'][1]):
                continue
            
            # Must be close (large)
            if area < self.proximity_px:
                continue
            
            # Score: closer to center = more dangerous, larger = more dangerous
            dist_from_center = abs(cx - self.center_x)
            score = area / (dist_from_center + 1)  # +1 to avoid div by zero
            
            if score > best_score:
                best_score = score
                best_obstacle = det
        
        obstacle_present = best_obstacle is not None
        
        if obstacle_present:
            # Determine which side to turn based on obstacle position
            obs_x = best_obstacle['center'][0]
            
            if obs_x < self.center_x:
                # Obstacle on LEFT side of center → turn RIGHT
                side = "LEFT"  # Obstacle is on left
                action = "RIGHT"
                print(f"[Nav] Obstacle on LEFT (x={obs_x:.0f}) → TURN RIGHT")
            else:
                # Obstacle on RIGHT side of center → turn LEFT
                side = "RIGHT"  # Obstacle is on right
                action = "LEFT"
                print(f"[Nav] Obstacle on RIGHT (x={obs_x:.0f}) → TURN LEFT")
        else:
            side = "NONE"
            action = "FORWARD"
        
        # Apply movement cooldown (anti-jitter) separately from detection
        if self.decision_cooldown > 0:
            self.decision_cooldown -= 1
            # Still return TRUE obstacle status even if keeping previous action
            return self.last_decision, obstacle_present, side
        else:
            self.last_decision = action
            self.decision_cooldown = 3
            return action, obstacle_present, side


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
            print(f"[Motor] >>> {movement}")
    
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
                    h1 { color: #0f0; text-align: center; font-size: 22px; }
                    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; max-width: 600px; margin: 0 auto; }
                    .stat { background: #222; padding: 15px; border-radius: 8px; border-left: 4px solid #0f0; }
                    .stat.alert { border-left-color: #f00; background: #331111; }
                    .stat.left { border-left-color: #ff8800; }
                    .stat.right { border-left-color: #ff00ff; }
                    .label { color: #888; font-size: 12px; }
                    .value { font-size: 20px; font-weight: bold; color: #0f0; }
                    .video { width: 100%; max-width: 640px; display: block; margin: 20px auto; border: 3px solid #0f0; border-radius: 10px; }
                    .action { text-align: center; font-size: 18px; margin: 10px 0; padding: 10px; background: #222; border-radius: 5px; }
                    .speaking { animation: pulse 0.5s infinite; color: #f00; font-weight: bold; }
                    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
                    .side-left { color: #ff8800; }
                    .side-right { color: #ff00ff; }
                </style>
            </head>
            <body>
                <h1>🚗 Autonomous Car Dashboard</h1>
                <div class="action">Action: <span id="action">INIT</span> | Side: <span id="side">-</span></div>
                <div class="action" id="voice-box" style="display: none;">🔊 <span id="voice-text">Alert!</span></div>
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
                    <div class="stat left">
                        <div class="label">Left Turns</div>
                        <div class="value" id="left" style="color: #ff8800;">0</div>
                    </div>
                    <div class="stat right">
                        <div class="label">Right Turns</div>
                        <div class="value" id="right" style="color: #ff00ff;">0</div>
                    </div>
                    <div class="stat alert">
                        <div class="label">Total Obstacles</div>
                        <div class="value" id="obs" style="color: #f00;">0</div>
                    </div>
                    <div class="stat alert">
                        <div class="label">Obstacle Time</div>
                        <div class="value" id="obs-time" style="color: #f00;">0s</div>
                    </div>
                    <div class="stat">
                        <div class="label">Voice Alerts</div>
                        <div class="value" id="voice">0</div>
                    </div>
                    <div class="stat">
                        <div class="label">FPS</div>
                        <div class="value" id="fps">0</div>
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
                            document.getElementById('left').innerText = data.avoidance_left;
                            document.getElementById('right').innerText = data.avoidance_right;
                            document.getElementById('obs').innerText = data.obstacles_detected;
                            document.getElementById('voice').innerText = data.voice_alerts;
                            document.getElementById('fps').innerText = data.avg_fps;
                            document.getElementById('action').innerText = data.current_action;
                            document.getElementById('obs-time').innerText = data.obstacle_duration + 's';
                            
                            const sideEl = document.getElementById('side');
                            if (data.last_side === "LEFT") {
                                sideEl.innerText = "OBSTACLE LEFT → Turn RIGHT";
                                sideEl.className = "side-left";
                            } else if (data.last_side === "RIGHT") {
                                sideEl.innerText = "OBSTACLE RIGHT → Turn LEFT";
                                sideEl.className = "side-right";
                            } else {
                                sideEl.innerText = "CLEAR";
                                sideEl.className = "";
                            }
                            
                            // Voice alert flash
                            if (data.voice_alerts > lastVoiceCount) {
                                lastVoiceCount = data.voice_alerts;
                                const vb = document.getElementById('voice-box');
                                const vt = document.getElementById('voice-text');
                                vt.innerText = "Please move to the " + data.last_side + "!";
                                vb.style.display = 'block';
                                vb.className = "action speaking";
                                setTimeout(() => { 
                                    vb.className = "action"; 
                                    setTimeout(() => { vb.style.display = 'none'; }, 1000);
                                }, 2000);
                            }
                        } catch(e) {}
                    }
                    setInterval(updateStats, 400);
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
        print("AUTONOMOUS CAR - LEFT/RIGHT SMART AVOIDANCE + CONTINUOUS VOICE")
        print("=" * 60)
        
        self.logger = MetricsLogger()
        self.voice = VoiceController(self.logger)
        self.vision = VisionSystem()
        self.navigator = NavigationLogic()
        self.motors = MotorController()
        self.web = WebServer(self.vision, self.logger)
        
        self.running = False
        self.web.run()
        
        print("[System] Blue line = Center | Orange = Obstacle Left | Purple = Obstacle Right")
        print("[System] Voice repeats every", CONFIG['voice_cooldown'], "seconds while obstacle present")
        print("[System] Press 'q' to quit, 's' to save")
        print("=" * 60)
    
    def run(self):
        self.running = True
        
        try:
            while self.running:
                if not self.vision.update():
                    break
                
                detections = self.vision.current_detections
                
                # Get decision with side info
                movement, obstacle_present, side = self.navigator.decide(detections)
                
                # Update metrics
                self.logger.update(movement, obstacle_present, side)
                
                # Update voice (FIXED: continuous alerts while obstacle present)
                self.voice.update(obstacle_present, side, movement)
                
                # Execute movement
                self.motors.command(movement)
                
                # Display
                frame = self.vision.current_frame.copy()
                stats = self.logger.get_stats()
                
                y_pos = 30
                # Top HUD
                cv2.putText(frame, f"Dist: {stats['distance_m']:.1f}m | Voice: {stats['voice_alerts']} | ObsTime: {stats['obstacle_duration']:.1f}s", 
                           (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(frame, f"FPS: {stats['avg_fps']:.1f} | Action: {movement} | Side: {side}", 
                           (10, y_pos+25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                
                # Voice status
                if obstacle_present:
                    status = f"REPEATING ({stats['obstacle_duration']:.1f}s)" if stats['obstacle_duration'] > CONFIG['voice_cooldown'] else "ALERT"
                    color = (0, 0, 255) if stats['obstacle_duration'] > CONFIG['voice_repeat_threshold'] else (0, 165, 255)
                    cv2.putText(frame, f"VOICE {status}: Move to {side}!", (10, y_pos+50),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                cv2.imshow("Autonomous Car (Blue=Center, L=Orange, R=Purple)", frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.logger.save_to_file()
                    print("[Key] Manual save")
                
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