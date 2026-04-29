# ─────────────────────────────────────────────
#  map.py  –  floor graph + alias/description tables
#  Edit this file when the physical map changes.
# ─────────────────────────────────────────────
import networkx as nx

# ── Graph ─────────────────────────────────────
# Nodes = room keys  |  Edges = navigable connections
FLOOR_GRAPH = nx.Graph()
FLOOR_GRAPH.add_edges_from([
    ("medical_station", "general_room"),
    ("medical_station", "room_301"),
    ("medical_station", "room_302"),
    ("medical_station", "room_3003"),
    ("general_room",    "room_301"),
    ("room_301",        "room_302"),
    ("room_302",        "room_3003"),
])

LOCATIONS: list[str] = list(FLOOR_GRAPH.nodes)

# ── Human-readable names (used in TTS) ────────
DISPLAY: dict[str, str] = {
    "medical_station": "Medical Station",
    "general_room":    "General Room",
    "room_301":        "Room 3 0 1",    # spoken digit-by-digit sounds natural
    "room_302":        "Room 3 0 2",
    "room_3003":       "Room 3 0 0 3",
}

# ── Alias map  (for fuzzy mode) ───────────────
# KEY RULE: "room" alone must NOT match any single room –
#   it's too ambiguous. Require a number alongside it.
ALIASES: dict[str, list[str]] = {
    "medical_station": [
        "medical station", "medical", "station", "hub", "home",
        "base", "nurse station", "med station", "return", "back to base",
    ],
    "general_room": [
        "general room", "general", "common room", "common area",
        "lounge", "waiting room", "waiting area", "main room", "hall",
    ],
    "room_301": [
        "room 301", "301", "three o one", "three zero one",
        "room three o one", "room three zero one",
    ],
    "room_302": [
        "room 302", "302", "three o two", "three zero two",
        "room three o two", "room three zero two",
    ],
    "room_3003": [
        "room 3003", "3003", "three thousand three",
        "room three thousand three", "thirty o three",
    ],
}

# Flattened alias → location lookup (built once at import)
ALIAS_LOOKUP: dict[str, str] = {
    alias: loc
    for loc, aliases in ALIASES.items()
    for alias in aliases
}

# ── Rich descriptions (for embedding mode) ────
# More words = better semantic coverage for vague commands.
LOCATION_DESCRIPTIONS: dict[str, str] = {
    "medical_station": (
        "medical station nurse hub home base start return emergency "
        "healthcare medicine supplies treatment care"
    ),
    "general_room": (
        "general room common area lounge hall waiting area "
        "rest relax sit gather people open space"
    ),
    "room_301": "room 301 three zero one patient ward 301",
    "room_302": "room 302 three zero two patient ward 302",
    "room_3003": "room 3003 three thousand three patient ward 3003",
}
