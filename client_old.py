"""client.py  --  Pygame client for Mini Multiplayer Bullet Game

Rendering for pickups uses coloured shapes + single-char labels so they
display correctly on every system (no emoji-font dependency).
"""
import argparse, asyncio, json, math, time, random, pygame, websockets

WIDTH, HEIGHT = 800, 600
TILE     = 8
SPEED    = 5.0
SEND_HZ  = 20
BOUNDARY = 50
MSG_TTL  = 5.0

# hit-feedback timers
SHAKE_DURATION     = 0.25
SHAKE_INTENSITY    = 8
RED_FLASH_DURATION = 0.35
BLUE_FLASH_DURATION = 0.30

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
    "txt":      (200, 200, 200),
    "dim":      (140, 140, 140),
}

# =====================================================================
# ── Pickup visual definitions (mirrors server PICKUP_DEFS) ──────
#   shape + colours so every pickup is clearly distinct on screen
# =====================================================================
PICKUP_VIS = {
    "health":        {"bg": (255, 80, 120),  "border": (200, 40, 80),   "label": "+",  "shape": "circle"},
    "double_heart":  {"bg": (255, 120, 160), "border": (200, 80, 120),  "label": "++", "shape": "circle"},
    "triple_heart":  {"bg": (255, 160, 200), "border": (220, 100, 140), "label": "3+", "shape": "circle"},
    "boost":         {"bg": (255, 220,  50), "border": (200, 170, 10),  "label": "B",  "shape": "diamond"},
    "shield":        {"bg": (100, 180, 255), "border": (40, 120, 220),  "label": "S",  "shape": "shield"},
    "muscle":        {"bg": (220, 80, 40),   "border": (180, 50, 20),   "label": "M",  "shape": "diamond"},
    "cross":         {"bg": (255, 255, 200), "border": (200, 200, 120), "label": "X",  "shape": "cross"},
    # weapon pickups
    "machine_gun":   {"bg": (200, 200, 60),  "border": (160, 160, 30),  "label": "MG", "shape": "rect"},
    "shotgun":       {"bg": (180, 100, 40),  "border": (140, 70, 20),   "label": "SG", "shape": "rect"},
    "rifle":         {"bg": (60, 180, 200),  "border": (30, 140, 160),  "label": "RF", "shape": "rect"},
    "bomb":          {"bg": (80, 80, 80),    "border": (200, 60, 60),   "label": "BM", "shape": "circle"},
    # ability pickups
    "ability_bullet_cancel":  {"bg": (180, 60, 220),  "border": (140, 30, 180),  "label": "BC", "shape": "diamond"},
    "ability_double_kill":    {"bg": (220, 180, 60),  "border": (180, 140, 30),  "label": "x2", "shape": "diamond"},
    "ability_kill_heal":      {"bg": (60, 220, 120),  "border": (30, 180, 80),   "label": "KH", "shape": "diamond"},
    "ability_kill_atk_speed": {"bg": (220, 120, 60),  "border": (180, 80, 30),   "label": "AS", "shape": "diamond"},
    "ability_extra_shots":    {"bg": (120, 60, 220),  "border": (80, 30, 180),   "label": "FS", "shape": "diamond"},
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
                        _EXTRA_KEYS = (
                            "muscle", "regen20", "regen30",
                            "revive_immortal",
                            "weapon", "ammo",
                            "ability_bullet_cancel", "ability_double_kill",
                            "ability_kill_heal", "ability_kill_atk_speed",
                            "atk_speed_mul", "free_shots",
                        )
                        for p in d.get("players", []):
                            pd = {
                                "x": float(p["x"]), "y": float(p["y"]),
                                "name": p.get("name", ""),
                                "hp": p.get("hp", 2),
                                "max_hp": p.get("max_hp", 4),
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
                        state["enemies"]      = d.get("enemies", [])
                        state["bullets"]      = d.get("bullets", [])
                        state["obstacles"]    = d.get("obstacles", [])
                        state["pickups"]      = d.get("pickups", [])
                        state["level"]        = d.get("level", 1)
                        state["kills"]        = d.get("kills", 0)
                        state["kills_needed"] = d.get("kills_needed", 6)
                        state["level_clear"]  = d.get("level_clear", False)

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
                            "hp": 2, "max_hp": 4, "score": 0,
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


def _msg(st, text):
    st["msgs"].append((text, time.time()))

# ── Drawing helpers ──────────────────────────────────────────────
def _w2s(wx, wy, cx, cy):
    return int(WIDTH / 2 + (wx - cx) * TILE), int(HEIGHT / 2 + (wy - cy) * TILE)


def _draw_diamond(surface, colour, cx, cy, r):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    pygame.draw.polygon(surface, colour, pts)

# ── Main draw ────────────────────────────────────────────────────
def draw(screen, state, font, fsm):
    me = state["peers"].get(state["my_id"], {"x": 0, "y": 0})
    cx, cy = me.get("x", 0), me.get("y", 0)

    # screen shake offset
    sx_off = sy_off = 0
    if state.get("shake_t", 0) > 0:
        sx_off = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)
        sy_off = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)

    screen.fill(COL["bg"])

    # grid
    for gx in range(int(-BOUNDARY), int(BOUNDARY) + 1, 5):
        sx, _ = _w2s(gx, 0, cx, cy)
        sx += sx_off
        if 0 <= sx <= WIDTH:
            pygame.draw.line(screen, COL["grid"], (sx, 0), (sx, HEIGHT))
    for gy in range(int(-BOUNDARY), int(BOUNDARY) + 1, 5):
        _, sy = _w2s(0, gy, cx, cy)
        sy += sy_off
        if 0 <= sy <= HEIGHT:
            pygame.draw.line(screen, COL["grid"], (0, sy), (WIDTH, sy))

    # boundary
    bx1, by1 = _w2s(-BOUNDARY, -BOUNDARY, cx, cy)
    bx2, by2 = _w2s(BOUNDARY, BOUNDARY, cx, cy)
    pygame.draw.rect(screen, COL["bound"],
                     (bx1 + sx_off, by1 + sy_off, bx2 - bx1, by2 - by1), 2)

    # obstacles
    for o in state.get("obstacles", []):
        ox, oy = _w2s(o["x"], o["y"], cx, cy)
        pygame.draw.rect(screen, COL["obs"],
                         (ox + sx_off, oy + sy_off, int(o["w"] * TILE), int(o["h"] * TILE)))

    # ── pickups (shaped icons, no emoji font needed) ─────────────
    for pk in state.get("pickups", []):
        px, py = _w2s(pk["x"], pk["y"], cx, cy)
        px += sx_off; py += sy_off
        tp = pk.get("tp", "health")
        vis = PICKUP_VIS.get(tp, PICKUP_VIS["health"])
        sh = vis.get("shape", "circle")
        if sh == "diamond":
            _draw_diamond(screen, vis["bg"], px, py, 10)
            _draw_diamond(screen, vis["border"], px, py, 10)
        elif sh == "shield":
            pygame.draw.circle(screen, vis["bg"], (px, py), 10)
            pygame.draw.circle(screen, vis["border"], (px, py), 10, 2)
            pygame.draw.circle(screen, (255, 255, 255), (px, py), 5, 1)
        elif sh == "cross":
            pygame.draw.circle(screen, vis["bg"], (px, py), 10)
            pygame.draw.circle(screen, vis["border"], (px, py), 10, 2)
            pygame.draw.line(screen, vis["border"], (px - 6, py), (px + 6, py), 3)
            pygame.draw.line(screen, vis["border"], (px, py - 6), (px, py + 6), 3)
        elif sh == "rect":
            pygame.draw.rect(screen, vis["bg"], (px - 9, py - 6, 18, 12))
            pygame.draw.rect(screen, vis["border"], (px - 9, py - 6, 18, 12), 2)
        else:  # circle (default)
            pygame.draw.circle(screen, vis["bg"], (px, py), 9)
            pygame.draw.circle(screen, vis["border"], (px, py), 9, 2)
            # draw cross for health types
            if tp in ("health", "double_heart", "triple_heart"):
                pygame.draw.line(screen, (255, 255, 255), (px - 4, py), (px + 4, py), 2)
                pygame.draw.line(screen, (255, 255, 255), (px, py - 4), (px, py + 4), 2)
        lbl = fsm.render(vis["label"], True, (255, 255, 255))
        screen.blit(lbl, (px - lbl.get_width() // 2, py + 11))

    # enemies
    for e in state.get("enemies", []):
        ex, ey = _w2s(e["x"], e["y"], cx, cy)
        ex += sx_off; ey += sy_off
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
        pygame.draw.circle(screen, col, (bx + sx_off, by + sy_off), 3)

    # players
    now_t = time.time()
    for pid, p in list(state["peers"].items()):
        sx, sy = _w2s(p["x"], p["y"], cx, cy)
        sx += sx_off; sy += sy_off

        if p.get("dead"):
            pygame.draw.line(screen, COL["dead"], (sx - 6, sy - 6), (sx + 6, sy + 6), 2)
            pygame.draw.line(screen, COL["dead"], (sx + 6, sy - 6), (sx - 6, sy + 6), 2)
            continue

        # immortal blink (~6.67 Hz)
        is_immortal = p.get("immortal", False)
        if is_immortal and int(now_t * 6.67) % 2 == 0:
            lbl = fsm.render(p.get("name", "") or pid, True, (220, 220, 220))
            screen.blit(lbl, (sx - lbl.get_width() // 2, sy - 28))
            continue

        col = COL["self"] if pid == state["my_id"] else COL["other"]

        # shield ring
        if p.get("shield"):
            pygame.draw.circle(screen, (100, 180, 255), (sx, sy), 18, 2)
        # boost ring
        if p.get("boost"):
            pygame.draw.circle(screen, (255, 220, 50), (sx, sy), 16, 2)
        # muscle glow
        if p.get("muscle"):
            pygame.draw.circle(screen, (220, 80, 40), (sx, sy), 20, 2)
        # regen aura (green pulse)
        if p.get("regen20") or p.get("regen30"):
            pulse = int(abs(math.sin(now_t * 4)) * 60) + 40
            pygame.draw.circle(screen, (50, pulse + 140, 50), (sx, sy), 22, 1)

        pygame.draw.rect(screen, col, (sx - 10, sy - 10, 20, 20))

        # facing arrow
        fdx = p.get("fdx", 1); fdy = p.get("fdy", 0)
        pygame.draw.line(screen, (255, 255, 255), (sx, sy),
                         (sx + int(fdx * 14), sy + int(fdy * 14)), 2)

        # health bar above player (like enemies)
        p_hp = max(p.get("hp", 2), 0)
        p_mhp = max(p.get("max_hp", 4), 1)
        p_hr = min(p_hp / p_mhp, 1.0)
        hb_w = 24
        pygame.draw.rect(screen, (60, 20, 20), (sx - hb_w // 2, sy - 20, hb_w, 3))
        hc = (50, 200, 50) if p_hr > 0.5 else (220, 180, 40) if p_hr > 0.25 else (220, 50, 50)
        pygame.draw.rect(screen, hc, (sx - hb_w // 2, sy - 20, int(hb_w * p_hr), 3))

        # name
        lbl = fsm.render(p.get("name", "") or pid, True, (220, 220, 220))
        screen.blit(lbl, (sx - lbl.get_width() // 2, sy - 30))

    # ══════════════════════════════════════════════════════════════
    #  HUD (not affected by shake)
    # ══════════════════════════════════════════════════════════════

    # top-center: level + kills + coords
    level = state.get("level", 1)
    kills = state.get("kills", 0)
    kn    = state.get("kills_needed", 6)
    coord = font.render(
        f"Lv.{level}  Kills: {kills}/{kn}  pos: ({cx:.1f}, {cy:.1f})",
        True, COL["txt"])
    screen.blit(coord, (WIDTH // 2 - coord.get_width() // 2, 8))

    # top-left: player count + HP bar + weapon + buffs + abilities
    pc = fsm.render(f"Players: {len(state['peers'])}", True, COL["dim"])
    screen.blit(pc, (10, 10))

    hp     = max(me.get("hp", 2), 0)
    max_hp = max(me.get("max_hp", 4), 1)
    hp_ratio = min(hp / max_hp, 1.0)
    bar_w, bar_h = 140, 14
    bar_x, bar_y = 10, 30
    pygame.draw.rect(screen, (60, 20, 20), (bar_x, bar_y, bar_w, bar_h))
    if hp_ratio > 0.6:
        bar_col = (50, 200, 50)
    elif hp_ratio > 0.3:
        bar_col = (220, 180, 40)
    else:
        bar_col = (220, 50, 50)
    pygame.draw.rect(screen, bar_col, (bar_x, bar_y, int(bar_w * hp_ratio), bar_h))
    pygame.draw.rect(screen, (180, 180, 180), (bar_x, bar_y, bar_w, bar_h), 1)
    hp_txt = fsm.render(f"{hp}/{max_hp}", True, (255, 255, 255))
    screen.blit(hp_txt, (bar_x + bar_w // 2 - hp_txt.get_width() // 2,
                         bar_y + bar_h // 2 - hp_txt.get_height() // 2))

    # weapon + ammo
    weapon = me.get("weapon", "pistol")
    ammo   = me.get("ammo", 0)
    w_names = {"pistol": "Pistol", "machine_gun": "Machine Gun",
               "shotgun": "Shotgun", "rifle": "Rifle", "bomb": "Bomb"}
    w_cols  = {"pistol": (180, 180, 180), "machine_gun": (200, 200, 60),
               "shotgun": (180, 100, 40), "rifle": (60, 180, 200), "bomb": (200, 60, 60)}
    w_label = w_names.get(weapon, weapon)
    if weapon != "pistol":
        w_label += f" [{ammo}]"
    wt = fsm.render(w_label, True, w_cols.get(weapon, (180, 180, 180)))
    screen.blit(wt, (10, 48))

    buf_y = 66
    if me.get("shield"):
        screen.blit(fsm.render("[S] Shield", True, (100, 180, 255)), (10, buf_y))
        buf_y += 16
    if me.get("boost"):
        screen.blit(fsm.render("[B] Boost", True, (255, 220, 50)), (10, buf_y))
        buf_y += 16
    if me.get("muscle"):
        screen.blit(fsm.render("[M] Muscle x2", True, (220, 80, 40)), (10, buf_y))
        buf_y += 16
    if me.get("immortal"):
        screen.blit(fsm.render("** IMMORTAL **", True, (255, 255, 200)), (10, buf_y))
        buf_y += 16
    if me.get("regen20"):
        screen.blit(fsm.render("[R] Regen 20%", True, (80, 220, 80)), (10, buf_y))
        buf_y += 16
    if me.get("regen30"):
        screen.blit(fsm.render("[R] Regen 30% (rooted)", True, (80, 255, 120)), (10, buf_y))
        buf_y += 16

    # ── ability icons ──
    if me.get("ability_bullet_cancel"):
        screen.blit(fsm.render("[BC] Bullet Cancel", True, (180, 60, 220)), (10, buf_y))
        buf_y += 16
    if me.get("ability_double_kill"):
        screen.blit(fsm.render("[x2] Double Kill", True, (220, 180, 60)), (10, buf_y))
        buf_y += 16
    if me.get("ability_kill_heal"):
        screen.blit(fsm.render("[KH] Kill Heals 2%", True, (60, 220, 120)), (10, buf_y))
        buf_y += 16
    if me.get("ability_kill_atk_speed"):
        mul = me.get("atk_speed_mul", 1.0)
        screen.blit(fsm.render(f"[AS] Atk Spd x{mul:.2f}", True, (220, 120, 60)), (10, buf_y))
        buf_y += 16
    fs = me.get("free_shots", 0)
    if fs > 0:
        screen.blit(fsm.render(f"[FS] Free shots: {fs}", True, (120, 60, 220)), (10, buf_y))
        buf_y += 16

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
    my = buf_y + 4
    for txt, ts in state["msgs"]:
        fade = max(0.2, 1.0 - (now - ts) / MSG_TTL)
        c = int(180 * fade)
        im = fsm.render(txt, True, (c, max(c, 60), c))
        screen.blit(im, (10, my))
        my += 18

    # level clear banner
    if state.get("level_clear"):
        banner = font.render(f"LEVEL {level} CLEAR!", True, (80, 255, 80))
        screen.blit(banner, (WIDTH // 2 - banner.get_width() // 2, HEIGHT // 2 - 40))
        sub = fsm.render("Next level loading...", True, (180, 255, 180))
        screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2))

    # dead overlay -- manual respawn
    if me.get("dead"):
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 150))
        screen.blit(ov, (0, 0))
        dt_txt = font.render("YOU DIED", True, (255, 80, 80))
        screen.blit(dt_txt, (WIDTH // 2 - dt_txt.get_width() // 2, HEIGHT // 2 - 30))
        r1 = fsm.render("[ R ]  Respawn at random position", True, (180, 220, 180))
        screen.blit(r1, (WIDTH // 2 - r1.get_width() // 2, HEIGHT // 2 + 10))
        r2 = fsm.render("[ T ]  Respawn at current position", True, (180, 180, 220))
        screen.blit(r2, (WIDTH // 2 - r2.get_width() // 2, HEIGHT // 2 + 35))

    # ── red flash overlay (damage taken) ─────────────────────────
    if state.get("red_flash_t", 0) > 0:
        ratio = state["red_flash_t"] / RED_FLASH_DURATION
        alpha = int(100 * ratio)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 0, 0, alpha))
        bw = 6
        pygame.draw.rect(flash, (255, 30, 30, min(255, alpha + 80)),
                         (0, 0, WIDTH, bw))
        pygame.draw.rect(flash, (255, 30, 30, min(255, alpha + 80)),
                         (0, HEIGHT - bw, WIDTH, bw))
        pygame.draw.rect(flash, (255, 30, 30, min(255, alpha + 80)),
                         (0, 0, bw, HEIGHT))
        pygame.draw.rect(flash, (255, 30, 30, min(255, alpha + 80)),
                         (WIDTH - bw, 0, bw, HEIGHT))
        screen.blit(flash, (0, 0))

    # ── blue flash overlay (shield absorbed) ─────────────────────
    if state.get("blue_flash_t", 0) > 0:
        ratio = state["blue_flash_t"] / BLUE_FLASH_DURATION
        alpha = int(80 * ratio)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((60, 120, 255, alpha))
        bw = 5
        pygame.draw.rect(flash, (60, 120, 255, min(255, alpha + 100)),
                         (0, 0, WIDTH, bw))
        pygame.draw.rect(flash, (60, 120, 255, min(255, alpha + 100)),
                         (0, HEIGHT - bw, WIDTH, bw))
        pygame.draw.rect(flash, (60, 120, 255, min(255, alpha + 100)),
                         (0, 0, bw, HEIGHT))
        pygame.draw.rect(flash, (60, 120, 255, min(255, alpha + 100)),
                         (WIDTH - bw, 0, bw, HEIGHT))
        screen.blit(flash, (0, 0))
        # "SHIELD BREAK" text
        sb = fsm.render("SHIELD BREAK!", True, (100, 180, 255))
        screen.blit(sb, (WIDTH // 2 - sb.get_width() // 2, HEIGHT // 2 + 60))

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
        await asyncio.sleep(0)

        now = time.perf_counter()
        dt  = min(now - prev, 0.1)
        prev = now
        shoot_cd = max(0, shoot_cd - dt)

        # tick effect timers
        for key in ("shake_t", "red_flash_t", "blue_flash_t"):
            if state.get(key, 0) > 0:
                state[key] = max(0, state[key] - dt)

        # events
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return
                my_id = state["my_id"]
                me = state["peers"].get(my_id) or state["peers"].get("local")
                if me and me.get("dead"):
                    if ev.key == pygame.K_r and mp:
                        try:
                            out_q.put_nowait({"type": "respawn", "mode": "random"})
                        except asyncio.QueueFull:
                            pass
                    elif ev.key == pygame.K_t and mp:
                        try:
                            out_q.put_nowait({"type": "respawn", "mode": "here"})
                        except asyncio.QueueFull:
                            pass

        my_id   = state["my_id"]
        me      = state["peers"].get(my_id) or state["peers"].get("local")
        dead    = me.get("dead", False) if me else False
        immortal = me.get("immortal", False) if me else False
        boosted = me.get("boost", False) if me else False

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
            spd = SPEED * (1.8 if boosted else 1.0)
            me["x"] = max(-BOUNDARY, min(BOUNDARY, me["x"] + dx * spd * dt))
            me["y"] = max(-BOUNDARY, min(BOUNDARY, me["y"] + dy * spd * dt))
            me["fdx"] = face[0]
            me["fdy"] = face[1]

            # shoot -- blocked during immortality and regen30 (rooted)
            rooted = me.get("regen30", False)
            if keys[pygame.K_SPACE] and mp and shoot_cd <= 0 and not immortal and not rooted:
                # weapon-aware cooldown
                _WEAPON_CD = {"pistol": 0.15, "machine_gun": 0.05,
                              "shotgun": 0.8, "rifle": 0.4, "bomb": 1.2}
                cur_weapon = me.get("weapon", "pistol")
                mul = me.get("atk_speed_mul", 1.0)
                shoot_cd = _WEAPON_CD.get(cur_weapon, 0.15) / max(mul, 0.5)
                try:
                    out_q.put_nowait({"type": "shoot", "fdx": face[0], "fdy": face[1]})
                except asyncio.QueueFull:
                    pass

        # send position
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
        "peers": {"local": {
            "x": 0.0, "y": 0.0, "name": args.name,
            "hp": 2, "max_hp": 4, "score": 0,
            "fdx": 1, "fdy": 0,
            "dead": False, "immortal": True,   # starts immortal
            "shield": False, "boost": False,
        }},
        "my_id": "local", "room": None, "msgs": [], "error": None,
        "enemies": [], "bullets": [], "obstacles": [], "pickups": [],
        "level": 1, "kills": 0, "kills_needed": 6, "level_clear": False,
        "shake_t": 0.0, "red_flash_t": 0.0, "blue_flash_t": 0.0,
    }
    out_q = asyncio.Queue(maxsize=64)

    choice = "2" if args.multiplayer else await run_menu(screen, font)
    if choice is None:
        pygame.quit()
        return

    mp = (choice == "2")
    net = embedded = None

    if mp:
        pygame.display.set_caption(f"[Room: {args.room}] {args.name}")
        net = asyncio.create_task(
            net_task(f"ws://{args.host}:{args.port}", args.name, args.room, out_q, state))
    else:
        pygame.display.set_caption(f"Single Player -- {args.name}")
        import server as srv
        embedded = asyncio.create_task(srv.run_embedded())
        await asyncio.sleep(0.3)
        net = asyncio.create_task(
            net_task(f"ws://localhost:{srv.EMBEDDED_PORT}", args.name, "solo", out_q, state))
        mp = True

    await run_game(screen, font, fsm, state, out_q, mp)

    if net:
        net.cancel()
    if embedded:
        embedded.cancel()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
