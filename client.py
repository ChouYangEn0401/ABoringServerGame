"""client.py ── Pygame client for Mini Multiplayer Bullet Game"""
import argparse, asyncio, json, math, time, pygame, websockets

WIDTH, HEIGHT = 800, 600
TILE     = 8        # px per world unit
SPEED    = 5.0      # world units / sec
SEND_HZ  = 20
BOUNDARY = 50
MSG_TTL  = 5.0      # seconds before messages fade

COL = {
    "bg":       (20, 20, 30),
    "grid":     (30, 30, 42),
    "bound":    (120, 60, 60),
    "self":     (80, 160, 255),
    "other":    (200, 120, 120),
    "dead":     (80, 80, 80),
    "esm":      (50, 200, 50),
    "ebg":      (255, 150, 50),
    "bul_p":    (255, 255, 100),
    "bul_e":    (255, 100, 100),
    "obs":      (70, 70, 90),
    "pickup":   (255, 80, 120),
    "txt":      (200, 200, 200),
    "dim":      (140, 140, 140),
}

# ── Network ──────────────────────────────────────────────────────
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
                            inc[p["id"]] = {
                                "x": float(p["x"]), "y": float(p["y"]),
                                "name": p.get("name", ""),
                                "hp": p.get("hp", 2), "score": p.get("score", 0),
                                "fdx": p.get("fdx", 1), "fdy": p.get("fdy", 0),
                                "dead": p.get("dead", False),
                            }
                        for pid, pd in inc.items():
                            if pid == my:
                                me = state["peers"].setdefault(my, {})
                                me["name"]  = pd["name"]
                                me["hp"]    = pd["hp"]
                                me["score"] = pd["score"]
                                me["dead"]  = pd["dead"]
                                # gentle snap to server pos (avoids jitter)
                                me["x"] = me.get("x", 0.0) * 0.75 + pd["x"] * 0.25
                                me["y"] = me.get("y", 0.0) * 0.75 + pd["y"] * 0.25
                            else:
                                state["peers"][pid] = pd
                        for pid in list(state["peers"]):
                            if pid not in inc and pid != "local":
                                state["peers"].pop(pid)
                        state["enemies"]   = d.get("enemies", [])
                        state["bullets"]   = d.get("bullets", [])
                        state["obstacles"] = d.get("obstacles", [])
                        state["pickups"]   = d.get("pickups", [])

                    elif t == "joined":
                        state["room"] = d.get("room")

                    elif t == "player_join":
                        pid = d.get("id"); pn = d.get("name", "")
                        state["peers"].setdefault(pid, {"x": 0, "y": 0, "name": pn,
                                                        "hp": 2, "score": 0, "dead": False})
                        _msg(state, f"+ {pn} joined")

                    elif t == "player_leave":
                        pid = d.get("id")
                        who = state["peers"].get(pid, {}).get("name", pid)
                        state["peers"].pop(pid, None)
                        _msg(state, f"- {who} left")

            await asyncio.gather(_tx(), _rx())
    except Exception as e:
        state["error"] = str(e)


def _msg(st, text):
    st["msgs"].append((text, time.time()))

# ── Drawing ──────────────────────────────────────────────────────
def _w2s(wx, wy, cx, cy):
    return int(WIDTH / 2 + (wx - cx) * TILE), int(HEIGHT / 2 + (wy - cy) * TILE)


def draw(screen, state, font, fsm):
    me = state["peers"].get(state["my_id"], {"x": 0, "y": 0})
    cx, cy = me.get("x", 0), me.get("y", 0)

    screen.fill(COL["bg"])

    # grid
    for gx in range(int(-BOUNDARY), int(BOUNDARY) + 1, 5):
        sx, _ = _w2s(gx, 0, cx, cy)
        if 0 <= sx <= WIDTH:
            pygame.draw.line(screen, COL["grid"], (sx, 0), (sx, HEIGHT))
    for gy in range(int(-BOUNDARY), int(BOUNDARY) + 1, 5):
        _, sy = _w2s(0, gy, cx, cy)
        if 0 <= sy <= HEIGHT:
            pygame.draw.line(screen, COL["grid"], (0, sy), (WIDTH, sy))

    # boundary
    bx1, by1 = _w2s(-BOUNDARY, -BOUNDARY, cx, cy)
    bx2, by2 = _w2s(BOUNDARY, BOUNDARY, cx, cy)
    pygame.draw.rect(screen, COL["bound"], (bx1, by1, bx2 - bx1, by2 - by1), 2)

    # obstacles
    for o in state.get("obstacles", []):
        ox, oy = _w2s(o["x"], o["y"], cx, cy)
        pygame.draw.rect(screen, COL["obs"], (ox, oy, int(o["w"] * TILE), int(o["h"] * TILE)))

    # pickups
    for pk in state.get("pickups", []):
        px, py = _w2s(pk["x"], pk["y"], cx, cy)
        pygame.draw.circle(screen, COL["pickup"], (px, py), 6)

    # enemies
    for e in state.get("enemies", []):
        ex, ey = _w2s(e["x"], e["y"], cx, cy)
        is_big = e.get("tp") == "big"
        sz = 14 if is_big else 9
        col = COL["ebg"] if is_big else COL["esm"]
        pygame.draw.rect(screen, col, (ex - sz, ey - sz, sz * 2, sz * 2))
        bw = sz * 2
        ratio = e["hp"] / max(e.get("mhp", 2), 1)
        pygame.draw.rect(screen, (100, 30, 30), (ex - sz, ey - sz - 6, bw, 4))
        pygame.draw.rect(screen, (50, 200, 50), (ex - sz, ey - sz - 6, int(bw * ratio), 4))

    # bullets
    for b in state.get("bullets", []):
        bx, by = _w2s(b["x"], b["y"], cx, cy)
        col = COL["bul_p"] if b.get("ow") == "player" else COL["bul_e"]
        pygame.draw.circle(screen, col, (bx, by), 3)

    # players
    for pid, p in list(state["peers"].items()):
        sx, sy = _w2s(p["x"], p["y"], cx, cy)
        if p.get("dead"):
            col = COL["dead"]
        elif pid == state["my_id"]:
            col = COL["self"]
        else:
            col = COL["other"]
        pygame.draw.rect(screen, col, (sx - 10, sy - 10, 20, 20))
        # facing arrow
        fdx = p.get("fdx", 1); fdy = p.get("fdy", 0)
        pygame.draw.line(screen, (255, 255, 255), (sx, sy),
                         (sx + int(fdx * 14), sy + int(fdy * 14)), 2)
        # name label
        lbl = fsm.render(p.get("name", "") or pid, True, (220, 220, 220))
        screen.blit(lbl, (sx - lbl.get_width() // 2, sy - 28))

    # ── HUD ──

    # top-center: coords
    coord = font.render(f"pos: ({cx:.1f}, {cy:.1f})", True, COL["txt"])
    screen.blit(coord, (WIDTH // 2 - coord.get_width() // 2, 8))

    # top-left: player count + HP
    pc = fsm.render(f"Players: {len(state['peers'])}", True, COL["dim"])
    screen.blit(pc, (10, 10))
    hp = max(me.get("hp", 2), 0)
    mx = 2  # max hp
    hp_str = "HP: " + ("@ " * hp) + ("_ " * (mx - hp))
    ht = fsm.render(hp_str, True, (255, 100, 100))
    screen.blit(ht, (10, 30))

    # top-right: score ranking
    scores = sorted([(p.get("name", pid), p.get("score", 0))
                     for pid, p in state["peers"].items()],
                    key=lambda x: -x[1])
    ry = 10
    hdr = fsm.render("-- Score --", True, COL["dim"])
    screen.blit(hdr, (WIDTH - hdr.get_width() - 10, ry))
    ry += 20
    for nm, sc in scores[:8]:
        st = fsm.render(f"{nm}: {sc}", True, (220, 200, 100))
        screen.blit(st, (WIDTH - st.get_width() - 10, ry))
        ry += 18

    # messages (fade)
    now = time.time()
    state["msgs"] = [(t, ts) for t, ts in state["msgs"] if now - ts < MSG_TTL]
    my = 52
    for txt, ts in state["msgs"]:
        fade = max(0.2, 1.0 - (now - ts) / MSG_TTL)
        c = int(180 * fade)
        im = fsm.render(txt, True, (c, max(c, 60), c))
        screen.blit(im, (10, my))
        my += 18

    # dead overlay
    if me.get("dead"):
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 120))
        screen.blit(ov, (0, 0))
        dt_txt = font.render("DEAD -- respawning...", True, (255, 80, 80))
        screen.blit(dt_txt, (WIDTH // 2 - dt_txt.get_width() // 2, HEIGHT // 2))

    # error
    if state.get("error"):
        et = fsm.render("NET ERR: " + state["error"], True, (255, 80, 80))
        screen.blit(et, (10, HEIGHT - 24))


# ── Menu ─────────────────────────────────────────────────────────
async def run_menu(screen, font):
    while True:
        await asyncio.sleep(0)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_1:
                    return "1"
                if ev.key == pygame.K_2:
                    return "2"
        screen.fill((18, 18, 24))
        items = [
            ("Mini Multiplayer Bullet Game", (220, 220, 220), -80),
            ("[ 1 ]  Single Player",          (180, 220, 180), -20),
            ("[ 2 ]  Multiplayer  (server)",   (180, 180, 220),  20),
            ("Press 1 or 2",                   (120, 120, 120),  80),
        ]
        for txt, col, yoff in items:
            s = font.render(txt, True, col)
            screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 2 + yoff))
        pygame.display.flip()
        await asyncio.sleep(1 / 30)


# ── Game loop ────────────────────────────────────────────────────
async def run_game(screen, font, fsm, state, out_q, mp):
    send_iv  = 1.0 / SEND_HZ
    send_acc = 0.0
    shoot_cd = 0.0
    prev     = time.perf_counter()
    face     = [1.0, 0.0]

    while True:
        await asyncio.sleep(0)               # yield to network task every frame!

        now = time.perf_counter()
        dt  = min(now - prev, 0.1)
        prev = now
        shoot_cd = max(0, shoot_cd - dt)

        # events
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return

        my_id = state["my_id"]
        me = state["peers"].get(my_id) or state["peers"].get("local")
        dead = me.get("dead", False) if me else False

        # movement
        dx = dy = 0.0
        if not dead and me:
            keys = pygame.key.get_pressed()
            if keys[pygame.K_w]: dy -= 1
            if keys[pygame.K_s]: dy += 1
            if keys[pygame.K_a]: dx -= 1
            if keys[pygame.K_d]: dx += 1
            if dx and dy:
                f = 1.0 / math.sqrt(2)
                dx *= f; dy *= f
            if dx or dy:
                ln = math.hypot(dx, dy)
                face = [dx / ln, dy / ln]
            me["x"] = max(-BOUNDARY, min(BOUNDARY, me["x"] + dx * SPEED * dt))
            me["y"] = max(-BOUNDARY, min(BOUNDARY, me["y"] + dy * SPEED * dt))
            me["fdx"] = face[0]
            me["fdy"] = face[1]

            # shoot (hold Space)
            if keys[pygame.K_SPACE] and mp and shoot_cd <= 0:
                shoot_cd = 0.15
                try:
                    out_q.put_nowait({"type": "shoot", "fdx": face[0], "fdy": face[1]})
                except asyncio.QueueFull:
                    pass

        # send position to server
        if mp and me and not dead:
            send_acc += dt
            if send_acc >= send_iv:
                send_acc = 0.0
                try:
                    out_q.put_nowait({
                        "type": "pos",
                        "x": round(me["x"], 3),
                        "y": round(me["y"], 3),
                        "fdx": face[0], "fdy": face[1],
                    })
                except asyncio.QueueFull:
                    pass

        draw(screen, state, font, fsm)
        pygame.display.flip()

        elapsed = time.perf_counter() - now
        await asyncio.sleep(max(0.0, 1 / 60 - elapsed))


# ── Entry ────────────────────────────────────────────────────────
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Player")
    ap.add_argument("--room", default="room1")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--multiplayer", action="store_true")
    args = ap.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(f"[Room: {args.room}] {args.name}")
    font = pygame.font.SysFont(None, 24)
    fsm  = pygame.font.SysFont(None, 20)

    state = {
        "peers": {"local": {"x": 0.0, "y": 0.0, "name": args.name,
                             "hp": 2, "score": 0, "fdx": 1, "fdy": 0, "dead": False}},
        "my_id": "local", "room": None, "msgs": [], "error": None,
        "enemies": [], "bullets": [], "obstacles": [], "pickups": [],
    }
    out_q = asyncio.Queue(maxsize=64)

    choice = "2" if args.multiplayer else await run_menu(screen, font)
    if choice is None:
        pygame.quit()
        return

    mp = (choice == "2")
    net = embedded = None

    if mp:
        # multiplayer — connect to external server
        pygame.display.set_caption(f"[Room: {args.room}] {args.name}")
        net = asyncio.create_task(
            net_task(f"ws://{args.host}:{args.port}", args.name, args.room, out_q, state))
    else:
        # single player — start embedded server then connect
        pygame.display.set_caption(f"Single Player -- {args.name}")
        import server as srv
        embedded = asyncio.create_task(srv.run_embedded())
        await asyncio.sleep(0.3)
        net = asyncio.create_task(
            net_task(f"ws://localhost:{srv.EMBEDDED_PORT}", args.name, "solo", out_q, state))
        mp = True  # from here on everything works the same

    await run_game(screen, font, fsm, state, out_q, mp)

    if net:
        net.cancel()
    if embedded:
        embedded.cancel()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
