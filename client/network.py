"""client.network  --  WebSocket send / receive task.

Translates JSON messages from the server into the shared *state* dict
that the renderer reads every frame.
"""
import asyncio, json, time, websockets
from client.config import SHAKE_DURATION, RED_FLASH_DURATION, BLUE_FLASH_DURATION

# Extra per-player keys the server sends beyond the base set.
_EXTRA_KEYS = (
    "muscle", "regen20", "regen30", "revive_immortal",
    "weapon", "ammo",
    "ability_bullet_cancel", "ability_double_kill",
    "ability_kill_heal", "ability_kill_atk_speed",
    "atk_speed_mul", "free_shots",
)


def _msg(st, text):
    st["msgs"].append((text, time.time()))


async def net_task(uri, name, room, out_q, state):
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "join", "room": room, "name": name}))

            async def _tx():
                while True:
                    msg = await out_q.get()
                    try:
                        await ws.send(json.dumps(msg))
                    except Exception:
                        pass

            async def _rx():
                async for raw in ws:
                    try:
                        d = json.loads(raw)
                    except Exception:
                        continue
                    t = d.get("type")

                    if t == "welcome":
                        sid = d["id"]
                        if state["my_id"] == "local" and "local" in state["peers"]:
                            state["peers"][sid] = state["peers"].pop("local")
                        state["my_id"] = sid

                    elif t == "state":
                        my = state["my_id"]
                        inc = {}
                        for p in d.get("players", []):
                            pd = {
                                "x": float(p["x"]), "y": float(p["y"]),
                                "name": p.get("name", ""),
                                "hp": p.get("hp", 10),
                                "max_hp": p.get("max_hp", 10),
                                "score": p.get("score", 0),
                                "fdx": p.get("fdx", 1), "fdy": p.get("fdy", 0),
                                "dead": p.get("dead", False),
                                "immortal": p.get("immortal", False),
                                "shield": p.get("shield", False),
                                "boost": p.get("boost", False),
                            }
                            for ek in _EXTRA_KEYS:
                                if ek in p:
                                    pd[ek] = p[ek]
                            inc[p["id"]] = pd
                        for pid, pd in inc.items():
                            if pid == my:
                                me = state["peers"].setdefault(my, {})
                                for k in ("name", "hp", "max_hp", "score",
                                          "dead", "immortal", "shield", "boost",
                                          *_EXTRA_KEYS):
                                    if k in pd:
                                        me[k] = pd[k]
                                me["x"] = me.get("x", 0.0) * 0.75 + pd["x"] * 0.25
                                me["y"] = me.get("y", 0.0) * 0.75 + pd["y"] * 0.25
                            else:
                                state["peers"][pid] = pd
                        for pid in list(state["peers"]):
                            if pid not in inc and pid != "local":
                                state["peers"].pop(pid)
                        state["enemies"]     = d.get("enemies", [])
                        state["bullets"]     = d.get("bullets", [])
                        state["obstacles"]   = d.get("obstacles", [])
                        state["pickups"]     = d.get("pickups", [])
                        state["level"]       = d.get("level", 1)
                        state["kills"]       = d.get("kills", 0)
                        state["kills_needed"]= d.get("kills_needed", 6)
                        state["level_clear"] = d.get("level_clear", False)

                    elif t == "joined":
                        state["room"] = d.get("room")

                    elif t == "hit":
                        absorbed = d.get("absorbed", False)
                        state["shake_t"] = SHAKE_DURATION
                        if absorbed:
                            state["blue_flash_t"] = BLUE_FLASH_DURATION
                        else:
                            state["red_flash_t"] = RED_FLASH_DURATION

                    elif t == "player_join":
                        pid = d.get("id"); pn = d.get("name", "")
                        state["peers"].setdefault(pid, {
                            "x": 0, "y": 0, "name": pn,
                            "hp": 10, "max_hp": 10, "score": 0,
                            "dead": False, "immortal": False,
                            "shield": False, "boost": False})
                        _msg(state, f"+ {pn} joined")

                    elif t == "player_leave":
                        pid = d.get("id")
                        who = state["peers"].get(pid, {}).get("name", pid)
                        state["peers"].pop(pid, None)
                        _msg(state, f"- {who} left")

            await asyncio.gather(_tx(), _rx())
    except Exception as e:
        state["error"] = str(e)
