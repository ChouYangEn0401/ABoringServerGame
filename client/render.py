"""client.render  --  All Pygame drawing code.

One public function: ``draw(screen, state, font, fsm)``.
Everything visual lives here so the game loop stays tiny.
"""
import math, random, time, pygame
from client.config import (
    WIDTH, HEIGHT, TILE, BOUNDARY, MSG_TTL,
    SHAKE_INTENSITY, RED_FLASH_DURATION, BLUE_FLASH_DURATION,
    COL, PICKUP_VIS,
    WEAPON_NAMES, WEAPON_COLOURS,
)

# ── helpers ──────────────────────────────────────────────────────
def _w2s(wx, wy, cx, cy):
    return int(WIDTH / 2 + (wx - cx) * TILE), int(HEIGHT / 2 + (wy - cy) * TILE)


def _draw_diamond(surface, colour, cx, cy, r):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    pygame.draw.polygon(surface, colour, pts)


def _draw_hp_bar(screen, sx, sy, ratio, bar_w):
    """Draw a tiny horizontal HP bar at *(sx, sy)* (top-left)."""
    h = 3
    pygame.draw.rect(screen, (60, 20, 20), (sx, sy, bar_w, h))
    if ratio > 0.5:
        c = (50, 200, 50)
    elif ratio > 0.25:
        c = (220, 180, 40)
    else:
        c = (220, 50, 50)
    pygame.draw.rect(screen, c, (sx, sy, int(bar_w * ratio), h))


# ── main draw ────────────────────────────────────────────────────
def draw(screen, state, font, fsm):
    me = state["peers"].get(state["my_id"], {"x": 0, "y": 0})
    cx, cy = me.get("x", 0), me.get("y", 0)

    # screen-shake offset
    sx_off = sy_off = 0
    if state.get("shake_t", 0) > 0:
        sx_off = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)
        sy_off = random.randint(-SHAKE_INTENSITY, SHAKE_INTENSITY)

    screen.fill(COL["bg"])

    # ── grid ─────────────────────────────────────────────────────
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

    # ── obstacles ────────────────────────────────────────────────
    for o in state.get("obstacles", []):
        ox, oy = _w2s(o["x"], o["y"], cx, cy)
        pygame.draw.rect(screen, COL["obs"],
                         (ox + sx_off, oy + sy_off, int(o["w"] * TILE), int(o["h"] * TILE)))

    # ── pickups ──────────────────────────────────────────────────
    _draw_pickups(screen, fsm, state, cx, cy, sx_off, sy_off)

    # ── enemies ──────────────────────────────────────────────────
    for e in state.get("enemies", []):
        ex, ey = _w2s(e["x"], e["y"], cx, cy)
        ex += sx_off; ey += sy_off
        is_big = e.get("tp") == "big"
        sz = 14 if is_big else 9
        col = COL["ebg"] if is_big else COL["esm"]
        pygame.draw.rect(screen, col, (ex - sz, ey - sz, sz * 2, sz * 2))
        ratio = e["hp"] / max(e.get("mhp", 2), 1)
        bw = sz * 2
        pygame.draw.rect(screen, (100, 30, 30), (ex - sz, ey - sz - 6, bw, 4))
        pygame.draw.rect(screen, (50, 200, 50), (ex - sz, ey - sz - 6, int(bw * ratio), 4))

    # ── bullets ──────────────────────────────────────────────────
    for b in state.get("bullets", []):
        bx, by = _w2s(b["x"], b["y"], cx, cy)
        col = COL["bul_p"] if b.get("ow") == "player" else COL["bul_e"]
        pygame.draw.circle(screen, col, (bx + sx_off, by + sy_off), 3)

    # ── players ──────────────────────────────────────────────────
    _draw_players(screen, fsm, state, cx, cy, sx_off, sy_off)

    # ══════════════════════════════════════════════════════════════
    #  HUD (not affected by shake)
    # ══════════════════════════════════════════════════════════════
    _draw_hud(screen, font, fsm, state, me)

    # ── overlays ─────────────────────────────────────────────────
    _draw_overlays(screen, font, fsm, state, me)


# ──────────────────────────────────────────────────────────────────
#  Sub-draw functions (keep draw() readable)
# ──────────────────────────────────────────────────────────────────
def _draw_pickups(screen, fsm, state, cx, cy, sx_off, sy_off):
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
        else:
            pygame.draw.circle(screen, vis["bg"], (px, py), 9)
            pygame.draw.circle(screen, vis["border"], (px, py), 9, 2)
            if tp in ("health", "double_heart", "triple_heart"):
                pygame.draw.line(screen, (255, 255, 255), (px - 4, py), (px + 4, py), 2)
                pygame.draw.line(screen, (255, 255, 255), (px, py - 4), (px, py + 4), 2)
        lbl = fsm.render(vis["label"], True, (255, 255, 255))
        screen.blit(lbl, (px - lbl.get_width() // 2, py + 11))


def _draw_players(screen, fsm, state, cx, cy, sx_off, sy_off):
    now_t = time.time()
    for pid, p in list(state["peers"].items()):
        sx, sy = _w2s(p["x"], p["y"], cx, cy)
        sx += sx_off; sy += sy_off

        if p.get("dead"):
            pygame.draw.line(screen, COL["dead"], (sx - 6, sy - 6), (sx + 6, sy + 6), 2)
            pygame.draw.line(screen, COL["dead"], (sx + 6, sy - 6), (sx - 6, sy + 6), 2)
            continue

        is_immortal = p.get("immortal", False)
        if is_immortal and int(now_t * 6.67) % 2 == 0:
            lbl = fsm.render(p.get("name", "") or pid, True, (220, 220, 220))
            screen.blit(lbl, (sx - lbl.get_width() // 2, sy - 30))
            continue

        col = COL["self"] if pid == state["my_id"] else COL["other"]

        # buff rings
        if p.get("shield"):
            pygame.draw.circle(screen, (100, 180, 255), (sx, sy), 18, 2)
        if p.get("boost"):
            pygame.draw.circle(screen, (255, 220, 50), (sx, sy), 16, 2)
        if p.get("muscle"):
            pygame.draw.circle(screen, (220, 80, 40), (sx, sy), 20, 2)
        if p.get("regen20") or p.get("regen30"):
            pulse = int(abs(math.sin(now_t * 4)) * 60) + 40
            pygame.draw.circle(screen, (50, pulse + 140, 50), (sx, sy), 22, 1)

        pygame.draw.rect(screen, col, (sx - 10, sy - 10, 20, 20))

        # facing arrow
        fdx = p.get("fdx", 1); fdy = p.get("fdy", 0)
        pygame.draw.line(screen, (255, 255, 255), (sx, sy),
                         (sx + int(fdx * 14), sy + int(fdy * 14)), 2)

        # health bar above head
        p_hp  = max(p.get("hp", 10), 0)
        p_mhp = max(p.get("max_hp", 10), 1)
        _draw_hp_bar(screen, sx - 12, sy - 20, min(p_hp / p_mhp, 1.0), 24)

        # name
        lbl = fsm.render(p.get("name", "") or pid, True, (220, 220, 220))
        screen.blit(lbl, (sx - lbl.get_width() // 2, sy - 30))


def _draw_hud(screen, font, fsm, state, me):
    cx, cy = me.get("x", 0), me.get("y", 0)

    # top-centre: level + kills + coords
    level = state.get("level", 1)
    kills = state.get("kills", 0)
    kn    = state.get("kills_needed", 6)
    coord = font.render(
        f"Lv.{level}  Kills: {kills}/{kn}  pos: ({cx:.1f}, {cy:.1f})",
        True, COL["txt"])
    screen.blit(coord, (WIDTH // 2 - coord.get_width() // 2, 8))

    # top-left: player count
    pc = fsm.render(f"Players: {len(state['peers'])}", True, COL["dim"])
    screen.blit(pc, (10, 10))

    # HP bar
    hp     = max(me.get("hp", 10), 0)
    max_hp = max(me.get("max_hp", 10), 1)
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
    w_label = WEAPON_NAMES.get(weapon, weapon)
    if weapon != "pistol":
        w_label += f" [{ammo}]"
    wt = fsm.render(w_label, True, WEAPON_COLOURS.get(weapon, (180, 180, 180)))
    screen.blit(wt, (10, 48))

    # buff / ability status lines
    buf_y = 66
    _STATUS = [
        ("shield",               "[S] Shield",             (100, 180, 255)),
        ("boost",                "[B] Boost",              (255, 220, 50)),
        ("muscle",               "[M] Muscle x2",          (220, 80, 40)),
        ("immortal",             "** IMMORTAL **",         (255, 255, 200)),
        ("regen20",              "[R] Regen 20%",          (80, 220, 80)),
        ("regen30",              "[R] Regen 30% (rooted)", (80, 255, 120)),
        ("ability_bullet_cancel","[BC] Bullet Cancel",     (180, 60, 220)),
        ("ability_double_kill",  "[x2] Double Kill",       (220, 180, 60)),
        ("ability_kill_heal",    "[KH] Kill Heals 2%",     (60, 220, 120)),
    ]
    for key, label, col in _STATUS:
        if me.get(key):
            screen.blit(fsm.render(label, True, col), (10, buf_y))
            buf_y += 16

    # atk speed (show multiplier)
    if me.get("ability_kill_atk_speed"):
        mul = me.get("atk_speed_mul", 1.0)
        screen.blit(fsm.render(f"[AS] Atk Spd x{mul:.2f}", True, (220, 120, 60)), (10, buf_y))
        buf_y += 16
    # free shots
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
    screen.blit(hdr, (WIDTH - hdr.get_width() - 10, ry)); ry += 20
    for nm, sc in scores[:8]:
        st = fsm.render(f"{nm}: {sc}", True, (220, 200, 100))
        screen.blit(st, (WIDTH - st.get_width() - 10, ry)); ry += 18

    # messages (fade)
    now = time.time()
    state["msgs"] = [(t, ts) for t, ts in state["msgs"] if now - ts < MSG_TTL]
    my = buf_y + 4
    for txt, ts in state["msgs"]:
        fade = max(0.2, 1.0 - (now - ts) / MSG_TTL)
        c = int(180 * fade)
        im = fsm.render(txt, True, (c, max(c, 60), c))
        screen.blit(im, (10, my)); my += 18


def _draw_overlays(screen, font, fsm, state, me):
    level = state.get("level", 1)

    # level clear
    if state.get("level_clear"):
        banner = font.render(f"LEVEL {level} CLEAR!", True, (80, 255, 80))
        screen.blit(banner, (WIDTH // 2 - banner.get_width() // 2, HEIGHT // 2 - 40))
        sub = fsm.render("Next level loading...", True, (180, 255, 180))
        screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2))

    # dead overlay
    if me.get("dead"):
        ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 150))
        screen.blit(ov, (0, 0))
        dt_txt = font.render("YOU DIED", True, (255, 80, 80))
        screen.blit(dt_txt, (WIDTH // 2 - dt_txt.get_width() // 2, HEIGHT // 2 - 30))
        r1 = fsm.render("[ R ]  Respawn at random position  (-5 kills)", True, (180, 220, 180))
        screen.blit(r1, (WIDTH // 2 - r1.get_width() // 2, HEIGHT // 2 + 10))
        r2 = fsm.render("[ T ]  Respawn at current position  (-5 kills)", True, (180, 180, 220))
        screen.blit(r2, (WIDTH // 2 - r2.get_width() // 2, HEIGHT // 2 + 35))

    # red flash
    if state.get("red_flash_t", 0) > 0:
        ratio = state["red_flash_t"] / RED_FLASH_DURATION
        alpha = int(100 * ratio)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 0, 0, alpha))
        bw = 6
        for rect in [(0, 0, WIDTH, bw), (0, HEIGHT - bw, WIDTH, bw),
                      (0, 0, bw, HEIGHT), (WIDTH - bw, 0, bw, HEIGHT)]:
            pygame.draw.rect(flash, (255, 30, 30, min(255, alpha + 80)), rect)
        screen.blit(flash, (0, 0))

    # blue flash
    if state.get("blue_flash_t", 0) > 0:
        ratio = state["blue_flash_t"] / BLUE_FLASH_DURATION
        alpha = int(80 * ratio)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((60, 120, 255, alpha))
        bw = 5
        for rect in [(0, 0, WIDTH, bw), (0, HEIGHT - bw, WIDTH, bw),
                      (0, 0, bw, HEIGHT), (WIDTH - bw, 0, bw, HEIGHT)]:
            pygame.draw.rect(flash, (60, 120, 255, min(255, alpha + 100)), rect)
        screen.blit(flash, (0, 0))
        sb = fsm.render("SHIELD BREAK!", True, (100, 180, 255))
        screen.blit(sb, (WIDTH // 2 - sb.get_width() // 2, HEIGHT // 2 + 60))

    # error
    if state.get("error"):
        et = fsm.render("NET ERR: " + state["error"], True, (255, 80, 80))
        screen.blit(et, (10, HEIGHT - 24))
