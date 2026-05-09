from pathlib import Path

# Get the project root (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent

# ── Matching strategy ─────────────────────────
# "fuzzy"  → RapidFuzz alias map (no ML, ~50 KB)
# "embedding" → sentence-transformers cosine sim (~80 MB)
MATCH_MODE: str = "fuzzy"

# ── Thresholds ────────────────────────────────
FUZZY_THRESH: int   = 72    # partial_ratio 0-100; raise to be stricter
EMBED_THRESH: float = 0.42  # cosine 0-1;          raise to be stricter
AMBIGUOUS_GAP: float = 0.08 # if top-2 scores within this gap → ask user

# ── Retry / UX ────────────────────────────────
MAX_RETRIES: int = 2        # re-record attempts before giving up
STT_TIMEOUT: int = 8        # seconds to wait for speech to start
STT_PHRASE_LIMIT: int = 6   # max seconds per utterance
TTS_RATE: int = 155          # words per minute for pyttsx3

# ── STT backend ───────────────────────────────
# "moonshine"  → uses Moonshine (pip install moonshine-voice)
# "google"     → Google STT via speech_recognition (needs internet)
# "vosk"       → Vosk offline  (needs model folder in models/vosk/)
STT_BACKEND: str = "moonshine"
VOSK_MODEL_PATH: str = "models/vosk"

# ── ROS2 ──────────────────────────────────────
# Set False when running on Windows / without a ROS2 environment.
# The system will log the goal instead of publishing.
USE_ROS2: bool = False
ROS2_TOPIC: str = "/voice_nav_goal"

# ── Logging ───────────────────────────────────
# Uses absolute paths so logs work regardless of where you run main.py from
LOG_FILE: str = str(PROJECT_ROOT / "logs" / "commands.json")
ERR_FILE: str = str(PROJECT_ROOT / "logs" / "errors.log")

# ── Home / hub ────────────────────────────────
HOME_LOCATION: str = "medical_station"
AUTO_RETURN_HOME: bool = True   # return to hub after each delivery