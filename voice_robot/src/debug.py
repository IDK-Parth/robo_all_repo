# test_imports.py
print("Testing imports...")
try:
    import numpy
    print("✓ numpy OK")
except ImportError as e:
    print(f"✗ numpy failed: {e}")

try:
    import sounddevice
    print("✓ sounddevice OK")
except ImportError as e:
    print(f"✗ sounddevice failed: {e}")

try:
    from moonshine_voice  import Transcriber
    print("✓ moonshine_onnx OK")
except ImportError as e:
    print(f"✗ moonshine_voice  failed: {e}")
    print("  Try: pip install moonshine-onnx")