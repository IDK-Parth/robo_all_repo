# test_mic.py - Run this to check if microphone is working
import sounddevice as sd
import numpy as np

print("Available audio devices:")
print(sd.query_devices())
print("\nDefault input device:", sd.query_devices(kind='input'))

print("\nRecording 3 seconds of audio... Speak now!")
SAMPLE_RATE = 16000
duration = 3

audio = sd.rec(int(SAMPLE_RATE * duration), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
sd.wait()
audio = audio.squeeze()

rms = np.sqrt(np.mean(audio ** 2))
max_amp = np.max(np.abs(audio))

print(f"Audio stats:")
print(f"  RMS (average volume): {rms:.4f}")
print(f"  Max amplitude: {max_amp:.4f}")

if rms < 0.005:
    print("\nWARNING: Audio level is very low! Check your microphone.")
    print("Tips:")
    print("1. Make sure your microphone is not muted")
    print("2. Increase microphone volume in Windows Sound settings")
    print("3. Try a different microphone device")
else:
    print("\nMicrophone is working! Audio levels look good.")