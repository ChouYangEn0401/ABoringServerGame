"""client.config  --  Display constants, colours, pickup visuals.

Edit values here to change anything visual without touching game logic.
"""

# ── Window ───────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 600
TILE          = 8
SPEED         = 5.0
SEND_HZ       = 20
BOUNDARY      = 50
MSG_TTL       = 5.0

# ── Hit-feedback timers ──────────────────────────────────────────
SHAKE_DURATION      = 0.25
SHAKE_INTENSITY     = 8
RED_FLASH_DURATION  = 0.35
BLUE_FLASH_DURATION = 0.30

# ── Colour palette ───────────────────────────────────────────────
COL = {
    "bg":    (20, 20, 30),
    "grid":  (30, 30, 42),
    "bound": (120, 60, 60),
    "self":  (80, 160, 255),
    "other": (200, 120, 120),
    "dead":  (80, 80, 80),
    "esm":   (50, 200, 50),
    "ebg":   (255, 150, 50),
    "bul_p": (255, 255, 100),
    "bul_e": (255, 100, 100),
    "obs":   (70, 70, 90),
    "txt":   (200, 200, 200),
    "dim":   (140, 140, 140),
}

# ── Pickup visual definitions ────────────────────────────────────
#   Mirrors server PICKUP_DEFS.  Each entry carries:
#     bg, border  — fill / outline colours
#     label       — short text drawn under the icon
#     shape       — "circle" | "diamond" | "shield" | "cross" | "rect"
PICKUP_VIS = {
    "health":        {"bg": (255, 80, 120),  "border": (200, 40, 80),   "label": "+",  "shape": "circle"},
    "double_heart":  {"bg": (255, 120, 160), "border": (200, 80, 120),  "label": "++", "shape": "circle"},
    "triple_heart":  {"bg": (255, 160, 200), "border": (220, 100, 140), "label": "3+", "shape": "circle"},
    "boost":         {"bg": (255, 220,  50), "border": (200, 170, 10),  "label": "B",  "shape": "diamond"},
    "shield":        {"bg": (100, 180, 255), "border": (40, 120, 220),  "label": "S",  "shape": "shield"},
    "muscle":        {"bg": (220, 80, 40),   "border": (180, 50, 20),   "label": "M",  "shape": "diamond"},
    "cross":         {"bg": (255, 255, 200), "border": (200, 200, 120), "label": "X",  "shape": "cross"},
    # weapons
    "machine_gun":   {"bg": (200, 200, 60),  "border": (160, 160, 30),  "label": "MG", "shape": "rect"},
    "shotgun":       {"bg": (180, 100, 40),  "border": (140, 70, 20),   "label": "SG", "shape": "rect"},
    "rifle":         {"bg": (60, 180, 200),  "border": (30, 140, 160),  "label": "RF", "shape": "rect"},
    "bomb":          {"bg": (80, 80, 80),    "border": (200, 60, 60),   "label": "BM", "shape": "circle"},
    # abilities
    "ability_bullet_cancel":  {"bg": (180, 60, 220),  "border": (140, 30, 180),  "label": "BC", "shape": "diamond"},
    "ability_double_kill":    {"bg": (220, 180, 60),  "border": (180, 140, 30),  "label": "x2", "shape": "diamond"},
    "ability_kill_heal":      {"bg": (60, 220, 120),  "border": (30, 180, 80),   "label": "KH", "shape": "diamond"},
    "ability_kill_atk_speed": {"bg": (220, 120, 60),  "border": (180, 80, 30),   "label": "AS", "shape": "diamond"},
    "ability_extra_shots":    {"bg": (120, 60, 220),  "border": (80, 30, 180),   "label": "FS", "shape": "diamond"},
}

# ── Weapon display helpers ───────────────────────────────────────
WEAPON_NAMES = {
    "pistol": "Pistol", "machine_gun": "Machine Gun",
    "shotgun": "Shotgun", "rifle": "Rifle", "bomb": "Bomb",
}
WEAPON_COLOURS = {
    "pistol": (180, 180, 180), "machine_gun": (200, 200, 60),
    "shotgun": (180, 100, 40), "rifle": (60, 180, 200), "bomb": (200, 60, 60),
}
WEAPON_COOLDOWNS = {
    "pistol": 0.35, "machine_gun": 0.05,
    "shotgun": 0.8, "rifle": 0.4, "bomb": 1.2,
}
