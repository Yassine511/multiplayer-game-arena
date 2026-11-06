# Multiplayer Game Arena (CS411 Project #2)

A competitive 2D arena: 3 to 10 players walk a shared map to 10 question
terminals and race to answer computer-networking MCQs within 3 minutes, while
an admin spectates live. Native Python (pygame) clients talk to one
authoritative server over raw **TCP (port 5000)** and **UDP (port 5001)**.

## Install

Python 3.10+ on every machine:

```
pip install -r requirements.txt
```

All commands below are run **from this `arena/` folder**.

## Run on one LAN (same Wi-Fi or hotspot)

**PC 1 (server + admin):**

```
python -m server.main
python -m client.main --admin
```

The server prints its LAN and Tailscale addresses at startup. On first start
it creates `server/data/users.json` with the admin account
(`admin` / `admin123`; change it with the `ARENA_ADMIN_PASSWORD` environment
variable before the first start).

**PCs 2-4 (players):**

```
python -m client.main --server 192.168.1.20
```

(Use the LAN IP the server printed.)

**Firewall (server PC, do this before demo day).** The Windows Defender prompt
on first start often allows only *Private* networks, while campus Wi-Fi and
phone hotspots are usually *Public*, so packets get dropped silently. Open
both ports for every profile from an **administrator** PowerShell:

```
New-NetFirewallRule -DisplayName "Arena TCP" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "Arena UDP" -Direction Inbound -Protocol UDP -LocalPort 5001 -Action Allow -Profile Any
```

**Join string / QR address.** The server writes its Tailscale IP into the
join string and QR when Tailscale is running, otherwise its LAN IP. For the
LAN part of the demo, force the LAN IP:

```
python -m server.main --public-host 192.168.1.20
```

## Run across networks (bonus, Tailscale)

1. Create one Tailscale account for the team; install Tailscale on all four
   laptops and log each one into it.
2. On the server PC allow inbound TCP 5000 and UDP 5001 in the firewall.
3. Start the server as usual (it binds `0.0.0.0`, so it listens on the LAN and
   the tailnet interface).
4. Point each client at the server's tailnet IP or MagicDNS name:

   ```
   python -m client.main --server 100.x.y.z
   ```

5. Show `tailscale status` on a client: the server's peer entry and whether
   the link is direct or relayed (DERP). Both work.

Tailscale **Funnel** is not used: it only publishes TCP on ports
443/8443/10000, so the UDP traffic could never reach the server.

## How to play

| Key | Action |
|---|---|
| WASD / arrows | move (220 px/s) |
| E | open the terminal within 60 px |
| 1-4 or click | answer; Esc closes the question |

* First correct answer at a terminal: **+100**; the terminal cools down for
  5 s in the winner's colour, then shows a new question.
* Correct but someone was first: `too_late`, 0 points.
* Wrong answer: **-20** (score floors at 0) and a 5 s lockout from that
  terminal only.
* The highest score after 180 s wins; ties go to whoever reached the score first.

Any logged-in player can create a room (they become host and can start it).
The admin creates rooms as host-spectator and can spectate any room. Start
needs at least 3 players.

## Project layout

```
common/protocol.py   message names, TCP line framing, UDP datagram helpers
common/config.py     ports, game constants (env-overridable)
common/map_data.py   walls, terminals T1-T10, spawns (shared by both sides)
server/main.py       accept loop, dispatch, tick loop (20 Hz), heartbeats, resume
server/connection.py per-client reader + writer threads and outbound queue
server/auth.py       users.json (salted PBKDF2), sessions and tokens
server/rooms.py      room registry, codes, join / leave / spectate
server/game.py       phases, terminals, claim race, scoring, timer
server/udp.py        POS validation, SNAPSHOT broadcast
server/data/questions.json   52 networking MCQs (answers never leave the server)
client/main.py       app shell (--admin, --server)
client/net.py        TCP + UDP background threads, ping, auto-reconnect + RESUME
client/assets.py     art loader with shape fallbacks
client/screens/      login, lobby, room, game, spectator, results
```

## Art (map and characters)

Drop PNG files into `client/assets/` and they are picked up automatically, no
code change needed. Anything missing is drawn with simple shapes.

| File | Used for | Size it is scaled to |
|---|---|---|
| `map.png` | whole background | 1280 x 720 |
| `player_<c>_<dir>.png` | player with colour index `c` (0-9) facing `dir` (`up`/`down`/`left`/`right`) | 40 x 40 |
| `player_<c>.png` | player with colour `c`, any direction | 40 x 40 |
| `player_<dir>.png` / `player.png` | same sprite for every player | 40 x 40 |
| `terminal.png` | terminal ready to answer | 46 x 46 |
| `terminal_cooldown.png` | terminal just claimed | 46 x 46 |

If you draw your own `map.png`, its walls must match the rectangles in
`common/map_data.py` (the server uses those for collision); edit the
coordinates there to match the art. Terminal and spawn positions live in the
same file.

## Configuration

| Variable / flag | Default | Meaning |
|---|---|---|
| `--server` (client) / `ARENA_SERVER` | 127.0.0.1 | server address |
| `--tcp-port`, `--udp-port` / `ARENA_TCP_PORT`, `ARENA_UDP_PORT` | 5000 / 5001 | ports |
| `--public-host` (server) / `ARENA_PUBLIC_HOST` | auto | address written in the join string and QR |
| `ARENA_GAME_SECONDS` | 180 | round length (handy for rehearsals) |
| `ARENA_ADMIN_PASSWORD` | admin123 | admin password, used when users.json is first created |

## Demo script

1. Start the server on PC 1 and open the admin client there.
2. On PCs 2-4: register one new player, log in the others.
3. Admin creates a room; the 6-digit code and QR appear.
4. Players join with the code; one leaves and rejoins; the roster updates live.
5. Admin tries to start with 2 players and is refused; with 3 the countdown runs.
6. Two players race to the same terminal: one gets `correct`, the other `too_late`.
7. A player answers wrong and shows the 5 s lockout; scores update everywhere.
8. Turn off one client's Wi-Fi: within 5 s it greys out; the game continues.
9. Turn the Wi-Fi back on: it resumes within 30 s with the score intact.
10. The timer ends; the leaderboard and winner pop up everywhere.
11. Bonus: repeat a short round over Tailscale and show `tailscale status`.
