"""server.py  --  Authoritative game server for Mini Multiplayer Bullet Game

Architecture notes
-------------------
*  Buff System   -- BUFF_DEFS   registry.  Add a key to get a new buff.
*  Pickup System -- PICKUP_DEFS registry.  Add a key + apply_pickup branch.
*  Weapon System -- WEAPON_DEFS registry.  fire_weapon() reads from it.
Each registry is a plain dict so new entries need zero boilerplate.
"""
import asyncio, json, math, os, random, time, websockets

# ── Config ───────────────────────────────────────────────────────
HOST            = "0.0.0.0"
PORT            = 8765
EMBEDDED_PORT   = 18765
TICK            = 0.05           # 20 TPS
BOUNDARY        = 50

PLAYER_INIT_HP  = 2
PLAYER_MAX_HP   = 4              # hearts can stack up to 4
PLAYER_R        = 0.6
BULLET_R        = 0.5
BULLET_SPEED    = 15.0

ENEMY_R         = {"small": 1.1, "big": 1.75}
ENEMY_SPD       = {"small": 1.5, "big": 0.8}
ENEMY_SH_CD     = {"small": 2.5, "big": 1.8}
ENEMY_BUL_SPD   = 8.0
SCORE_KILL      = {"small": 10,  "big": 50}
MAX_ENEMIES     = 10

SPAWN_INTERVAL  = 3.0
SPAWN_QUEUE_CD  = 1.5

PICKUP_SPAWN_CD = 5.0
MAX_PICKUPS     = 8

IMMORTAL_T      = 3.0
LEVEL_KILLS     = [6, 10, 15, 20, 25]

# =====================================================================
# ── Buff System (registry) ──────────────────────────────────────
#   To add a new buff:  1) add key here  2) check with has_buff()
# =====================================================================
BUFF_DEFS = {
    "immortal": {"duration": 3.0},
    "boost":    {"duration": 20.0},
    "shield":   {"duration": 999.0},     # stays until consumed by a hit
}

def apply_buff(p, name):
    """Grant buff *name* to player dict *p*."""
    p[f"{name}_t"] = BUFF_DEFS[name]["duration"]

def has_buff(p, name):
    return p.get(f"{name}_t", 0) > 0

def tick_buffs(p, dt):
    for name in BUFF_DEFS:
        key = f"{name}_t"
        if p.get(key, 0) > 0:
            p[key] = max(0, p[key] - dt)

def init_buff_fields(p):
    """Zero every buff timer (call once on player creation)."""
    for name in BUFF_DEFS:
        p[f"{name}_t"] = 0

# =====================================================================
# ── Pickup System (registry) ───────────────────────────────────
#   To add a new pickup:  1) add key+weight here  2) add branch in
#   apply_pickup()
# =====================================================================
PICKUP_DEFS = {
    "health":  {"weight": 50},
    "boost":   {"weight": 25},
    "shield":  {"weight": 25},
}

def random_pickup_type():
    types   = list(PICKUP_DEFS.keys())
    weights = [PICKUP_DEFS[t]["weight"] for t in types]
    return random.choices(types, weights=weights, k=1)[0]

def apply_pickup(p, ptype):
    """Apply pickup effect to player *p*.  Returns True if consumed."""
    if ptype == "health":
        if p.get("hp", PLAYER_INIT_HP) < PLAYER_MAX_HP:
            p["hp"] = min(PLAYER_MAX_HP, p["hp"] + 1)
            return True
        return False                    # already full
    if ptype in BUFF_DEFS:
        apply_buff(p, ptype)
        return True
    return False

# =====================================================================
# ── Weapon System (registry) ───────────────────────────────────
#   To add a new weapon:  add key here, then call fire_weapon(w=key)
# =====================================================================
WEAPON_DEFS = {
    "default": {"speed": BULLET_SPEED, "cooldown": 0.15,
                "damage": 1, "count": 1, "spread": 0.0},
}

def fire_weapon(g, p, pid, fdx, fdy, weapon="default"):
    """Spawn bullet(s) for player *pid* using weapon def."""
    w = WEAPON_DEFS[weapon]
    p["scd"] = w["cooldown"]
    base = math.atan2(fdy, fdx)
    for i in range(w["count"]):
        off = (i - (w["count"] - 1) / 2) * w["spread"]
        a = base + off
        g["bullets"].append({
            "id": g["_bid"], "x": p["x"], "y": p["y"],
            "vx": math.cos(a) * w["speed"],
            "vy": math.sin(a) * w["speed"],
            "owner": "player", "opid": pid, "dmg": w["damage"],
        })
        g["_bid"] += 1

# ── Helpers ──────────────────────────────────────────────────────
def clamp(v, lo, hi): return max(lo, min(hi, v))
def dist(a, b, c, d): return math.hypot(a - c, b - d)
def pt_in_rect(px, py, rx, ry, rw, rh):
    return rx <= px <= rx + rw and ry <= py <= ry + rh

def _random_spawn_pos():
    """Well-spread spawn position, avoids center 10-unit radius."""
    qx = random.choice([-1, 1])
    qy = random.choice([-1, 1])
    return (round(qx * random.uniform(12, BOUNDARY - 5), 1),
            round(qy * random.uniform(12, BOUNDARY - 5), 1))

# ── Global state ─────────────────────────────────────────────────
clients    = {}
players    = {}
rooms      = {}
room_games = {}
_nid       = 1
_lock      = asyncio.Lock()

# ── Map ──────────────────────────────────────────────────────────
def _load_map(name):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps", name)
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
        es.append({"x": ex, "y": ey, "type": "big" if random.random() < .2 else "small"})
    # mixed pickup types from the start
    ps = []
    for _ in range(random.randint(3, 5)):
        ps.append({"x": round(random.uniform(-40, 40), 1),
                    "y": round(random.uniform(-40, 40), 1),
                    "type": random_pickup_type()})
    return {"obstacles": obs, "enemy_spawns": es, "pickup_spawns": ps}

# ── Room game state ──────────────────────────────────────────────
def _init_room(room):
    try:
        m = _load_map("default.map")
    except Exception:
        m = _rand_map()
    g = {
        "obstacles": m.get("obstacles", []),
        "enemies": [], "bullets": [], "pickups": [],
        "_eid": 1, "_bid": 1,
        "_spawn_queue": [],
        "_spawn_cd": 0.0,
        "_spawn_timer": 0.0,
        "pickup_t": 0.0,
        "level": 1, "kills": 0,
        "kills_needed": LEVEL_KILLS[0],
        "level_clear": False,
        "_level_msg_t": 0.0,
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
        x, y = _random_spawn_pos()
        g["_spawn_queue"].append({"x": x, "y": y, "type": tp})
    g["pickups"] = []
    for s in m.get("pickup_spawns", []):
        g["pickups"].append({"x": s["x"], "y": s["y"],
                              "type": s.get("type", "health")})

def _game(room):
    return room_games.get(room) or _init_room(room)

# ── Net helpers ──────────────────────────────────────────────────
async def _send(ws, msg):
    try: await ws.send(msg)
    except Exception: pass

async def _bcast_lobby():
    info = json.dumps({"type": "lobby",
                       "rooms": [{"name": r, "count": len(p)} for r, p in rooms.items()]})
    await asyncio.gather(*[_send(ws, info) for ws in clients.values()],
                         return_exceptions=True)

async def _bcast_room(room):
    pids = rooms.get(room, set())
    if not pids:
        return
    g = room_games.get(room)
    pl = []
    for pid in pids:
        p = players.get(pid)
        if not p:
            continue
        pl.append({
            "id": pid, "x": round(p["x"], 2), "y": round(p["y"], 2),
            "name": p.get("name", ""),
            "hp": p.get("hp", PLAYER_INIT_HP),
            "max_hp": PLAYER_MAX_HP,
            "score": p.get("score", 0),
            "fdx": p.get("fdx", 1), "fdy": p.get("fdy", 0),
            "dead": p.get("dead", False),
            "immortal": has_buff(p, "immortal"),
            "shield":   has_buff(p, "shield"),
            "boost":    has_buff(p, "boost"),
        })
    msg = {"type": "state", "room": room, "players": pl}
    if g:
        msg["enemies"]   = [{"id": e["id"], "x": round(e["x"], 2), "y": round(e["y"], 2),
                              "hp": e["hp"], "mhp": e["mhp"], "tp": e["type"]}
                             for e in g["enemies"]]
        msg["bullets"]   = [{"x": round(b["x"], 2), "y": round(b["y"], 2), "ow": b["owner"]}
                             for b in g["bullets"]]
        msg["obstacles"] = g["obstacles"]
        msg["pickups"]   = [{"x": pk["x"], "y": pk["y"], "tp": pk.get("type", "health")}
                             for pk in g["pickups"]]
        msg["level"]        = g.get("level", 1)
        msg["kills"]        = g.get("kills", 0)
        msg["kills_needed"] = g.get("kills_needed", 6)
        msg["level_clear"]  = g.get("level_clear", False)
    s = json.dumps(msg)
    await asyncio.gather(*[_send(clients[pid], s) for pid in pids if pid in clients],
                         return_exceptions=True)

async def _send_hit(pid, absorbed=False):
    ws = clients.get(pid)
    if ws:
        await _send(ws, json.dumps({"type": "hit", "absorbed": absorbed}))

# ── Game tick ────────────────────────────────────────────────────
def _tick(room, dt):
    pids = rooms.get(room, set())
    g = room_games.get(room)
    if not g:
        return []
    hit_pids = []      # (pid, absorbed)

    alive = {pid: players[pid] for pid in pids
             if pid in players and not players[pid].get("dead")}

    # tick buffs + shoot cooldowns
    for pid in pids:
        p = players.get(pid)
        if not p:
            continue
        tick_buffs(p, dt)
        p["scd"] = max(0, p.get("scd", 0) - dt)

    # move bullets
    for b in g["bullets"]:
        b["x"] += b["vx"] * dt
        b["y"] += b["vy"] * dt

    # remove OOB bullets
    g["bullets"] = [b for b in g["bullets"]
                    if abs(b["x"]) <= BOUNDARY + 5 and abs(b["y"]) <= BOUNDARY + 5]

    # bullet <-> obstacle
    g["bullets"] = [b for b in g["bullets"]
                    if not any(pt_in_rect(b["x"], b["y"], o["x"], o["y"], o["w"], o["h"])
                               for o in g["obstacles"])]

    # ── bullet <-> bullet cancellation (player vs enemy) ────────
    p_idx = [i for i, b in enumerate(g["bullets"]) if b["owner"] == "player"]
    e_idx = [i for i, b in enumerate(g["bullets"]) if b["owner"] == "enemy"]
    cancel = set()
    for pi in p_idx:
        pb = g["bullets"][pi]
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
                    g["kills"] = g.get("kills", 0) + 1
                    op = b.get("opid")
                    if op and op in players:
                        players[op]["score"] += SCORE_KILL.get(e["type"], 10)
                break
    g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in rb]
    g["enemies"] = [e for e in g["enemies"] if e["id"] not in re]

    # level clear
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
                    p["shield_t"] = 0          # shield absorbs & breaks
                    hit_pids.append((pid, True))
                else:
                    p["hp"] = p.get("hp", PLAYER_INIT_HP) - 1
                    hit_pids.append((pid, False))
                    if p["hp"] <= 0:
                        p["dead"] = True
                break
    g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in rb2]

    # ── player <-> pickup (uses apply_pickup registry) ───────────
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

    # ── staggered spawns from queue ──────────────────────────────
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

    # ── spawn pickups (mixed types via registry) ─────────────────
    g["pickup_t"] += dt
    if g["pickup_t"] >= PICKUP_SPAWN_CD and len(g["pickups"]) < MAX_PICKUPS:
        g["pickup_t"] = 0
        g["pickups"].append({"x": round(random.uniform(-40, 40), 1),
                             "y": round(random.uniform(-40, 40), 1),
                             "type": random_pickup_type()})

    return hit_pids

# ── Tick loop ────────────────────────────────────────────────────
async def _tick_loop():
    while True:
        await asyncio.sleep(TICK)
        for room in list(rooms.keys()):
            if room in room_games:
                hits = _tick(room, TICK)
                for pid, absorbed in hits:
                    await _send_hit(pid, absorbed)
            await _bcast_room(room)

# ── Handler ──────────────────────────────────────────────────────
async def handler(ws):
    global _nid
    async with _lock:
        pid = str(_nid); _nid += 1
        clients[pid] = ws
        p = {"x": 0.0, "y": 0.0, "room": None, "name": "",
             "hp": PLAYER_INIT_HP, "score": 0,
             "fdx": 1, "fdy": 0, "dead": False, "scd": 0}
        init_buff_fields(p)
        players[pid] = p
    print(f"[srv] + client {pid}")
    try:
        await _send(ws, json.dumps({"type": "welcome", "id": pid}))
        await _bcast_lobby()
        async for raw in ws:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            t = data.get("type")

            if t == "join":
                room = data.get("room", "default")
                name = data.get("name", "")
                async with _lock:
                    old = players[pid].get("room")
                    if old and pid in rooms.get(old, set()):
                        rooms[old].discard(pid)
                    rooms.setdefault(room, set()).add(pid)
                    sx, sy = random.uniform(-5, 5), random.uniform(-5, 5)
                    players[pid].update(room=room, name=name,
                                         hp=PLAYER_INIT_HP, score=0, dead=False,
                                         x=sx, y=sy)
                    init_buff_fields(players[pid])
                    apply_buff(players[pid], "immortal")   # spawn immunity
                _game(room)
                print(f"[srv] {name}({pid}) -> room '{room}'")
                await _send(ws, json.dumps({"type": "joined", "room": room}))
                jm = json.dumps({"type": "player_join", "id": pid, "name": name})
                for p in rooms.get(room, set()):
                    w2 = clients.get(p)
                    if w2:
                        await _send(w2, jm)
                await _bcast_lobby()
                await _bcast_room(room)

            elif t == "pos":
                if players[pid].get("dead"):
                    continue
                players[pid]["x"] = clamp(float(data.get("x", 0)), -BOUNDARY, BOUNDARY)
                players[pid]["y"] = clamp(float(data.get("y", 0)), -BOUNDARY, BOUNDARY)
                fdx = data.get("fdx")
                fdy = data.get("fdy")
                if fdx is not None:
                    players[pid]["fdx"] = fdx
                    players[pid]["fdy"] = fdy

            elif t == "shoot":
                if players[pid].get("dead"):
                    continue
                if has_buff(players[pid], "immortal"):
                    continue                                   # can't shoot while immortal
                if players[pid].get("scd", 0) > 0:
                    continue
                room = players[pid].get("room")
                g = room_games.get(room)
                if not g:
                    continue
                fdx = float(data.get("fdx", players[pid].get("fdx", 1)))
                fdy = float(data.get("fdy", players[pid].get("fdy", 0)))
                ln = math.hypot(fdx, fdy)
                if ln > 0:
                    fdx /= ln; fdy /= ln
                    fire_weapon(g, players[pid], pid, fdx, fdy)

            elif t == "respawn":
                if not players[pid].get("dead"):
                    continue
                mode = data.get("mode", "random")
                if mode == "here":
                    pass                                       # stay at death pos
                else:
                    sx, sy = _random_spawn_pos()
                    players[pid]["x"] = sx
                    players[pid]["y"] = sy
                players[pid]["dead"] = False
                players[pid]["hp"] = PLAYER_INIT_HP
                init_buff_fields(players[pid])
                apply_buff(players[pid], "immortal")
                print(f"[srv] {players[pid]['name']}({pid}) respawned ({mode})")

    finally:
        async with _lock:
            clients.pop(pid, None)
            room = players.get(pid, {}).get("room")
            if room and pid in rooms.get(room, set()):
                lm = json.dumps({"type": "player_leave", "id": pid})
                for p in rooms.get(room, set()):
                    if p != pid:
                        w2 = clients.get(p)
                        if w2:
                            await _send(w2, lm)
                rooms[room].discard(pid)
                if not rooms[room]:
                    rooms.pop(room, None)
                    room_games.pop(room, None)
            players.pop(pid, None)
        print(f"[srv] - client {pid}")
        await _bcast_lobby()
        if room:
            await _bcast_room(room)

# ── Entry ────────────────────────────────────────────────────────
async def run_embedded():
    async with websockets.serve(handler, "localhost", EMBEDDED_PORT):
        asyncio.create_task(_tick_loop())
        await asyncio.Future()

async def main():
    print("+" + "=" * 42 + "+")
    print(f"|  Game Server   ws://{HOST}:{PORT}          |")
    print(f"|  Tick: {int(1/TICK)} TPS   Boundary: +/-{BOUNDARY}        |")
    print("+" + "=" * 42 + "+")
    async with websockets.serve(handler, HOST, PORT):
        asyncio.create_task(_tick_loop())
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
