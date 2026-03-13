"""server.network  --  WebSocket handler &amp; broadcasting.

Owns the wire protocol (JSON messages) and translates between
network events and the game state managed by ``server.game``.
"""
import asyncio, json, math, random

from server.config import (
    TICK, BOUNDARY,
    PLAYER_INIT_HP, PLAYER_MAX_HP,
    EMBEDDED_PORT, HOST, PORT,
    RESPAWN_KILL_PENALTY,
)
from server.buffs   import has_buff, apply_buff, init_buff_fields, cancel_rooted_regen
from server.weapons import fire_weapon
from server.helpers import clamp, dist, random_spawn_pos
from server.game    import (
    clients, players, rooms, room_games,
    _lock, get_game, tick,
)

# ── send / broadcast ─────────────────────────────────────────────
async def _send(ws, msg):
    try:
        await ws.send(msg)
    except Exception:
        pass


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
            "muscle":   has_buff(p, "muscle"),
            "regen20":  p.get("regen20_t", 0) > 0,
            "regen30":  p.get("regen30_root_t", 0) > 0,
            "revive_immortal": p.get("revive_immortal_t", 0) > 0,
            "weapon": p.get("weapon", "pistol"),
            "ammo": p.get(f"ammo_{p.get('weapon','pistol')}", 0),
            "ability_bullet_cancel": has_buff(p, "ability_bullet_cancel"),
            "ability_double_kill": has_buff(p, "ability_double_kill"),
            "ability_kill_heal": has_buff(p, "ability_kill_heal"),
            "ability_kill_atk_speed": has_buff(p, "ability_kill_atk_speed"),
            "atk_speed_mul": p.get("atk_speed_mul", 1.0),
            "free_shots": p.get("free_shots", 0),
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


# ── tick loop ────────────────────────────────────────────────────
async def tick_loop():
    while True:
        await asyncio.sleep(TICK)
        for room in list(rooms.keys()):
            if room in room_games:
                hits = tick(room, TICK)
                for pid, absorbed in hits:
                    await _send_hit(pid, absorbed)
            await _bcast_room(room)


# ── WebSocket handler ────────────────────────────────────────────
async def handler(ws):
    import server.game as _g          # mutable _nid lives here
    async with _lock:
        pid = str(_g._nid); _g._nid += 1
        clients[pid] = ws
        p = {"x": 0.0, "y": 0.0, "room": None, "name": "",
             "hp": PLAYER_INIT_HP, "score": 0,
             "fdx": 1, "fdy": 0, "dead": False, "scd": 0,
             "weapon": "pistol"}
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
                    apply_buff(players[pid], "immortal")
                get_game(room)
                print(f"[srv] {name}({pid}) -> room '{room}'")
                await _send(ws, json.dumps({"type": "joined", "room": room}))
                jm = json.dumps({"type": "player_join", "id": pid, "name": name})
                for p2 in rooms.get(room, set()):
                    w2 = clients.get(p2)
                    if w2:
                        await _send(w2, jm)
                await _bcast_lobby()
                await _bcast_room(room)

            elif t == "pos":
                if players[pid].get("dead"):
                    continue
                px = clamp(float(data.get("x", 0)), -BOUNDARY, BOUNDARY)
                py = clamp(float(data.get("y", 0)), -BOUNDARY, BOUNDARY)
                fdx = data.get("fdx")
                fdy = data.get("fdy")
                if players[pid].get("regen30_root_t", 0) > 0:
                    anchor = players[pid].get("regen30_anchor")
                    if not anchor:
                        players[pid]["regen30_anchor"] = (
                            players[pid].get("x", 0.0),
                            players[pid].get("y", 0.0))
                    else:
                        ax, ay = anchor
                        if dist(px, py, ax, ay) > 0.3:
                            cancel_rooted_regen(players[pid])
                            players[pid]["x"] = px
                            players[pid]["y"] = py
                else:
                    players[pid]["x"] = px
                    players[pid]["y"] = py
                if fdx is not None:
                    players[pid]["fdx"] = fdx
                    players[pid]["fdy"] = fdy

            elif t == "shoot":
                if players[pid].get("dead"):
                    continue
                if has_buff(players[pid], "immortal"):
                    continue
                if players[pid].get("regen30_root_t", 0) > 0:
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
                    fire_weapon(g, players[pid], pid, fdx, fdy)

            elif t == "respawn":
                if not players[pid].get("dead"):
                    continue
                mode = data.get("mode", "random")
                if mode != "here":
                    sx, sy = random_spawn_pos()
                    players[pid]["x"] = sx
                    players[pid]["y"] = sy
                players[pid]["dead"] = False
                players[pid]["hp"]   = PLAYER_INIT_HP
                players[pid]["weapon"] = "pistol"
                init_buff_fields(players[pid])
                apply_buff(players[pid], "immortal")
                # respawn penalty: subtract kills
                room = players[pid].get("room")
                g = room_games.get(room)
                if g:
                    g["kills"] = max(0, g["kills"] - RESPAWN_KILL_PENALTY)
                print(f"[srv] {players[pid]['name']}({pid}) respawned ({mode}) "
                      f"[-{RESPAWN_KILL_PENALTY} kills]")

    finally:
        async with _lock:
            clients.pop(pid, None)
            room = players.get(pid, {}).get("room")
            if room and pid in rooms.get(room, set()):
                lm = json.dumps({"type": "player_leave", "id": pid})
                for p2 in rooms.get(room, set()):
                    if p2 != pid:
                        w2 = clients.get(p2)
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
