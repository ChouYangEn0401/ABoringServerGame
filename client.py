import argparse
import asyncio
import json
import time
import pygame
import websockets

WIDTH, HEIGHT = 800, 600
TILE    = 20    # pixels per world unit
SPEED   = 5.0   # world units / sec
SEND_HZ = 20    # network move sends per second

# ──────────────────────────── Network ────────────────────────────

async def net_task(uri, name, room, out_q, state):
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({'type': 'join', 'room': room, 'name': name}))

            async def _send():
                while True:
                    msg = await out_q.get()
                    try:
                        await ws.send(json.dumps(msg))
                    except Exception:
                        pass

            async def _recv():
                async for raw in ws:
                    try:
                        d = json.loads(raw)
                    except Exception:
                        continue
                    t = d.get('type')

                    if t == 'welcome':
                        sid = d['id']
                        # rename 'local' placeholder to server-assigned id
                        if state['my_id'] == 'local' and 'local' in state['peers']:
                            state['peers'][sid] = state['peers'].pop('local')
                        state['my_id'] = sid
                        print(f"[client] connected as id={sid}")

                    elif t == 'state':
                        my = state['my_id']
                        incoming = {
                            p['id']: {
                                'x': float(p['x']),
                                'y': float(p['y']),
                                'name': p.get('name', ''),
                            }
                            for p in d.get('players', [])
                        }
                        # update others from server; keep local x/y for self (client prediction)
                        for pid, pdata in incoming.items():
                            if pid == my:
                                if my in state['peers']:
                                    state['peers'][my]['name'] = pdata['name']
                                else:
                                    state['peers'][my] = pdata
                            else:
                                state['peers'][pid] = pdata
                        # remove players no longer in the room
                        for pid in list(state['peers']):
                            if pid not in incoming and pid != 'local':
                                state['peers'].pop(pid)

                    elif t == 'joined':
                        state['room'] = d.get('room')
                        print(f"[client] joined room '{state['room']}'")

                    elif t == 'player_join':
                        pid   = d.get('id')
                        pname = d.get('name', '')
                        state['peers'].setdefault(pid, {'x': 0.0, 'y': 0.0, 'name': pname})
                        _push_msg(state, f"+ {pname} joined")
                        print(f"[client] {pname} joined room")

                    elif t == 'player_leave':
                        pid  = d.get('id')
                        who  = state['peers'].get(pid, {}).get('name', pid)
                        state['peers'].pop(pid, None)
                        _push_msg(state, f"- {who} left")
                        print(f"[client] {who} left room")

            await asyncio.gather(_send(), _recv())
    except Exception as e:
        state['error'] = str(e)
        print(f"[client] network error: {e}")


def _push_msg(state, text):
    state['msgs'].append(text)
    if len(state['msgs']) > 6:
        state['msgs'].pop(0)

# ──────────────────────────── Drawing ────────────────────────────

def draw(screen, state, font, font_sm):
    screen.fill((20, 20, 30))

    my_id = state['my_id']
    me    = state['peers'].get(my_id, {'x': 0.0, 'y': 0.0})
    cam_x, cam_y = me['x'], me['y']

    def to_screen(x, y):
        return (
            int(WIDTH  / 2 + (x - cam_x) * TILE),
            int(HEIGHT / 2 + (y - cam_y) * TILE),
        )

    # draw all players
    for pid, p in list(state['peers'].items()):
        sx, sy = to_screen(p['x'], p['y'])
        color  = (80, 160, 255) if pid == my_id else (200, 120, 120)
        pygame.draw.rect(screen, color, pygame.Rect(sx - 10, sy - 10, 20, 20))
        label = font_sm.render(p.get('name', '') or pid, True, (220, 220, 220))
        screen.blit(label, (sx - label.get_width() // 2, sy - 26))

    # ── coords top-centre ──
    cx = round(me['x'], 1)
    cy = round(me['y'], 1)
    coord = font.render(f"pos: ({cx}, {cy})", True, (200, 200, 200))
    screen.blit(coord, (WIDTH // 2 - coord.get_width() // 2, 8))

    # ── player count top-left ──
    pc = font_sm.render(f"Players: {len(state['peers'])}", True, (180, 180, 180))
    screen.blit(pc, (10, 10))

    # ── join/leave messages ──
    for i, m in enumerate(state.get('msgs', [])):
        im = font_sm.render(m, True, (160, 200, 160))
        screen.blit(im, (10, 36 + i * 18))

    # ── network error ──
    if state.get('error'):
        err = font_sm.render('NET ERR: ' + state['error'], True, (255, 80, 80))
        screen.blit(err, (10, HEIGHT - 30))

# ──────────────────────────── Menu ───────────────────────────────

async def run_menu(screen, font):
    """Non-blocking async menu. Uses await asyncio.sleep so network can start."""
    while True:
        await asyncio.sleep(0)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return None
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_1:
                    return '1'
                if ev.key == pygame.K_2:
                    return '2'

        screen.fill((18, 18, 24))
        t  = font.render('Mini Multiplayer Game',            True, (220, 220, 220))
        o1 = font.render('[ 1 ]  Single Player',             True, (180, 220, 180))
        o2 = font.render('[ 2 ]  Multiplayer  (via server)', True, (180, 180, 220))
        h  = font.render('Press 1 or 2',                     True, (120, 120, 120))
        screen.blit(t,  (WIDTH // 2 - t.get_width()  // 2, HEIGHT // 2 - 80))
        screen.blit(o1, (WIDTH // 2 - o1.get_width() // 2, HEIGHT // 2 - 20))
        screen.blit(o2, (WIDTH // 2 - o2.get_width() // 2, HEIGHT // 2 + 20))
        screen.blit(h,  (WIDTH // 2 - h.get_width()  // 2, HEIGHT // 2 + 80))
        pygame.display.flip()
        await asyncio.sleep(1 / 30)

# ──────────────────────────── Game loop ──────────────────────────

async def run_game(screen, font, font_sm, state, out_q, multiplayer):
    """
    Main game loop that yields to asyncio every frame.
    KEY FIX: await asyncio.sleep(0) at top of each frame lets the network
    coroutine run, so messages are processed without blocking.
    """
    send_interval = 1.0 / SEND_HZ
    send_acc      = 0.0
    prev          = time.perf_counter()

    while True:
        # ── yield to asyncio so net_task can process messages ──
        await asyncio.sleep(0)

        now = time.perf_counter()
        dt  = min(now - prev, 0.1)
        prev = now

        # ── handle events ──
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return
                if ev.key == pygame.K_SPACE and multiplayer:
                    try:
                        out_q.put_nowait({'type': 'shoot'})
                    except asyncio.QueueFull:
                        pass

        # ── movement input ──
        keys = pygame.key.get_pressed()
        dx, dy = 0.0, 0.0
        if keys[pygame.K_w]: dy -= 1
        if keys[pygame.K_s]: dy += 1
        if keys[pygame.K_a]: dx -= 1
        if keys[pygame.K_d]: dx += 1
        if dx and dy:                       # normalise diagonal
            f = 1.0 / (2 ** 0.5)
            dx *= f; dy *= f

        # ── local immediate movement (client-side prediction) ──
        my_id = state['my_id']
        if my_id not in state['peers']:
            my_id = 'local'
        p = state['peers'].get(my_id)
        if p:
            p['x'] += dx * SPEED * dt
            p['y'] += dy * SPEED * dt

        # ── periodic move send to server ──
        if multiplayer:
            if dx or dy:
                send_acc += dt
                if send_acc >= send_interval:
                    send_acc = 0.0
                    try:
                        out_q.put_nowait({
                            'type': 'move',
                            'dx': round(dx * SPEED * send_interval, 4),
                            'dy': round(dy * SPEED * send_interval, 4),
                        })
                    except asyncio.QueueFull:
                        pass
            else:
                send_acc = 0.0

        # ── render ──
        draw(screen, state, font, font_sm)
        pygame.display.flip()

        # ── FPS cap (non-blocking) ──
        elapsed = time.perf_counter() - now
        wait    = max(0.0, 1 / 60 - elapsed)
        if wait:
            await asyncio.sleep(wait)

# ──────────────────────────── Entry ──────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name',        default='Player')
    parser.add_argument('--room',        default='room1')
    parser.add_argument('--host',        default='localhost')
    parser.add_argument('--port',        type=int, default=8765)
    parser.add_argument('--multiplayer', action='store_true',
                        help='Skip menu, go straight to multiplayer')
    args = parser.parse_args()

    pygame.init()
    screen  = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(f"[Room: {args.room}] {args.name}")
    font    = pygame.font.SysFont(None, 24)
    font_sm = pygame.font.SysFont(None, 20)

    state = {
        'peers': {'local': {'x': 0.0, 'y': 0.0, 'name': args.name}},
        'my_id': 'local',
        'room':  None,
        'msgs':  [],
        'error': None,
    }
    out_q = asyncio.Queue(maxsize=64)

    # ── choose mode ──
    choice = '2' if args.multiplayer else await run_menu(screen, font)
    if choice is None:
        pygame.quit()
        return

    multiplayer = (choice == '2')
    caption = (f"[Room: {args.room}] {args.name}"
               if multiplayer else f"Single Player — {args.name}")
    pygame.display.set_caption(caption)

    net = None
    if multiplayer:
        net = asyncio.create_task(
            net_task(f"ws://{args.host}:{args.port}",
                     args.name, args.room, out_q, state)
        )

    await run_game(screen, font, font_sm, state, out_q, multiplayer)

    if net:
        net.cancel()
    pygame.quit()


if __name__ == '__main__':
    asyncio.run(main())
