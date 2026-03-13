# Mini Multiplayer Game (Python)

This is a minimal server-authoritative multiplayer demo using `websockets` and `asyncio`.

Files
- [server.py](server.py)
- [client.py](client.py)
- [requirements.txt](requirements.txt)

Setup

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run

Start the server in one terminal:

```powershell
python server.py
```

Start two clients in separate terminals:

```powershell
python client.py
python client.py
```

Usage

In each client terminal type `w`, `a`, `s`, or `d` followed by Enter to move. Type `q` then Enter to quit.

Notes

- The server keeps the authoritative player positions and broadcasts the full world state after each move.
- This is a tiny, educational demo — intended for local testing and experimentation.
- Docker instructions are intentionally omitted for now per your request.



IDEA:
ok, let make game much more difficult !!!

1. refactor (if needed)
2. split enemy, projectile, character, pickable item into better file arrangement  (if needed, optional)

3. shooting method upgrade, `sigle-slow-shot` default. there are pickable weapon to allow user to change shoot mode, `shotgun-mode (10)`, `machine-gun-mode (40)`, `bumb-throw-gun (5) (toss away and split into area damage)`, when bullet ran off, will switch back to deafault gun `pistol-gun`. of course, please design the cold down for each weapon for me
4. item-pickable: `thunder-boost`, `snowflake-protection`, `respawn-cookie (instance respawn without panelty)`, 'muscle (attack damage double)'
5. player dead, will minus 5 enemey kill amount for penalty
6. if enemy accidentally get `respawn-cookie` the first kill will not add kill amount, other item-pickale can also active on enemy like it does on player
7. enemy get slowly ability increase when game-stage level-up, and so do player, but enemy will get much more scale then player does
8. add two more enemy, one that can freeze down player if hit, one can poison player and deal continous damage to player
9. player heart become blood now, and heart can heal 15%, add one more `item-pickable`, a `double-heart`, a regeneration skill for healing 25% in 5 seconds, hit will stop this
10. big enemy drops random gift, despawn in 10 seconds, color fading out 75% for first 7 second, and until the end will vanish

do as much as you could thanks



add 2 more 3 big enemy
1. slow down player when path attack hit, create a path that slow down player
2. a summoner, can summon `green-cube` monster (up to 10 max), in a very slowly pace, but when this enemey spawn can spawn 3 at the begining
3. `space-man` can teleport to near player position, it will summon a portal on ground, this will carry all enemy with it, CD for 120 secs, attack frozen player on ground 3 seconds, attack CD 10 secs, but touch player also deal damage
> when big enemy dead, can drop gift

add 3 more small enemy
1. stay on ground for 7 secs may explode when anything get passed, if player, explode attack, if enemy, explode and add random current available buff onto enemy ; if time pass, summon 7 small tiny 米黃色 cube
2. 米黃色 cube, run fast, chase after player, when first time hit by player bullet, cancel attack, suddenly sprint toward player in immortal status, if hit player due huge damage; this ability can use twice then dead
3. a bumb thrower

player gun can no more canceling the enemy bullet by deafult, this is the `GameAbility` player can picked
1. bullet cancel
2. kill enemy count twice
3. kill enemy recharge health 2%
4. kill enemy increase attack speed for 1%, continuously kill will maintain the time, max to 200%
5. gun can shoot extra 2~7 time per 10 seconds within using on ammo