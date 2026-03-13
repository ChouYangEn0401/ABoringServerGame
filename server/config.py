"""server.config  --  All game-server constants in one place.

To tweak balance, edit values here.  Every other server module imports
from this file so changes propagate automatically.
"""

# ── Network ──────────────────────────────────────────────────────
HOST          = "0.0.0.0"
PORT          = 8765
EMBEDDED_PORT = 18765
TICK          = 0.05        # 20 TPS

# ── World ────────────────────────────────────────────────────────
BOUNDARY = 50

# ── Player ───────────────────────────────────────────────────────
PLAYER_INIT_HP = 10
PLAYER_MAX_HP  = 10
PLAYER_R       = 0.6

# ── Bullet ───────────────────────────────────────────────────────
BULLET_R     = 0.5
BULLET_SPEED = 15.0

# ── Enemies ──────────────────────────────────────────────────────
ENEMY_R       = {"small": 1.1, "big": 1.75}
ENEMY_SPD     = {"small": 1.5, "big": 0.8}
ENEMY_SH_CD   = {"small": 2.5, "big": 1.8}
ENEMY_BUL_SPD = 8.0
SCORE_KILL    = {"small": 10,  "big": 50}
MAX_ENEMIES   = 10

# ── Spawning ─────────────────────────────────────────────────────
SPAWN_INTERVAL = 3.0
SPAWN_QUEUE_CD = 1.5

# ── Pickups ──────────────────────────────────────────────────────
PICKUP_SPAWN_CD = 5.0
MAX_PICKUPS     = 8

# ── Progression ──────────────────────────────────────────────────
IMMORTAL_T      = 3.0
LEVEL_KILLS     = [6, 10, 15, 20, 25]
RESPAWN_KILL_PENALTY = 5      # kills subtracted on respawn
