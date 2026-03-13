"""server  --  Authoritative game-server package.

Import hierarchy (no cycles):
    config  <-  helpers  <-  buffs  <-  weapons  <-  pickups  <-  game  <-  network

Quick-start::

    import server
    asyncio.run(server.main())
"""
import asyncio, websockets

from server.config  import HOST, PORT, EMBEDDED_PORT, TICK
from server.network import handler, tick_loop

# Re-export so ``import server as srv; srv.EMBEDDED_PORT`` still works.
__all__ = ["run_embedded", "main", "EMBEDDED_PORT"]


async def run_embedded():
    """Start the server on localhost for single-player / embedded mode."""
    async with websockets.serve(handler, "localhost", EMBEDDED_PORT):
        asyncio.create_task(tick_loop())
        await asyncio.Future()


async def main():
    print("+" + "=" * 42 + "+")
    print(f"|  Game Server   ws://{HOST}:{PORT}          |")
    print(f"|  Tick: {int(1/TICK)} TPS   Boundary: +/-50        |")
    print("+" + "=" * 42 + "+")
    async with websockets.serve(handler, HOST, PORT):
        asyncio.create_task(tick_loop())
        await asyncio.Future()
