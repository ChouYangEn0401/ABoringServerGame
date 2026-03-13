import asyncio
import json
import websockets

HOST = 'localhost'
PORT = 8765

# Global state
clients = {}      # id -> websocket
players = {}      # id -> {'x': int, 'y': int, 'room': str, 'name': str}
rooms = {}        # room -> set(pid)
next_id = 1
lock = asyncio.Lock()

TICK_INTERVAL = 0.05  # 20 ticks per second

async def send_safe(ws, msg):
    try:
        await ws.send(msg)
    except Exception:
        pass

async def broadcast_room(room):
    pids = rooms.get(room, set())
    if not pids:
        return
    state = {
        'type': 'state',
        'room': room,
        'players': [{'id': pid, 'x': players[pid]['x'], 'y': players[pid]['y'], 'name': players[pid].get('name','')} for pid in pids]
    }
    msg = json.dumps(state)
    tasks = []
    for pid in list(pids):
        ws = clients.get(pid)
        if ws:
            tasks.append(send_safe(ws, msg))
    if tasks:
        await asyncio.gather(*tasks)

async def broadcast_lobby():
    # simple lobby info: list of rooms and counts
    info = {'type': 'lobby', 'rooms': [{'name': r, 'players': len(rooms[r])} for r in rooms]}
    msg = json.dumps(info)
    tasks = [send_safe(ws, msg) for ws in clients.values()]
    if tasks:
        await asyncio.gather(*tasks)

async def tick_loop():
    while True:
        await asyncio.sleep(TICK_INTERVAL)
        # broadcast each active room
        for room in list(rooms.keys()):
            await broadcast_room(room)

async def handler(ws):
    global next_id
    async with lock:
        pid = str(next_id)
        next_id += 1
        clients[pid] = ws
        players[pid] = {'x': 0.0, 'y': 0.0, 'room': None, 'name': ''}
    try:
        await send_safe(ws, json.dumps({'type': 'welcome', 'id': pid}))
        await broadcast_lobby()
        async for message in ws:
            try:
                data = json.loads(message)
            except Exception:
                continue
            mtype = data.get('type')
            if mtype == 'join':
                room = data.get('room','default')
                name = data.get('name','')
                async with lock:
                    # leave old room
                    old = players[pid].get('room')
                    if old and pid in rooms.get(old, set()):
                        rooms[old].discard(pid)
                    # join new
                    rooms.setdefault(room, set()).add(pid)
                    players[pid]['room'] = room
                    players[pid]['name'] = name
                    print(f"[server] player {pid} joined room '{room}' as '{name}'")
                    await send_safe(ws, json.dumps({'type':'joined','room':room}))
                    # notify room of the new player
                    join_msg = json.dumps({'type':'player_join','id': pid, 'name': name})
                    for p in rooms.get(room, set()):
                        ws2 = clients.get(p)
                        if ws2:
                            await send_safe(ws2, join_msg)
                await broadcast_lobby()
                await broadcast_room(room)
            elif mtype == 'move':
                # accept either legacy dir or numeric dx/dy
                if 'dir' in data:
                    d = data.get('dir')
                    if d == 'w':
                        players[pid]['y'] -= 1
                    elif d == 's':
                        players[pid]['y'] += 1
                    elif d == 'a':
                        players[pid]['x'] -= 1
                    elif d == 'd':
                        players[pid]['x'] += 1
                    print(f"[server] move from {pid}: {d} -> ({players[pid]['x']},{players[pid]['y']})")
                else:
                    dx = float(data.get('dx', 0))
                    dy = float(data.get('dy', 0))
                    players[pid]['x'] += dx
                    players[pid]['y'] += dy
                    print(f"[server] move from {pid}: dx={dx},dy={dy} -> ({players[pid]['x']},{players[pid]['y']})")
            elif mtype == 'chat':
                # simple relay
                room = players[pid].get('room')
                if room:
                    msg = json.dumps({'type':'chat','from':players[pid].get('name',''), 'text': data.get('text','')})
                    for p in rooms.get(room, set()):
                        ws2 = clients.get(p)
                        if ws2:
                            await send_safe(ws2, msg)
    finally:
        async with lock:
            # remove client
            clients.pop(pid, None)
            room = players.get(pid, {}).get('room')
            if room and pid in rooms.get(room, set()):
                # notify remaining clients that this player is leaving
                leave_msg = json.dumps({'type':'player_leave','id': pid})
                for p in rooms.get(room, set()):
                    if p == pid:
                        continue
                    ws2 = clients.get(p)
                    if ws2:
                        await send_safe(ws2, leave_msg)
                rooms[room].discard(pid)
                if not rooms[room]:
                    rooms.pop(room, None)
            players.pop(pid, None)
        await broadcast_lobby()
        # also broadcast the room state (so remaining clients update immediately)
        if room:
            await broadcast_room(room)

async def main():
    print(f"╔══════════════════════════════════════════╗")
    print(f"║  Game Server  ws://{HOST}:{PORT}             ║")
    print(f"║  Tick rate: {int(1/TICK_INTERVAL)} TPS                      ║")
    print(f"╚══════════════════════════════════════════╝")
    async with websockets.serve(handler, HOST, PORT):
        asyncio.create_task(tick_loop())
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())
