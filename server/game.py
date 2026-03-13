"""server.game  --  Room / game-state management, tick loop, maps, enemy AI.

This is the "engine" — it owns the authoritative game state and steps
the simulation forward every tick.
"""
import asyncio, json, math, os, random

from server.config import (
    TICK, BOUNDARY,
    PLAYER_INIT_HP, PLAYER_MAX_HP, PLAYER_R,
    BULLET_R, BULLET_SPEED,
    ENEMY_R, ENEMY_SPD, ENEMY_SH_CD, ENEMY_BUL_SPD,
    SCORE_KILL, MAX_ENEMIES,
    SPAWN_INTERVAL, SPAWN_QUEUE_CD,
    PICKUP_SPAWN_CD, MAX_PICKUPS,
    LEVEL_KILLS, RESPAWN_KILL_PENALTY,
)
from server.buffs   import (
    has_buff, tick_buffs, apply_buff,
    init_buff_fields, clear_on_death,
    cancel_regen, cancel_rooted_regen,
)
from server.pickups import random_pickup_type, apply_pickup
from server.weapons import fire_weapon
from server.helpers import clamp, dist, pt_in_rect, random_spawn_pos

# ── Global mutable state ─────────────────────────────────────────
clients    = {}        # pid -> websocket
players    = {}        # pid -> player dict
rooms      = {}        # room_name -> set of pids
room_games = {}        # room_name -> game dict
_nid       = 1
_lock      = asyncio.Lock()

# ── Map helpers ──────────────────────────────────────────────────
_MAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "maps")


def _load_map(name):
    p = os.path.join(_MAP_DIR, name)
    with open(p) as f:
        return json.load(f)


def _rand_map():
    obs = []
    for _ in range(random.randint(8, 15)):
        w = round(random.uniform(1, 4), 1)
        h = round(random.uniform(1, 4), 1)
        x = round(random.uniform(-BOUNDARY + 3, BOUNDARY - 3 - w), 1)
        y = round(random.uniform(-BOUNDARY + 3, BOUNDARY - 3 - h), 1)
        if abs(x) < 8 and abs(y) < 8:
            continue
        obs.append({"x": x, "y": y, "w": w, "h": h})
    es = []
    for _ in range(random.randint(5, 8)):
        ex = round(random.uniform(-BOUNDARY + 5, BOUNDARY - 5), 1)
        ey = round(random.uniform(-BOUNDARY + 5, BOUNDARY - 5), 1)
        if abs(ex) < 10 and abs(ey) < 10:
            continue
        es.append({"x": ex, "y": ey, "type": "big" if random.random() < 0.2 else "small"})
    ps = []
    for _ in range(random.randint(3, 5)):
        ps.append({"x": round(random.uniform(-40, 40), 1),
                    "y": round(random.uniform(-40, 40), 1),
                    "type": random_pickup_type()})
    return {"obstacles": obs, "enemy_spawns": es, "pickup_spawns": ps}


# ── Room lifecycle ───────────────────────────────────────────────
def init_room(room):
    try:
        m = _load_map("default.map")
    except Exception:
        m = _rand_map()
    g = {
        "obstacles": m.get("obstacles", []),
        "enemies": [], "bullets": [], "pickups": [],
        "_eid": 1, "_bid": 1,
        "_spawn_queue": [],
        "_spawn_cd": 0.0, "_spawn_timer": 0.0,
        "pickup_t": 0.0,
        "level": 1, "kills": 0,
        "kills_needed": LEVEL_KILLS[0],
        "level_clear": False, "_level_msg_t": 0.0,
    }
    for s in m.get("enemy_spawns", []):
        g["_spawn_queue"].append({"x": s["x"], "y": s["y"], "type": s["type"]})
    for s in m.get("pickup_spawns", []):
        g["pickups"].append({"x": s["x"], "y": s["y"],
                              "type": s.get("type", "health")})
    room_games[room] = g
    return g


def _next_level(g):
    g["level"] += 1
    g["kills"] = 0
    lvl = g["level"]
    idx = min(lvl - 1, len(LEVEL_KILLS) - 1)
    g["kills_needed"] = LEVEL_KILLS[idx]
    g["level_clear"] = False
    g["_level_msg_t"] = 0.0
    g["enemies"] = []
    m = _rand_map()
    g["obstacles"] = m.get("obstacles", [])
    for _ in range(4 + lvl * 2):
        tp = "big" if random.random() < (0.1 + lvl * 0.05) else "small"
        x, y = random_spawn_pos()
        g["_spawn_queue"].append({"x": x, "y": y, "type": tp})
    g["pickups"] = []
    for s in m.get("pickup_spawns", []):
        g["pickups"].append({"x": s["x"], "y": s["y"],
                              "type": s.get("type", "health")})


def get_game(room):
    return room_games.get(room) or init_room(room)


# ── Tick ─────────────────────────────────────────────────────────
def tick(room, dt):
    """Advance one step.  Returns list of (pid, absorbed) hit events."""
    pids = rooms.get(room, set())
    g = room_games.get(room)
    if not g:
        return []
    hit_pids = []

    alive = {pid: players[pid] for pid in pids
             if pid in players and not players[pid].get("dead")}

    # ── per-player cooldowns ─────────────────────────────────────
    for pid in pids:
        p = players.get(pid)
        if not p:
            continue
        tick_buffs(p, dt)
        p["scd"] = max(0, p.get("scd", 0) - dt)
        # rooted-regen cancel on move
        if p.get("regen30_root_t", 0) > 0 and p.get("regen30_anchor"):
            ax, ay = p["regen30_anchor"]
            if dist(p.get("x", 0), p.get("y", 0), ax, ay) > 0.3:
                cancel_rooted_regen(p)

    # ── move bullets ─────────────────────────────────────────────
    for b in g["bullets"]:
        b["x"] += b["vx"] * dt
        b["y"] += b["vy"] * dt

    # ── bombs (ttl -> explosion) ─────────────────────────────────
    explode_idx = []
    for i, b in enumerate(g["bullets"]):
        if b.get("bomb"):
            b["ttl"] = b.get("ttl", 0) - dt
            if b["ttl"] <= 0:
                explode_idx.append(i)
    if explode_idx:
        dead_eids = set()
        for ei in sorted(explode_idx, reverse=True):
            b = g["bullets"].pop(ei)
            rad = b.get("expl_rad", 6.0)
            dmg = b.get("expl_dmg", 4)
            shooter = b.get("opid")
            for e in list(g["enemies"]):
                if dist(b["x"], b["y"], e["x"], e["y"]) <= rad:
                    e["hp"] -= dmg
                    if e["hp"] <= 0:
                        dead_eids.add(e["id"])
                        g["kills"] += 1
                        if shooter and shooter in players:
                            players[shooter]["score"] += SCORE_KILL.get(e.get("type", "small"), 10)
        if dead_eids:
            g["enemies"] = [e for e in g["enemies"] if e["id"] not in dead_eids]

    # remove OOB
    g["bullets"] = [b for b in g["bullets"]
                    if abs(b["x"]) <= BOUNDARY + 5 and abs(b["y"]) <= BOUNDARY + 5]
    # bullet <-> obstacle
    g["bullets"] = [b for b in g["bullets"]
                    if not any(pt_in_rect(b["x"], b["y"], o["x"], o["y"], o["w"], o["h"])
                               for o in g["obstacles"])]

    # ── bullet <-> bullet cancellation ───────────────────────────
    p_idx = [i for i, b in enumerate(g["bullets"]) if b["owner"] == "player"]
    e_idx = [i for i, b in enumerate(g["bullets"]) if b["owner"] == "enemy"]
    cancel = set()
    for pi in p_idx:
        pb = g["bullets"][pi]
        if not pb.get("can_cancel"):
            continue
        for ei in e_idx:
            if ei in cancel:
                continue
            eb = g["bullets"][ei]
            if dist(pb["x"], pb["y"], eb["x"], eb["y"]) < BULLET_R * 2 + 0.3:
                cancel.add(pi)
                cancel.add(ei)
                break
    if cancel:
        g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in cancel]

    # ── player-bullets -> enemies ────────────────────────────────
    rb, re = set(), set()
    for i, b in enumerate(g["bullets"]):
        if b["owner"] != "player":
            continue
        for e in g["enemies"]:
            sz = ENEMY_R.get(e["type"], 1.1)
            if dist(b["x"], b["y"], e["x"], e["y"]) < sz + BULLET_R:
                e["hp"] -= b.get("dmg", 1)
                rb.add(i)
                if e["hp"] <= 0:
                    re.add(e["id"])
                    g["kills"] += 1
                    op = b.get("opid")
                    if op and op in players:
                        pl = players[op]
                        pl["score"] += SCORE_KILL.get(e["type"], 10)
                        if has_buff(pl, "ability_double_kill"):
                            g["kills"] += 1
                            pl["score"] += SCORE_KILL.get(e["type"], 10)
                        if has_buff(pl, "ability_kill_heal"):
                            heal = PLAYER_MAX_HP * 0.02
                            pl["hp"] = min(PLAYER_MAX_HP, pl.get("hp", PLAYER_INIT_HP) + heal)
                        if has_buff(pl, "ability_kill_atk_speed"):
                            mul = pl.get("atk_speed_mul", 1.0) * 1.01
                            pl["atk_speed_mul"] = min(2.0, mul)
                            pl["atk_speed_t"]   = 10.0
                break
    g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in rb]
    g["enemies"] = [e for e in g["enemies"] if e["id"] not in re]

    # ── level clear ──────────────────────────────────────────────
    if not g.get("level_clear") and g["kills"] >= g.get("kills_needed", 6):
        g["level_clear"] = True
        g["_level_msg_t"] = 3.0
    if g.get("level_clear"):
        g["_level_msg_t"] -= dt
        if g["_level_msg_t"] <= 0:
            _next_level(g)

    # ── enemy-bullets -> players ─────────────────────────────────
    rb2 = set()
    for i, b in enumerate(g["bullets"]):
        if b["owner"] != "enemy":
            continue
        for pid, p in alive.items():
            if has_buff(p, "immortal"):
                continue
            if dist(b["x"], b["y"], p["x"], p["y"]) < PLAYER_R + BULLET_R:
                rb2.add(i)
                if has_buff(p, "shield"):
                    p["shield_t"] = 0
                    hit_pids.append((pid, True))
                else:
                    p["hp"] = p.get("hp", PLAYER_INIT_HP) - 1
                    cancel_regen(p)
                    hit_pids.append((pid, False))
                    if p["hp"] <= 0:
                        p["dead"] = True
                        clear_on_death(p)
                break
    g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in rb2]

    # ── player <-> pickup ────────────────────────────────────────
    rp = []
    for i, pk in enumerate(g["pickups"]):
        for pid, p in alive.items():
            if dist(pk["x"], pk["y"], p["x"], p["y"]) < PLAYER_R + 0.6:
                if apply_pickup(p, pk.get("type", "health")):
                    rp.append(i)
                break
    for i in sorted(rp, reverse=True):
        g["pickups"].pop(i)

    # ── enemy AI ─────────────────────────────────────────────────
    for e in g["enemies"]:
        if not alive:
            e["vx"] = e["vy"] = 0
            continue
        npid = min(alive, key=lambda pid: dist(e["x"], e["y"],
                                               alive[pid]["x"], alive[pid]["y"]))
        np = alive[npid]
        d = dist(e["x"], e["y"], np["x"], np["y"])
        spd = ENEMY_SPD.get(e["type"], 1.5)
        if d > 1:
            e["vx"] = (np["x"] - e["x"]) / d * spd
            e["vy"] = (np["y"] - e["y"]) / d * spd
        else:
            e["vx"] = e["vy"] = 0
        e["x"] = clamp(e["x"] + e["vx"] * dt, -BOUNDARY, BOUNDARY)
        e["y"] = clamp(e["y"] + e["vy"] * dt, -BOUNDARY, BOUNDARY)

        e["scd"] -= dt
        if e["scd"] <= 0 and d < 30:
            e["scd"] = ENEMY_SH_CD.get(e["type"], 2.5)
            if e["type"] == "small" and d > 0:
                bvx = (np["x"] - e["x"]) / d * ENEMY_BUL_SPD
                bvy = (np["y"] - e["y"]) / d * ENEMY_BUL_SPD
                g["bullets"].append({"id": g["_bid"], "x": e["x"], "y": e["y"],
                                     "vx": bvx, "vy": bvy, "owner": "enemy"})
                g["_bid"] += 1
            elif e["type"] == "big" and d > 0:
                base = math.atan2(np["y"] - e["y"], np["x"] - e["x"])
                for off in (-0.4, -0.2, 0, 0.2, 0.4):
                    a = base + off
                    g["bullets"].append({"id": g["_bid"], "x": e["x"], "y": e["y"],
                                         "vx": math.cos(a) * ENEMY_BUL_SPD,
                                         "vy": math.sin(a) * ENEMY_BUL_SPD,
                                         "owner": "enemy"})
                    g["_bid"] += 1

    # ── staggered spawns ─────────────────────────────────────────
    if g["_spawn_queue"] and len(g["enemies"]) < MAX_ENEMIES:
        g["_spawn_cd"] -= dt
        if g["_spawn_cd"] <= 0:
            s = g["_spawn_queue"].pop(0)
            hp = 2 if s["type"] == "small" else random.randint(5, 8)
            g["enemies"].append({"id": g["_eid"], "x": s["x"], "y": s["y"],
                                 "hp": hp, "mhp": hp, "type": s["type"],
                                 "vx": 0, "vy": 0, "scd": random.uniform(1, 3)})
            g["_eid"] += 1
            g["_spawn_cd"] = SPAWN_QUEUE_CD

    # periodic edge spawns
    if not g["_spawn_queue"] and not g.get("level_clear"):
        g["_spawn_timer"] += dt
        if g["_spawn_timer"] >= SPAWN_INTERVAL and len(g["enemies"]) < MAX_ENEMIES:
            g["_spawn_timer"] = 0
            side = random.randint(0, 3)
            if   side == 0: sx, sy = random.uniform(-BOUNDARY, BOUNDARY), -BOUNDARY + 2
            elif side == 1: sx, sy = random.uniform(-BOUNDARY, BOUNDARY),  BOUNDARY - 2
            elif side == 2: sx, sy = -BOUNDARY + 2, random.uniform(-BOUNDARY, BOUNDARY)
            else:           sx, sy =  BOUNDARY - 2, random.uniform(-BOUNDARY, BOUNDARY)
            lvl = g.get("level", 1)
            t = "big" if random.random() < (0.1 + lvl * 0.05) else "small"
            hp = 2 if t == "small" else random.randint(5, 8)
            g["enemies"].append({"id": g["_eid"], "x": sx, "y": sy,
                                 "hp": hp, "mhp": hp, "type": t,
                                 "vx": 0, "vy": 0, "scd": random.uniform(1, 3)})
            g["_eid"] += 1

    # ── spawn pickups ────────────────────────────────────────────
    g["pickup_t"] += dt
    if g["pickup_t"] >= PICKUP_SPAWN_CD and len(g["pickups"]) < MAX_PICKUPS:
        g["pickup_t"] = 0
        g["pickups"].append({"x": round(random.uniform(-40, 40), 1),
                             "y": round(random.uniform(-40, 40), 1),
                             "type": random_pickup_type()})

    return hit_pids
