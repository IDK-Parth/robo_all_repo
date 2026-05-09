# ─────────────────────────────────────────────
# main.py – complete voice robot pipeline
# ─────────────────────────────────────────────

import sys
import time
import os
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    MATCH_MODE, FUZZY_THRESH, EMBED_THRESH, AMBIGUOUS_GAP,
    MAX_RETRIES, STT_TIMEOUT, STT_PHRASE_LIMIT, TTS_RATE,
    STT_BACKEND, VOSK_MODEL_PATH,
    USE_ROS2, ROS2_TOPIC,
    HOME_LOCATION, AUTO_RETURN_HOME,
)
from map import (
    FLOOR_GRAPH, LOCATIONS, DISPLAY,
    ALIASES, ALIAS_LOOKUP, LOCATION_DESCRIPTIONS,
)
from helpers import log, normalize, extract_intent, log_command
import networkx as nx

# ══════════════════════════════════════════════
# 1. TTS - Robust with re-init on failure
# ══════════════════════════════════════════════
def speak(text: str) -> None:
    """Speak text with robust error handling and re-init on failure."""
    log.info(f"Speaking: {text!r}")
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", TTS_RATE)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        time.sleep(0.3)
    except Exception as e:
        log.error(f"TTS failed: {e}")
        print(f"[ROBOT SAYS]: {text}")
        time.sleep(0.5)

# ══════════════════════════════════════════════
# 2. STT - With fallback
# ══════════════════════════════════════════════
_moonshine_available = True

def listen() -> str | None:
    """Record one utterance and return transcribed text, or None."""
    global _moonshine_available
    
    if STT_BACKEND == "moonshine" and _moonshine_available:
        result = _listen_moonshine()
        if result is None and not _moonshine_available:
            log.info("Moonshine failed, switching to Google STT...")
            return _listen_google()
        return result
    else:
        return _listen_google()

def _listen_google() -> str | None:
    import speech_recognition as sr
    r = sr.Recognizer()
    r.pause_threshold = 1.0
    r.energy_threshold = 400
    
    with sr.Microphone() as source:
        log.info("Listening … Speak now!")
        try:
            audio = r.listen(source, timeout=STT_TIMEOUT, phrase_time_limit=STT_PHRASE_LIMIT)
        except sr.WaitTimeoutError:
            log.warning("No speech detected (timeout).")
            return None
    
    try:
        text = r.recognize_google(audio)
        log.info(f"Heard: {text!r}")
        return text
    except sr.UnknownValueError:
        log.warning("Could not understand audio.")
        return None
    except sr.RequestError as e:
        log.error(f"STT request failed: {e}")
        return None

def _listen_moonshine() -> str | None:
    global _moonshine_available
    
    try:
        import numpy as np
        import sounddevice as sd
        from moonshine_voice import Transcriber
        
        SAMPLE_RATE = 16000
        log.info("Listening (Moonshine) … Speak now!")
        
        audio = sd.rec(
            int(SAMPLE_RATE * STT_PHRASE_LIMIT),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocking=True
        )
        audio = audio.squeeze()
        
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.005:
            log.warning(f"Silence detected (RMS: {rms:.4f})")
            return None
        
        log.info(f"Audio detected (RMS: {rms:.4f}), transcribing...")
        
        try:
            transcriber = Transcriber()
            text = transcriber.transcribe(audio, SAMPLE_RATE)
            if text and text.strip():
                log.info(f"Heard (Moonshine): {text!r}")
                return text.strip()
        except Exception as e:
            log.error(f"Moonshine transcriber error: {e}")
            _moonshine_available = False
            return None
            
    except ImportError:
        log.warning("moonshine-voice not installed")
        _moonshine_available = False
        return None
    except Exception as e:
        log.error(f"Moonshine error: {e}")
        _moonshine_available = False
        return None
    
    return None

def is_yes_response(text: str) -> bool:
    """Check if text contains yes/confirmation words."""
    if not text:
        return False
    return any(w in text.lower() for w in ("yes", "yeah", "correct", "yep", "right", "go", "sure", "ok"))

def is_no_response(text: str) -> bool:
    """Check if text contains no/rejection words."""
    if not text:
        return False
    return any(w in text.lower() for w in ("no", "nope", "wrong", "cancel", "stop", "not"))

# ══════════════════════════════════════════════
# 3. MATCHING (Fuzzy/Embedding)
# ══════════════════════════════════════════════
def _fuzzy_match(command: str) -> tuple[str | None, float]:
    from rapidfuzz import process, fuzz

    for phrase in [command] + command.split():
        if phrase in ALIAS_LOOKUP:
            return ALIAS_LOOKUP[phrase], 1.0

    best_loc, best_score = None, 0.0

    for word in command.split():
        result = process.extractOne(word, ALIAS_LOOKUP.keys(), scorer=fuzz.ratio)
        if result and result[1] > best_score * 100:
            best_score = result[1] / 100.0
            best_loc = ALIAS_LOOKUP[result[0]]

    result = process.extractOne(command, ALIAS_LOOKUP.keys(), scorer=fuzz.partial_ratio)
    if result and result[1] / 100.0 > best_score:
        best_score = result[1] / 100.0
        best_loc = ALIAS_LOOKUP[result[0]]

    if best_score * 100 >= FUZZY_THRESH:
        return best_loc, best_score
    return None, best_score

def find_destination(command: str) -> tuple[str | None, float]:
    return _fuzzy_match(command)

# ══════════════════════════════════════════════
# 4. VALIDATION
# ══════════════════════════════════════════════
def val1_keyword(text: str, intent: dict) -> bool:
    if intent["intent"] in ("go", "return"):
        return True
    if intent["room_mention"] is not None:
        return True
    low = text.lower()
    return any(alias in low for alias in ALIAS_LOOKUP)

def val2_room_check(dest: str | None) -> bool:
    return dest is not None and dest in FLOOR_GRAPH.nodes

# ══════════════════════════════════════════════
# 5. PATHFINDING & ROS
# ══════════════════════════════════════════════
def get_path(start: str, end: str) -> list[str]:
    try:
        return nx.shortest_path(FLOOR_GRAPH, start, end)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        log.error(f"No path from {start!r} to {end!r}")
        return []

class VoicePublisher(Node):
    def __init__(self):
        super().__init__('voice_publisher')
        self.pub = self.create_publisher(String, 'voice_command', 10)

    def publish(self, destination):
        msg = String()
        msg.data = destination
        self.pub.publish(msg)
        self.get_logger().info(f"Published: {destination}")

# ══════════════════════════════════════════════
# 6. MAIN LOOP
# ══════════════════════════════════════════════
def main():
    rclpy.init()
    node = VoicePublisher()
    current = HOME_LOCATION
    
    speak("Robot ready. Where should I go?")
    try:    
      for _ in range(1):
        retries = 0
        dest_confirmed = None
        raw = ""
        cleaned = ""
        
        # Inner loop: Get destination with retries
        while retries <= MAX_RETRIES and dest_confirmed is None:
            
            raw = input("Enter command: ")
            if not raw:
                speak("I didn't catch that. Please try again.")
                retries += 1
                continue
            
            # Acknowledge what was heard
            speak(f"You said: {raw}")
            
            cleaned = normalize(raw)
            intent = extract_intent(cleaned)
            log.info(f"Normalized: {cleaned!r} intent={intent['intent']}")
            
            dest, score = find_destination(cleaned)
            log.info(f"Match: {dest!r} score={score:.2f}")
            
            if not val1_keyword(cleaned, intent):
                speak("I'm not sure that's a destination. Can you say the room number?")
                retries += 1
                continue
            
            if not val2_room_check(dest):
                speak("I couldn't find that room. Please repeat the room number.")
                retries += 1
                continue
            
            # Confirmation loop - keep asking until we get yes/no
            display_name = DISPLAY.get(dest, dest)
            confirmation_retries = 0
            confirmed = False
            
            while confirmation_retries < 3 and not confirmed:
                speak(f"Did you mean {display_name}?")
                time.sleep(0.5)
                
                confirm = input("Confirm (yes/no): ")
                
                if confirm is None:
                    # Didn't hear anything - ask again without penalty
                    speak("I didn't hear your response.")
                    confirmation_retries += 1
                    continue
                
                if is_yes_response(confirm):
                    dest_confirmed = dest
                    confirmed = True
                    break
                elif is_no_response(confirm):
                    speak("OK, please say your destination again.")
                    break
                else:
                    # Heard something but not yes/no - ask again
                    speak("Please say yes or no.")
                    confirmation_retries += 1
            
            if not confirmed and dest_confirmed is None:
                # User said no or we couldn't get confirmation
                retries += 1
        
        # Check if we got a destination
        if dest_confirmed is None:
            log_command(raw or "", cleaned or "", None, 0.0, False)
            speak("I'm sorry, I couldn't understand. Please press the call button.")
            continue
        
        if dest_confirmed == current:
            speak(f"I'm already at {display_name}.")
            continue
        
        path = get_path(current, dest_confirmed)
        if not path:
            speak(f"I cannot find a path to {display_name}.")
            continue
        
        path_display = " then ".join(DISPLAY.get(p, p) for p in path)
        log_command(raw, cleaned, dest_confirmed, score, True, path)
        
        # NAVIGATION START
        speak(f"Got it. Leaving now for {display_name}.")
        speak(f"Route is: {path_display}.")
        speak("Please move aside, robot coming through.")
        
        node.publish(dest_confirmed)
        
        # Simulate travel
        time.sleep(2)
        current = dest_confirmed
        
        # Arrival
        speak(f"Arrived at {display_name}.")
        
        # Auto-return if enabled
        if AUTO_RETURN_HOME and current != HOME_LOCATION:
            time.sleep(1)
            home_name = DISPLAY.get(HOME_LOCATION, HOME_LOCATION)
            speak(f"Returning to {home_name}.")
            return_path = get_path(current, HOME_LOCATION)
            if return_path:
                node.publish(HOME_LOCATION)
                time.sleep(2)
                current = HOME_LOCATION
                speak(f"Back at {home_name}. Ready for next command.")
        
        time.sleep(0.5)
    finally:
      node.destroy_node()
      rclpy.shutdown()

if __name__ == "__main__":
    main()
