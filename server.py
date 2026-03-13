"""server.py ── Authoritative game server for Mini Multiplayer Bullet Game"""
import asyncio, json, math, os, random, websockets

# ── Config ───────────────────────────────────────────────────────
HOST            = "0.0.0.0"
PORT            = 8765
EMBEDDED_PORT   = 18765
TICK            = 0.05           # 20 TPS
BOUNDARY        = 50

PLAYER_MAX_HP   = 2
PLAYER_SHOOT_CD = 0.15
BULLET_SPEED    = 15.0
BULLET_R        = 0.3
PLAYER_R        = 0.5

ENEMY_R         = {"small": 0.4, "big": 0.6}
ENEMY_SPD       = {"small": 1.5, "big": 0.8}
ENEMY_SH_CD     = {"small": 2.5, "big": 1.8}
ENEMY_BUL_SPD   = 8.0
SCORE_KILL      = {"small": 10,  "big": 50}
ENEMY_SPAWN_CD  = 5.0
MAX_ENEMIES     = 12

PICKUP_SPAWN_CD = 8.0
MAX_PICKUPS     = 5
RESPAWN_T       = 3.0

# ── Global state ─────────────────────────────────────────────────
clients    = {}          # pid → ws
players    = {}          # pid → dict
rooms      = {}          # room → set(pid)
room_games = {}          # room → game‑dict
_nid       = 1
_lock      = asyncio.Lock()

# ── Helpers ──────────────────────────────────────────────────────
def clamp(v, lo, hi): return max(lo, min(hi, v))
def dist(a, b, c, d): return math.hypot(a - c, b - d)
def pt_in_rect(px, py, rx, ry, rw, rh):
    return rx <= px <= rx + rw and ry <= py <= ry + rh

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
    ps = [{"x": round(random.uniform(-40, 40), 1),
           "y": round(random.uniform(-40, 40), 1), "type": "health"}
          for _ in range(random.randint(2, 4))]
    return {"obstacles": obs, "enemy_spawns": es, "pickup_spawns": ps}

# ── Room game state ──────────────────────────────────────────────
def _init_room(room):
    try:
        m = _load_map("default.map")
    except Exception:
        m = _rand_map()
    g = {"obstacles": m.get("obstacles", []),
         "enemies": [], "bullets": [], "pickups": [],
         "_eid": 1, "_bid": 1,
         "spawn_t": 0.0, "pickup_t": 0.0}
    for s in m.get("enemy_spawns", []):
        hp = 2 if s["type"] == "small" else random.randint(5, 8)
        g["enemies"].append({"id": g["_eid"], "x": s["x"], "y": s["y"],
                             "hp": hp, "mhp": hp, "type": s["type"],
                             "vx": 0, "vy": 0, "scd": random.uniform(0, 2)})
        g["_eid"] += 1
    for s in m.get("pickup_spawns", []):
        g["pickups"].append({"x": s["x"], "y": s["y"], "type": s["type"]})
    room_games[room] = g
    return g

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
        pl.append({"id": pid, "x": round(p["x"], 2), "y": round(p["y"], 2),
                   "name": p.get("name", ""), "hp": p.get("hp", PLAYER_MAX_HP),
                   "score": p.get("score", 0),
                   "fdx": p.get("fdx", 1), "fdy": p.get("fdy", 0),
                   "dead": p.get("dead", False)})
    msg = {"type": "state", "room": room, "players": pl}
    if g:
        msg["enemies"]   = [{"id": e["id"], "x": round(e["x"], 2), "y": round(e["y"], 2),
                              "hp": e["hp"], "mhp": e["mhp"], "tp": e["type"]}
                             for e in g["enemies"]]
        msg["bullets"]   = [{"x": round(b["x"], 2), "y": round(b["y"], 2), "ow": b["owner"]}
                             for b in g["bullets"]]
        msg["obstacles"] = g["obstacles"]
        msg["pickups"]   = [{"x": pk["x"], "y": pk["y"]} for pk in g["pickups"]]
    s = json.dumps(msg)
    await asyncio.gather(*[_send(clients[pid], s) for pid in pids if pid in clients],
                         return_exceptions=True)

# ── Game tick ────────────────────────────────────────────────────
def _tick(room, dt):
    pids = rooms.get(room, set())
    g = room_games.get(room)
    if not g:
        return
    alive = {pid: players[pid] for pid in pids
             if pid in players and not players[pid].get("dead")}

    # respawn
    for pid in pids:
        p = players.get(pid)
        if p and p.get("dead"):
            p["_rt"] = p.get("_rt", RESPAWN_T) - dt
            if p["_rt"] <= 0:
                p["dead"] = False
                p["hp"] = PLAYER_MAX_HP
                p["x"] = random.uniform(-5, 5)
                p["y"] = random.uniform(-5, 5)

    # player shoot cooldowns
    for pid in pids:
        p = players.get(pid)
        if p:
            p["scd"] = max(0, p.get("scd", 0) - dt)

    # move bullets
    for b in g["bullets"]:
        b["x"] += b["vx"] * dt
        b["y"] += b["vy"] * dt

    # remove OOB bullets
    g["bullets"] = [b for b in g["bullets"]
                    if abs(b["x"]) <= BOUNDARY + 5 and abs(b["y"]) <= BOUNDARY + 5]

    # bullet ↔ obstacle
    g["bullets"] = [b for b in g["bullets"]
                    if not any(pt_in_rect(b["x"], b["y"], o["x"], o["y"], o["w"], o["h"])
                               for o in g["obstacles"])]

    # player‑bullets → enemies
    rb, re = set(), set()
    for i, b in enumerate(g["bullets"]):
        if b["owner"] != "player":
            continue
        for e in g["enemies"]:
            sz = ENEMY_R.get(e["type"], 0.4)
            if dist(b["x"], b["y"], e["x"], e["y"]) < sz + BULLET_R:
                e["hp"] -= 1
                rb.add(i)
                if e["hp"] <= 0:
                    re.add(e["id"])
                    op = b.get("opid")
                    if op and op in players:
                        players[op]["score"] = players[op].get("score", 0) + SCORE_KILL.get(e["type"], 10)
                break
    g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in rb]
    g["enemies"] = [e for e in g["enemies"] if e["id"] not in re]

    # enemy‑bullets → players
    rb2 = set()
    for i, b in enumerate(g["bullets"]):
        if b["owner"] != "enemy":
            continue
        for pid, p in alive.items():
            if dist(b["x"], b["y"], p["x"], p["y"]) < PLAYER_R + BULLET_R:
                p["hp"] = p.get("hp", PLAYER_MAX_HP) - 1
                rb2.add(i)
                if p["hp"] <= 0:
                    p["dead"] = True
                    p["_rt"] = RESPAWN_T
                break
    g["bullets"] = [b for i, b in enumerate(g["bullets"]) if i not in rb2]

    # player ↔ pickup
    rp = []
    for i, pk in enumerate(g["pickups"]):
        for pid, p in alive.items():
            if p.get("hp", PLAYER_MAX_HP) < PLAYER_MAX_HP:
                if dist(pk["x"], pk["y"], p["x"], p["y"]) < PLAYER_R + 0.5:
                    p["hp"] = min(PLAYER_MAX_HP, p["hp"] + 1)
                    rp.append(i)
                    break
    for i in sorted(rp, reverse=True):
        g["pickups"].pop(i)

    # enemy AI
    for e in g["enemies"]:
        if not alive:
            e["vx"] = e["vy"] = 0
            continue
        npid = min(alive, key=lambda pid: dist(e["x"], e["y"], alive[pid]["x"], alive[pid]["y"]))
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

    # spawn enemies
    g["spawn_t"] += dt
    if g["spawn_t"] >= ENEMY_SPAWN_CD and len(g["enemies"]) < MAX_ENEMIES:
        g["spawn_t"] = 0
        side = random.randint(0, 3)
        if   side == 0: sx, sy = random.uniform(-BOUNDARY, BOUNDARY), -BOUNDARY + 2
        elif side == 1: sx, sy = random.uniform(-BOUNDARY, BOUNDARY),  BOUNDARY - 2
        elif side == 2: sx, sy = -BOUNDARY + 2, random.uniform(-BOUNDARY, BOUNDARY)
        else:           sx, sy =  BOUNDARY - 2, random.uniform(-BOUNDARY, BOUNDARY)
        t = "big" if random.random() < 0.15 else "small"
        hp = 2 if t == "small" else random.randint(5, 8)
        g["enemies"].append({"id": g["_eid"], "x": sx, "y": sy,
                             "hp": hp, "mhp": hp, "type": t,
                             "vx": 0, "vy": 0, "scd": random.uniform(1, 3)})
        g["_eid"] += 1

    # spawn pickups
    g["pickup_t"] += dt
    if g["pickup_t"] >= PICKUP_SPAWN_CD and len(g["pickups"]) < MAX_PICKUPS:
        g["pickup_t"] = 0
        g["pickups"].append({"x": round(random.uniform(-40, 40), 1),
                             "y": round(random.uniform(-40, 40), 1), "type": "health"})

# ── Tick loop ────────────────────────────────────────────────────
async def _tick_loop():
    while True:
        await asyncio.sleep(TICK)
        for room in list(rooms.keys()):
            if room in room_games:
                _tick(room, TICK)
            await _bcast_room(room)

# ── Handler ──────────────────────────────────────────────────────
async def handler(ws):
    global _nid
    async with _lock:
        pid = str(_nid); _nid += 1
        clients[pid] = ws
        players[pid] = {"x": 0.0, "y": 0.0, "room": None, "name": "",
                        "hp": PLAYER_MAX_HP, "score": 0,
                        "fdx": 1, "fdy": 0, "dead": False, "scd": 0}
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
                    players[pid].update(room=room, name=name, hp=PLAYER_MAX_HP,
                                        score=0, dead=False,
                                        x=random.uniform(-5, 5),
                                        y=random.uniform(-5, 5))
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
                    players[pid]["scd"] = PLAYER_SHOOT_CD
                    g["bullets"].append({"id": g["_bid"],
                                         "x": players[pid]["x"],
                                         "y": players[pid]["y"],
                                         "vx": fdx * BULLET_SPEED,
                                         "vy": fdy * BULLET_SPEED,
                                         "owner": "player", "opid": pid})
                    g["_bid"] += 1

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
    """Start a local‑only server (for single‑player mode)."""
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
