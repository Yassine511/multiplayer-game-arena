# Multiplayer Game Arena (CS411 Project #2)

A competitive 2D arena: 3 to 10 players walk a shared map to 10 question
terminals and race to answer MCQs within 3 minutes. Whoever creates a room
**hosts it as a spectator**: they choose the questions (write them, import a
CSV, or use the built-in networking set), start the game and watch it live.
Native Python (pygame) clients talk to one authoritative server over raw
**TCP (port 5000)** and **UDP (port 5001)**.

## Quick start: one file, no Python needed

`dist/` holds one self-contained executable per OS. The same file is the server
and the game.

| OS | File |
|---|---|
| Windows 10/11 x64 | `dist/arena.exe` |
| Ubuntu 24.04 / 26.04 x64 (needs glibc 2.38+) | `dist/arena-linux` |

On Linux, make it executable once (copying through Windows drops the bit):

```bash
chmod +x arena-linux
```

1. **The PC that runs the server:** start the file and click **HOST ON THIS PC**.
   The login screen then shows the address others should type
   (LAN IP and, if running, Tailscale IP). A console window shows the server log.
2. **Every other PC:** start the file, type that address under
   **JOIN A SERVER**, press **CONNECT**. Mistyped it? Press Esc on the login screen to go back.
3. Register or log in. In the lobby, **CREATE ROOM** makes you the host
   (spectator); the others **JOIN** with the 6-digit code or the room list.

Skip the launcher with `arena --server 192.168.1.20`. Run a headless server
(no window) with `arena server` (`--public-host X` is accepted as before).
When frozen, accounts are stored in `arena_data/users.json` next to the
executable.

## Run from source

Python 3.10+ on every machine:

```
pip install -r requirements.txt
```

All commands below are run **from this `arena/` folder**.

```
python arena.py                          # launcher: host here or join
python arena.py server                   # headless server
python arena.py --server 192.168.1.20    # straight to a server's login
```

`python -m server.main` and `python -m client.main --server IP` still work.
There is no admin account any more: every registered user can create rooms,
and the creator of a room is its host and spectator.

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
| Arrow keys | move (220 px/s); WASD is not used |
| E | open the terminal within 60 px |
| 1-4 or click | answer; Esc closes the question |
| Space (or click the button) | fire your ultimate once it is charged |

* First correct answer at a terminal: **+100**. The terminal cools down for
  5 s in the winner's colour, then shows a new question.
* **Each terminal can be cracked by 3 different players, once each**
  (`ARENA_TERMINAL_USES`). After the third, it goes **OFFLINE** for the rest of the
  round. A player who already cracked a terminal cannot use it again, so you
  have to keep moving. Labels show the count, e.g. `T4 2/3`.
* Correct but someone was first: `too_late`, 0 points.
* Wrong answer: **-20** (the score floors at 0), a 5 s lockout from that
  terminal only, and your streak resets.
* The round ends at 180 s, or earlier once no connected player has a terminal
  left to crack. The highest score wins; ties go to whoever reached the score
  first.

### Ultimates (bonus)

Answer **5 questions correctly in a row** and an **ULTIMATE READY** button
appears. Press Space or click it, and **every other player loses 10 points**
(never below 0). Every screen in the room, including the host's, plays the
caster's cut-scene. Each one is drawn in code, with synthesized sound:

| Character | Ultimate |
|---|---|
| Gojo | *Domain Expansion: Infinite Void*: warp-speed void, the Six Eyes open, information overload |
| Sukuna | *Domain Expansion: Malevolent Kitchen*: a shrine rises under a blood moon; Dismantle / Cleave / Chop Chop (with chef's hat) |
| MUI Goku | *Kamehameha*: KA-ME-HA-ME charge, then a full-screen beam |
| Trump | *Sends $5 billion to Israel*: the money printer goes brrr, a counter rolls to $5,000,000,000, and the wire transfer is paid with your points |
| Palantir Patrick | *Drone strike*: night-vision Gotham HUD, each victim target-locked, then a drone drops a bomb on them |
| Claude | *Code review*: Claude diffs the leaderboard (`- "bob": 40` / `+ "bob": 30`), stamps CHANGES REQUESTED and ships the patch |
| Sam Altman | *Steal their RAM*: each victim's RAM sticks fly into a data centre while their GB counters drain to 0 |
| Mia, Leo, Epstein | -10 with no animation (a notice only) |

The streak counts correct answers; a wrong answer breaks it (`too_late` does
not). Only one charge is held at a time.

### Questions: the host decides

In the room, the host's middle panel is the **question bank**. The game cannot
start until it has at least one question.

* **WRITE**: type a question, four choices, click the letter of the right one,
  and press **ADD QUESTION** (Enter). The form stays open for the next one.
  Tab moves between fields and Ctrl+V pastes.
* **IMPORT CSV**: paste a path, or just **drag a .csv file onto the window**.
  **ADD TO BANK** appends; **REPLACE BANK** starts over.
* **BUILT-IN SET**: adds the 52 networking questions in `server/data/questions.json`.
* Hover a row and click **X** to delete it; **CLEAR ALL** empties the bank.

CSV format, one question per row (a header row is optional; `,` `;` or tab
separators all work; quote cells that contain the separator):

```
question,choice A,choice B,choice C,choice D,answer,topic
How many bits are in an IPv4 address?,16,32,64,128,B,IP
Which port does HTTPS use by default?,80,21,443,8080,443,Ports
```

`answer` is 1-4, A-D, or the exact text of the right choice. `topic` is
optional. See `sample_questions.csv`. Limits: 200 questions per room,
220 characters per question and 90 per choice. Players only ever receive the
question count and the question they open; answers stay on the server.

## Project layout

```
arena.py             single entry point (launcher / client / `server`), used by the executable
arena.spec           PyInstaller recipe for the one-file build
common/protocol.py   message names, TCP line framing, UDP datagram helpers
common/qcsv.py       the host's CSV question import
common/config.py     ports, game constants (env-overridable)
common/map_data.py   rooms, terminals T1-T10, spawns, collision (shared by both sides)
common/map_grid.py   generated floor grid (tools/build_map.py)
server/main.py       accept loop, dispatch, tick loop (20 Hz), heartbeats, resume
server/connection.py per-client reader + writer threads and outbound queue
server/auth.py       users.json (salted PBKDF2), sessions and tokens
server/rooms.py      room registry, codes, join / leave / spectate
server/game.py       phases, terminals (3 uses each), the answer race, scoring, streaks/ultimates, timer
server/udp.py        POS validation, SNAPSHOT broadcast
server/data/questions.json   the built-in set: 52 networking MCQs (answers never leave the server)
client/main.py       app shell (--server), embedded server when hosting
client/cutscenes.py  the seven ultimate cut-scenes (procedural pygame drawing)
client/sfx.py        synthesized sound effects for the cut-scenes
client/net.py        TCP + UDP background threads, ping, auto-reconnect + RESUME
client/assets.py     map, backdrops, room cards, character sprites, terminal beacons
common/characters.py the ten playable characters (shared by server and client)
client/ui.py         pixel-station UI kit: palette, text, panels, buttons
tools/               import_art.py, build_map.py
client/screens/      launch, login, lobby, room (+ qeditor: question bank tools), game, spectator, results
```

## Art (map, rooms, characters)

The game is set on the Mediterranean University station: ten rooms joined by
corridors, one terminal per room, everyone spawns on the central plaza.

| T | Room | T | Room |
|---|---|---|---|
| T1 | Central Plaza | T6 | Med Bay |
| T2 | Electronics Lab | T7 | Science Lab |
| T3 | Engine Room | T8 | Classroom |
| T4 | Greenhouse | T9 | Auditorium |
| T5 | Reactor Lab | T10 | Command Lounge |

Players see a camera that follows them (with a minimap); the host (spectator)
sees the whole station.

The artist's originals live in `Map_and_rooms_charac/`. Two small tools turn them
into what the game loads (they need `pip install pillow numpy scipy`; playing
does not):

```
python tools/import_art.py     # Map_and_rooms_charac/ -> client/assets/ (map, room cards, backdrops)
python tools/build_map.py      # client/assets/map.png -> common/map_grid.py (the walls)
```

`build_map.py` reads the walls straight off the picture: the dark hull and
open space are solid, rooms and corridors are floor, and the back walls and
furniture listed at the top of the script are blocked. Server and client both
import the resulting grid, so they always agree on collisions. Re-run both
tools after the map art changes (`--debug DIR` writes pictures of the floor).
Terminal, spawn and room positions are in `common/map_data.py`, written in
map.png pixels.

**Characters.** Ten characters: Gojo, Mia, Leo, MUI Goku, Epstein, Sukuna,
Claude, Palantir Patrick, Sam Altman and Trump. In the room, before the game,
every player picks one: the "Your character" panel (arrows `<` `>` or the
left/right keys) or the full grid (`C`, then click or press 1-0). Several
players may pick the same character; the coloured name above each sprite tells
them apart. The pick is remembered in `~/.arena_client.json` and sent to the
server (`SET_CHARACTER`) after login, so it carries into every room.

The names and order are in `common/characters.py`. The art is baked from
`Map_and_rooms_charac/` (three turnaround sheets plus seven Codex pet sheets in
`Map_and_rooms_charac/characters/`) into `client/assets/characters/`:

```
python tools/import_characters.py
```

The look of every screen (palette, pixel text, panels, buttons) is in
`client/ui.py`.

## Configuration

| Variable / flag | Default | Meaning |
|---|---|---|
| `--server` (client) / `ARENA_SERVER` | 127.0.0.1 | server address |
| `--tcp-port`, `--udp-port` / `ARENA_TCP_PORT`, `ARENA_UDP_PORT` | 5000 / 5001 | ports |
| `--public-host` (server) / `ARENA_PUBLIC_HOST` | auto | address written in the join string and QR |
| `ARENA_GAME_SECONDS` | 180 | round length (handy for rehearsals) |
| `ARENA_MIN_PLAYERS` | 3 | players needed to start (the host does not count); set to 1 to test with one player |
| `ARENA_TERMINAL_USES` | 3 | how many different players can crack a terminal before it goes offline |
| `ARENA_ULT_STREAK` | 5 | correct answers in a row that charge an ultimate |
| `ARENA_USERS_FILE` | server/data/users.json | account file (next to the executable when frozen) |

## Build the executables

PyInstaller cannot cross-compile, so build each file on its own OS. The same
`arena.spec` works on both.

**Windows** (PowerShell, in `arena/`):

```
pip install -r requirements.txt pyinstaller
python -m PyInstaller arena.spec --noconfirm --clean
```

This writes `dist/arena.exe`.

**Ubuntu** (or WSL Ubuntu), in `arena/`:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pyinstaller
.venv/bin/python -m PyInstaller arena.spec --noconfirm --clean
```

This writes `dist/arena`. If `venv` complains about `ensurepip`, run
`sudo apt install python3-venv` first. The Linux binary runs on systems whose
glibc is at least as new as the build machine's, so build on the oldest Ubuntu
you need to support.

## Demo script

1. On PC 1, start `arena.exe` and click **HOST ON THIS PC**. Note the IP on the login screen.
2. On PCs 2-4, start the file, type that IP and click **CONNECT**. Register one new player and log in the others.
3. PC 1 logs in, clicks **CREATE ROOM** and is the host-spectator. The 6-digit code and QR appear.
4. The host drags `sample_questions.csv` onto the window, writes one more question, and maybe adds the built-in set.
5. Players join with the code; one leaves and rejoins; the roster updates live.
6. Starting with 2 players is refused; with 3 the countdown runs.
7. Two players race to the same terminal: one gets `correct`, the other `too_late`.
8. The same player tries that terminal again and is told to find another. After 3 players crack it, it shows OFFLINE.
9. A player answers wrong and shows the 5 s lockout; scores update everywhere.
10. Someone reaches a 5-streak and fires their ultimate: every screen plays the cut-scene and the others lose 10.
11. Turn off one client's Wi-Fi: within 5 s it greys out; the game continues.
12. Turn the Wi-Fi back on: it resumes within 30 s with the score intact.
13. The timer ends (or every terminal is used up); the leaderboard and winner pop up everywhere.
14. Bonus: repeat a short round over Tailscale and show `tailscale status`.
