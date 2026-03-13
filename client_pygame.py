import asyncio
import json
import argparse
import pygame
import websockets

WIDTH, HEIGHT = 800, 600
SCALE = 20

async def network_task(uri, name, room, send_q, state):
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({'type':'join','room':room,'name':name}))

            async def sender():
                while True:
                    msg = await send_q.get()
                    await ws.send(json.dumps(msg))

            async def receiver():
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except Exception:
                        continue
                    if data.get('type') == 'state':
                        # update shared state
                        state['players'] = {p['id']:{'x':p['x'],'y':p['y'],'name':p.get('name','')} for p in data.get('players',[])}

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
    clock = pygame.time.Clock()

    send_q = asyncio.Queue()
    state = {'players': {}, 'error': None}

    net = asyncio.create_task(network_task(uri, args.name, args.room, send_q, state))

    running = True
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
                        await send_q.put({'type':'move','dir':keymap[ev.key]})
                    elif ev.key == pygame.K_SPACE:
                        await send_q.put({'type':'shoot'})

        screen.fill((20,20,30))

        # draw players
        for pid, p in state.get('players', {}).items():
            x = int(WIDTH/2 + p['x']*SCALE)
            y = int(HEIGHT/2 + p['y']*SCALE)
            color = (100,200,100) if p.get('name','').lower().startswith('player') else (200,100,100)
            pygame.draw.rect(screen, color, pygame.Rect(x-10, y-10, 20, 20))
            # draw name
            font = pygame.font.SysFont(None, 20)
            img = font.render(p.get('name','') or pid, True, (200,200,200))
            screen.blit(img, (x-10, y-25))

        if state.get('error'):
            font = pygame.font.SysFont(None, 24)
            img = font.render('Network error: '+state['error'], True, (255,50,50))
            screen.blit(img, (10,10))

        pygame.display.flip()
        clock.tick(60)

    net.cancel()
    pygame.quit()

if __name__ == '__main__':
    asyncio.run(main())
