# DEVBOOK — Mini Networked Bullet Game

Purpose
-------
Create a minimal, server-authoritative multiplayer demo suitable for local and remote testing. The game is a simple top-down shooter where players (colored squares) move with WASD, shoot with Space, collect health pickups (❤️), and fight AI monsters. Friendly fire is off; monsters don't hurt each other.

High-level goals
----------------
- Playable locally with multiple client windows.
- Server supports lobby/rooms and authoritative game state.
- Clients render using `pygame` and send inputs; server runs game logic and broadcasts state at fixed tick rate.
- Simple enemy types: small (2 hits) and big (5–8 hits, more complex patterns).

Boundaries & responsibilities
----------------------------
- Server (`server.py`):
  - Accepts websocket connections, manages lobby and rooms.
  - Maintains authoritative state: players, bullets, enemies, pickups, obstacles.
  - Processes client input commands (move, shoot) and runs fixed tick loop (e.g., 20–30 TPS).
  - Runs enemy AI and collision detection.
  - Broadcasts compact world state snapshots each tick (or every N ticks).

- Client (`client.py`):
  - Connects to server, sends player input events (direction, shoot) with timestamps or sequence ids.
  - Renders world using `pygame`: colored rectangles for players, hearts for pickups, simple sprites for bullets/enemies.
  - Local prediction is optional (initial version: render authoritative state from server to keep code simple).

- Single executable vs separate: keep `server.py` and `client.py` separate for clarity. Later we can combine into a single entry with `--server` flag.

Networking: messages & protocol
------------------------------
- Transport: WebSockets over TCP (use `websockets` library).
- JSON messages (small, human-readable). Each message has `type` and payload.

Client -> Server (examples):
- `{"type":"join", "name":"PlayerA", "room":"room1"}`
- `{"type":"input", "seq":42, "up":0,"down":1,"left":0,"right":0, "shoot":1}`
- `{"type":"chat", "text":"hi"}` (optional)

Server -> Client (examples):
- `{"type":"welcome","id":"1","room":"room1"}`
- `{"type":"lobby","rooms":[{"name":"room1","players":2}]}`
- `{"type":"state","tick":123,"players":[...],"enemies":[...],"bullets":[...],"pickups":[...]}`
- `{"type":"game_over","reason":"win"}`

State encoding guidance
- Keep arrays compact. Example player record: `{id,x,y,dir,hp,color}`. Bullets: `{id,x,y,vx,vy,owner}`.
- Only send what clients need to render. Server keeps full authoritative objects.

Game rules (core)
-----------------
- Player: 3 HP (lives). If HP <= 0, player is dead and removed from active players (or sent to spectator).
- Friendly fire: off.
- Bullet collides with enemies and players (but ignore same-team collisions).
- Pickup: restores 1 HP up to max (3).
- Enemies: small (HP=2, simple straight shooting or move), big (HP random 5–8, complex patterns). Enemy attacks are simple projectiles.
- Level: randomized obstacles and spawn positions for enemies and pickups. Clear all enemies → victory screen.

Tick rate and determinism
------------------------
- Fixed server tick: 20 ticks per second (50 ms). Server integrates movement, spawns bullets, resolves collisions.
- Clients render as often as possible, but only authoritative positions come from server.

Phased development plan
------------------------
Phase 0 — Spec & scaffold (this task)
- Deliver `DEVBOOK.md`, update `README.md`, finalize message formats.

Phase 1 — Minimal networking & headless test
- Implement server lobby + simple room creation.
- Implement minimal authoritative loop with players only (no enemies, bullets). Use headless clients (print state).
- Verify local multiple clients can connect.

Phase 2 — Pygame client + local play
- Implement `pygame` client rendering players and moving via WASD; send input to server.
- Add shooting (space) message; server spawns bullets and broadcasts.
- Add pickups and simple obstacles.

Phase 3 — Enemies & combat
- Implement small and big enemy types with basic AI (move toward players, shoot simple bullets or patterns).
- Implement health, damage, death, and victory conditions.

Phase 4 — Polish & remote testing
- Add lobby UI (client-side), reconnect logic, and basic NAT/port guidance in README.
- Add sample launch scripts and integration test recipe.

Files to create
---------------
- `server.py` — server implementation (websockets, asyncio)
- `client.py` — pygame client
- `requirements.txt` — `websockets`, `pygame`
- `DEVBOOK.md` (this file)
- `README.md` — run instructions and remote testing notes

Testing & run notes
-------------------
- Local dev: open one terminal run `python server.py`, open two terminals run `python client.py`.
- Remote testing: run server on a machine reachable from other devices (use IP instead of localhost), ensure firewall allows port (default 8765). For NAT traversal, use port-forwarding on router.

Next deliverable
----------------
- Implement Phase 1: update `server.py` to include lobby/rooms and a small authoritative tick loop; provide a headless client mode for quick verification. After Phase 1 passes, proceed to `pygame` client in Phase 2.
