# Voice Robot – Hospital Navigation

Speech-driven navigation module for a hospital delivery robot.

## Project structure

```
voice_robot/
├── src/
│   ├── main.py        # full pipeline (entry point)
│   ├── config.py      # all thresholds and switches
│   ├── map.py         # floor graph, aliases, TTS display names
│   └── helpers.py     # normalize, intent extract, logging
├── models/
│   ├── moonshine/     # Moonshine ONNX model files (auto-downloaded)
│   └── embeddings/    # sentence-transformer cache (if embedding mode)
├── logs/
│   ├── commands.json  # structured command log
│   └── errors.log     # warning/error file log
├── requirements.txt
└── README.md
```

## Quick start

```bash
cd voice_robot
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
cd src
python main.py
```

## Configuration

All switches live in `src/config.py`:

| Key | Default | Description |
|-----|---------|-------------|
| `STT_BACKEND` | `"moonshine"` | STT engine: `"moonshine"`, `"google"`, `"vosk"` |
| `MATCH_MODE` | `"fuzzy"` | Matching: `"fuzzy"` or `"embedding"` |
| `FUZZY_THRESH` | `72` | RapidFuzz score threshold (0-100) |
| `EMBED_THRESH` | `0.42` | Cosine similarity threshold (0-1) |
| `USE_ROS2` | `False` | Set `True` only on a real ROS2 environment |
| `AUTO_RETURN_HOME` | `True` | Return to Medical Station after each delivery |

## Adding rooms

Edit `src/map.py`:
1. Add edges to `FLOOR_GRAPH`
2. Add a `DISPLAY` entry (TTS name)
3. Add aliases to `ALIASES`
4. Add a description to `LOCATION_DESCRIPTIONS` (for embedding mode)

## Pipeline

```
Mic → STT → Immediate ACK ("You said ___")
    → Normalize → Intent+Entity
    → Semantic Match (RapidFuzz or embeddings)
    → Val 1: keyword check
    → Val 2: room validity check
    → Confirmation TTS ("Did you mean ___?")
    → Confidence gate
    → Navigation + Logging
    → ROS2 publish  ‖  TTS feedback
    → [return to hub]
```

## On Windows / without ROS2

Set `USE_ROS2 = False` in `config.py`. The nav goal is logged to console instead of published.
`rclpy` is never imported when `USE_ROS2 = False`, so there is no crash.
