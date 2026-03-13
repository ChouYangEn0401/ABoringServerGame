"""server.weapons  --  Weapon registry and fire logic.

HOW TO ADD A WEAPON
───────────────────
1. Add a key to ``WEAPON_DEFS``.
2. ``fire_weapon()`` reads from it automatically.
3. Optionally add a matching pickup in ``server.pickups``.
"""
import math, random
from server.config import BULLET_SPEED, PLAYER_MAX_HP
from server.buffs  import has_buff

# ── Registry ─────────────────────────────────────────────────────
WEAPON_DEFS = {
    "pistol":      {"speed": BULLET_SPEED,       "cooldown": 0.35, "damage": 1.0,
                    "count": 1, "spread": 0.0},
    "machine_gun": {"speed": BULLET_SPEED,       "cooldown": 0.05, "damage": 0.4,
                    "count": 1, "spread": 0.02},
    "shotgun":     {"speed": BULLET_SPEED * 0.9, "cooldown": 0.8,  "damage": 0.7,
                    "count": 6, "spread": 0.6},
    "rifle":       {"speed": BULLET_SPEED * 1.6, "cooldown": 0.4,  "damage": 3.0,
                    "count": 1, "spread": 0.0},
    "bomb":        {"speed": BULLET_SPEED * 0.6, "cooldown": 1.2,  "damage": 0,
                    "count": 1, "spread": 0.0,
                    "expl_dmg": 4, "expl_rad": 6.0, "ttl": 1.2},
}

# Ammo given when picking up a weapon
WEAPON_AMMO = {
    "machine_gun": 40,
    "shotgun":     20,
    "rifle":        5,
    "bomb":        30,
}


# ── Public API ───────────────────────────────────────────────────
def fire_weapon(g, p, pid, fdx, fdy, weapon=None):
    """Spawn bullet(s) for *pid* using their equipped weapon."""
    weapon = weapon or p.get("weapon", "pistol")
    if weapon not in WEAPON_DEFS:
        weapon = "pistol"

    # ammo gate
    if weapon != "pistol":
        ammo_k = f"ammo_{weapon}"
        if p.get(ammo_k, 0) <= 0:
            p["weapon"] = "pistol"
            weapon = "pistol"

    w = WEAPON_DEFS[weapon]
    # apply atk-speed multiplier to cooldown
    mul = p.get("atk_speed_mul", 1.0)
    p["scd"] = w["cooldown"] / max(mul, 0.5)
    base = math.atan2(fdy, fdx)

    dmg_mul = 2.0 if has_buff(p, "muscle") else 1.0

    cnt = random.randint(5, 8) if weapon == "shotgun" else w.get("count", 1)

    for i in range(cnt):
        off = (i - (cnt - 1) / 2) * w.get("spread", 0.0)
        if weapon == "machine_gun":
            off += random.uniform(-0.02, 0.02)
        a = base + off
        vx = math.cos(a) * w.get("speed", BULLET_SPEED)
        vy = math.sin(a) * w.get("speed", BULLET_SPEED)

        if weapon == "bomb":
            g["bullets"].append({
                "id": g["_bid"], "x": p["x"], "y": p["y"],
                "vx": vx, "vy": vy, "owner": "player", "opid": pid,
                "bomb": True, "ttl": w.get("ttl", 1.2),
                "expl_dmg": w.get("expl_dmg", 4),
                "expl_rad": w.get("expl_rad", 6.0),
            })
            g["_bid"] += 1
            break

        nb = {
            "id": g["_bid"], "x": p["x"], "y": p["y"],
            "vx": vx, "vy": vy,
            "owner": "player", "opid": pid,
            "dmg": w.get("damage", 1.0) * dmg_mul,
        }
        if has_buff(p, "ability_bullet_cancel"):
            nb["can_cancel"] = True
        g["bullets"].append(nb)
        g["_bid"] += 1

    # consume ammo (free-shots used first)
    if weapon != "pistol":
        used_free = False
        if p.get("free_shots", 0) > 0:
            p["free_shots"] = max(0, p["free_shots"] - 1)
            used_free = True
        if not used_free:
            ammo_k = f"ammo_{weapon}"
            if p.get(ammo_k, 0) > 0:
                p[ammo_k] = max(0, p[ammo_k] - 1)
            if p.get(ammo_k, 0) <= 0:
                p["weapon"] = "pistol"
