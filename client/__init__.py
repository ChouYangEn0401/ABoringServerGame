"""client  --  Pygame client package for Mini Multiplayer Bullet Game.

Usage:
    python -m client [--name NAME] [--room ROOM] [--host HOST] [--port PORT]
                     [--multiplayer]

Or import and call ``main()`` yourself::

    from client import main
    import asyncio
    asyncio.run(main())
"""
import argparse, asyncio, pygame

from client.config  import WIDTH, HEIGHT
from client.network import net_task
from client.game    import run_menu, run_game


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
            "hp": 10, "max_hp": 10, "score": 0,
            "fdx": 1, "fdy": 0,
            "dead": False, "immortal": True,
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
