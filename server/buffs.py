"""server.buffs  --  Buff registry and tick logic.

HOW TO ADD A BUFF
─────────────────
1. Add a key to ``BUFF_DEFS`` with ``{"duration": <seconds>}``.
2. Grant it with ``apply_buff(player, "your_key")``.
3. Check it with ``has_buff(player, "your_key")``.
That's it — tick_buffs() counts it down automatically.
"""
import math
from server.config import PLAYER_MAX_HP, PLAYER_INIT_HP

# ── Registry ─────────────────────────────────────────────────────
BUFF_DEFS = {
    "immortal":              {"duration": 3.0},
    "boost":                 {"duration": 20.0},
    "shield":                {"duration": 999.0},
    "regen20":               {"duration": 10.0},
    "regen30_root":          {"duration": 5.0},
    "muscle":                {"duration": 20.0},
    "revive_immortal":       {"duration": 5.0},
    # GameAbility buffs
    "ability_bullet_cancel": {"duration": 20.0},
    "ability_double_kill":   {"duration": 20.0},
    "ability_kill_heal":     {"duration": 20.0},
    "ability_kill_atk_speed":{"duration": 20.0},
}


# ── Public API ───────────────────────────────────────────────────
def apply_buff(p, name):
    """Grant buff *name* to player dict *p*."""
    p[f"{name}_t"] = BUFF_DEFS[name]["duration"]


def has_buff(p, name):
    return p.get(f"{name}_t", 0) > 0


def init_buff_fields(p):
    """Zero every buff timer + auxiliary fields (call on create / respawn)."""
    for name in BUFF_DEFS:
        p[f"{name}_t"] = 0
    p["atk_speed_mul"] = 1.0
    p["atk_speed_t"]   = 0.0
    p["free_shots"]    = 0
    p["free_shots_t"]  = 0.0


def clear_on_death(p):
    """Strip all buffs, abilities and weapon on death."""
    init_buff_fields(p)
    p["weapon"] = "pistol"


def tick_buffs(p, dt):
    """Tick every registered buff timer + special regen / atk-speed logic."""
    # generic countdown
    for name in BUFF_DEFS:
        key = f"{name}_t"
        if p.get(key, 0) > 0:
            p[key] = max(0, p[key] - dt)

    # ── regen20: heal 20 % of max HP over 10 s ──────────────────
    if p.get("regen20_t", 0) > 0:
        total = p.get("regen20_total", 0)
        if total <= 0:
            total = math.ceil(PLAYER_MAX_HP * 0.20)
            p["regen20_total"] = total
            p["regen20_acc"]   = 0.0
        rate = p.get("regen20_total", 0) / max(0.0001, 10.0)
        p["regen20_acc"] = p.get("regen20_acc", 0.0) + rate * dt
        while p.get("regen20_acc", 0) >= 1.0 and p.get("regen20_total", 0) > 0:
            if p.get("hp", PLAYER_INIT_HP) < PLAYER_MAX_HP:
                p["hp"] = min(PLAYER_MAX_HP, p.get("hp", PLAYER_INIT_HP) + 1)
            p["regen20_acc"]   -= 1.0
            p["regen20_total"]  = max(0, p["regen20_total"] - 1)
        if p.get("regen20_total", 0) <= 0:
            p["regen20_t"] = 0

    # ── regen30_root: heal 30 % of max HP over 5 s, rooted ──────
    if p.get("regen30_root_t", 0) > 0:
        total = p.get("regen30_total", 0)
        if total <= 0:
            total = math.ceil(PLAYER_MAX_HP * 0.30)
            p["regen30_total"] = total
            p["regen30_acc"]   = 0.0
            p["regen30_anchor"] = (p.get("x", 0.0), p.get("y", 0.0))
        rate = p.get("regen30_total", 0) / max(0.0001, 5.0)
        p["regen30_acc"] = p.get("regen30_acc", 0.0) + rate * dt
        while p.get("regen30_acc", 0) >= 1.0 and p.get("regen30_total", 0) > 0:
            if p.get("hp", PLAYER_INIT_HP) < PLAYER_MAX_HP:
                p["hp"] = min(PLAYER_MAX_HP, p.get("hp", PLAYER_INIT_HP) + 1)
            p["regen30_acc"]   -= 1.0
            p["regen30_total"]  = max(0, p["regen30_total"] - 1)
        if p.get("regen30_total", 0) <= 0:
            p["regen30_root_t"] = 0
            p.pop("regen30_anchor", None)

    # ── atk-speed-on-kill timer ──────────────────────────────────
    if p.get("atk_speed_t", 0) > 0:
        p["atk_speed_t"] = max(0, p["atk_speed_t"] - dt)
        if p["atk_speed_t"] <= 0:
            p["atk_speed_mul"] = 1.0

    # ── free-shots timer ─────────────────────────────────────────
    if p.get("free_shots_t", 0) > 0:
        p["free_shots_t"] = max(0, p["free_shots_t"] - dt)
        if p["free_shots_t"] <= 0:
            p["free_shots"] = 0


def cancel_regen(p):
    """Cancel any active regen buff (called on taking damage)."""
    p["regen20_t"] = 0
    p.pop("regen20_total", None)
    p.pop("regen20_acc", None)
    p["regen30_root_t"] = 0
    p.pop("regen30_total", None)
    p.pop("regen30_acc", None)
    p.pop("regen30_anchor", None)


def cancel_rooted_regen(p):
    """Cancel rooted regen only (called when player moves)."""
    p["regen30_root_t"] = 0
    p.pop("regen30_total", None)
    p.pop("regen30_acc", None)
    p.pop("regen30_anchor", None)
