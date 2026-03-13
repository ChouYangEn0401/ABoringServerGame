import argparse
import asyncio
import json
import pygame
import websockets

WIDTH, HEIGHT = 800, 600
SCALE = 20

async def network_task(uri, name, room, send_q, state):
    try:
        async with websockets.connect(uri) as ws:
            # server will send welcome
            await ws.send(json.dumps({'type':'join','room':room,'name':name}))

            async def sender():
                while True:
                    msg = await send_q.get()
                    try:
                        await ws.send(json.dumps(msg))
                    except Exception:
                        pass

            async def receiver():
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except Exception:
                        continue
                    m = data.get('type')
                    print('[client-net] received:', data)
                    if m == 'welcome':
                        sid = data.get('id')
                        # map local placeholder to assigned id
                        if state.get('id') == 'local' and 'local' in state['players']:
                            state['players'][sid] = state['players'].pop('local')
                        state['id'] = sid
                    elif m == 'state':
                        # update shared state (merge to keep local placeholders)
                        new_players = {p['id']:{'x':p['x'],'y':p['y'],'name':p.get('name','')} for p in data.get('players',[])}
                        state['players'].update(new_players)
                    elif m == 'joined':
                        state['room'] = data.get('room')

            await asyncio.gather(sender(), receiver())
    except Exception as e:
        state['error'] = str(e)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='Player')
    parser.add_argument('--room', default='room1')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()

    uri = f"ws://{args.host}:{args.port}"

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(f"[Room: {args.room}] {args.name}")
    pygame.key.set_repeat(50,50)
    clock = pygame.time.Clock()

    send_q = asyncio.Queue()
    # start with a local placeholder so something is rendered immediately
    state = {'players': {'local': {'x': 0, 'y': 0, 'name': args.name}}, 'error': None, 'id': 'local', 'room': None}

    net = asyncio.create_task(network_task(uri, args.name, args.room, send_q, state))

    running = True
    font = pygame.font.SysFont(None, 20)
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                else:
                    if ev.key in (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d):
                        keymap = {pygame.K_w:'w', pygame.K_a:'a', pygame.K_s:'s', pygame.K_d:'d'}
                        try:
                            send_q.put_nowait({'type':'move','dir':keymap[ev.key]})
                        except asyncio.QueueFull:
                            pass
                    elif ev.key == pygame.K_SPACE:
                        try:
                            send_q.put_nowait({'type':'shoot'})
                        except asyncio.QueueFull:
                            pass

        screen.fill((20,20,30))

        # draw players
        for pid, p in state.get('players', {}).items():
            x = int(WIDTH/2 + p['x']*SCALE)
            y = int(HEIGHT/2 + p['y']*SCALE)
            if pid == state.get('id'):
                color = (80,160,255)
            else:
                color = (200,120,120)
            pygame.draw.rect(screen, color, pygame.Rect(x-10, y-10, 20, 20))
            # draw name
            img = font.render(p.get('name','') or pid, True, (220,220,220))
            screen.blit(img, (x-10, y-25))

        if state.get('error'):
            img = font.render('Network error: '+state['error'], True, (255,50,50))
            screen.blit(img, (10,10))

        pygame.display.flip()
        clock.tick(60)

    net.cancel()
    pygame.quit()

if __name__ == '__main__':
    asyncio.run(main())
