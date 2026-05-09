# ─────────────────────────────────────────────
#  helpers.py  –  logging + small utilities
# ─────────────────────────────────────────────
import json
import logging
import datetime
from pathlib import Path
from config import LOG_FILE, ERR_FILE

# ── Logger setup ─────────────────────────────
def get_logger(name: str = "voice_robot") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (errors only)
    Path(ERR_FILE).parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(ERR_FILE)
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))
    logger.addHandler(fh)

    return logger

log = get_logger()


# ── Structured command logger ─────────────────
def log_command(
    raw: str,
    normalized: str,
    matched: str | None,
    score: float,
    success: bool,
    path: list[str] | None = None,
) -> None:
    """Append one command event to the JSON log file."""
    entry = {
        "ts":         datetime.datetime.now().isoformat(timespec="seconds"),
        "raw":        raw,
        "normalized": normalized,
        "matched":    matched,
        "score":      round(score, 3),
        "success":    success,
        "path":       path or [],
    }
    path_file = Path(LOG_FILE)
    path_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        records: list = json.loads(path_file.read_text()) if path_file.exists() else []
    except (json.JSONDecodeError, OSError):
        records = []
    records.append(entry)
    path_file.write_text(json.dumps(records, indent=2))


# ── Text normalization ────────────────────────
import re

_FILLERS = frozenset({
    "please", "can", "you", "take", "me", "go", "to", "the",
    "i", "want", "need", "head", "bring", "move", "let", "us",
    "a", "an", "and", "in", "at", "my",
})

def normalize(text: str) -> str:
    """Lowercase, remove punctuation, strip filler words."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = [w for w in text.split() if w not in _FILLERS]
    # Keep original if stripping removed everything meaningful
    return " ".join(words) if words else text


# ── Intent + entity extraction ────────────────
_ROOM_PATTERN = re.compile(
    r"\b(room\s*\d{2,4}|\d{3,4}|three\s*o\s*(?:one|two)|three\s*zero\s*(?:one|two)|"
    r"three\s*thousand\s*three|medical\s*station|general\s*room|"
    r"common|lounge|hub|home|base|station)\b",
    re.IGNORECASE,
)

_COMMAND_KEYWORDS = {
    "go":      ["go", "move", "head", "take", "drive", "navigate"],
    "return":  ["return", "back", "home", "hub", "base"],
    "stop":    ["stop", "halt", "wait", "pause"],
    "status":  ["where", "status", "location", "position"],
}

def extract_intent(text: str) -> dict:
    """
    Returns: {"intent": str, "room_mention": str | None, "full_text": str}
    intent ∈ {"go", "return", "stop", "status", "unknown"}
    """
    low = text.lower()
    intent = "unknown"
    for cmd, keywords in _COMMAND_KEYWORDS.items():
        if any(k in low for k in keywords):
            intent = cmd
            break

    room_match = _ROOM_PATTERN.search(low)
    room_mention = room_match.group(0).strip() if room_match else None

    return {"intent": intent, "room_mention": room_mention, "full_text": text}
