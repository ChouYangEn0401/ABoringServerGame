"""client.game  --  Menu screen and main game loop.

Public coroutines: ``run_menu``, ``run_game``.
"""
import asyncio, math, time, pygame

from client.config import (
    WIDTH, HEIGHT, SPEED, SEND_HZ, BOUNDARY,
    WEAPON_COOLDOWNS,
)
from client.render import draw


# ── Menu ─────────────────────────────────────────────────────────
async def run_menu(screen, font):
    """Show a simple single/multi menu.  Returns '1', '2', or None."""
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
                cur_weapon = me.get("weapon", "pistol")
                mul = me.get("atk_speed_mul", 1.0)
                shoot_cd = WEAPON_COOLDOWNS.get(cur_weapon, 0.35) / max(mul, 0.5)
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
