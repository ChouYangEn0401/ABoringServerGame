"""server.pickups  --  Pickup registry and application logic.

HOW TO ADD A PICKUP
───────────────────
1. Add a key + ``{"weight": N}`` to ``PICKUP_DEFS``.
2. Add a branch in ``apply_pickup()`` for the effect.
The weight controls spawn probability relative to other pickups.
"""
import math, random
from server.config  import PLAYER_MAX_HP, PLAYER_INIT_HP
from server.buffs   import (BUFF_DEFS, apply_buff, init_buff_fields)
from server.weapons import WEAPON_AMMO

# ── Registry ─────────────────────────────────────────────────────
PICKUP_DEFS = {
    "health":                {"weight": 40},
    "double_heart":          {"weight": 15},
    "triple_heart":          {"weight": 10},
    "boost":                 {"weight": 15},
    "shield":                {"weight": 10},
    "muscle":                {"weight":  5},
    "cross":                 {"weight":  5},
    # weapons
    "machine_gun":           {"weight":  4},
    "shotgun":               {"weight":  3},
    "rifle":                 {"weight":  2},
    "bomb":                  {"weight":  2},
    # abilities
    "ability_bullet_cancel": {"weight":  2},
    "ability_double_kill":   {"weight":  2},
    "ability_kill_heal":     {"weight":  2},
    "ability_kill_atk_speed":{"weight":  2},
    "ability_extra_shots":   {"weight":  2},
}


def random_pickup_type():
    types   = list(PICKUP_DEFS.keys())
    weights = [PICKUP_DEFS[t]["weight"] for t in types]
    return random.choices(types, weights=weights, k=1)[0]


def apply_pickup(p, ptype):
    """Apply pickup effect to player *p*.  Returns True if consumed."""
    # ── healing ──────────────────────────────────────────────────
    if ptype == "health":
        amt = max(1, math.ceil(PLAYER_MAX_HP * 0.15))
        if p.get("hp", PLAYER_INIT_HP) < PLAYER_MAX_HP:
            p["hp"] = min(PLAYER_MAX_HP, p.get("hp", PLAYER_INIT_HP) + amt)
            return True
        return False

    if ptype == "double_heart":
        p["regen20_t"] = BUFF_DEFS["regen20"]["duration"]
        p.pop("regen20_total", None); p.pop("regen20_acc", None)
        return True

    if ptype == "triple_heart":
        p["regen30_root_t"] = BUFF_DEFS["regen30_root"]["duration"]
        p.pop("regen30_total", None); p.pop("regen30_acc", None)
        p.pop("regen30_anchor", None)
        return True

    # ── weapons ──────────────────────────────────────────────────
    if ptype in WEAPON_AMMO:
        p["weapon"]          = ptype
        p[f"ammo_{ptype}"]   = WEAPON_AMMO[ptype]
        return True

    # ── abilities ────────────────────────────────────────────────
    if ptype == "ability_bullet_cancel":
        apply_buff(p, "ability_bullet_cancel"); return True
    if ptype == "ability_double_kill":
        apply_buff(p, "ability_double_kill");   return True
    if ptype == "ability_kill_heal":
        apply_buff(p, "ability_kill_heal");     return True
    if ptype == "ability_kill_atk_speed":
        apply_buff(p, "ability_kill_atk_speed");return True
    if ptype == "ability_extra_shots":
        n = random.randint(2, 7)
        p["free_shots"]   = n
        p["free_shots_t"] = 10.0
        return True

    # ── other buffs ──────────────────────────────────────────────
    if ptype == "muscle":
        apply_buff(p, "muscle"); return True

    if ptype == "cross":
        if p.get("dead"):
            p["dead"] = False
            p["hp"]   = max(1, p.get("hp", PLAYER_INIT_HP))
            init_buff_fields(p)
            p["revive_immortal_t"] = BUFF_DEFS["revive_immortal"]["duration"]
            return True
        else:
            apply_buff(p, "revive_immortal")
            return True

    if ptype in BUFF_DEFS:
        apply_buff(p, ptype); return True

    return False
