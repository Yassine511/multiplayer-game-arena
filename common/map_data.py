"""The station map, shared by server (validation) and client (drawing + prediction).

World coordinates stay 1280 x 720 as in the spec; the art (client/assets/map.png,
2669 x 1498) is that world drawn at ~2.085 px per unit. Positions below are
written in art pixels, which is what you read off the image in an editor, and
converted once at import.

Walls: the floor is a grid of CELL x CELL squares generated from the art by
tools/build_map.py (hull, back walls and furniture are solid). The grid is
already shrunk by the player foot radius, so a position is legal exactly when
its cell is set.
"""
import base64
import zlib

from common import config, map_grid

W, H = config.WORLD_W, config.WORLD_H
ART_W, ART_H = 2669, 1498
_SX, _SY = W / ART_W, H / ART_H


def from_art(px, py):
    """Art pixels -> world units."""
    return round(px * _SX, 1), round(py * _SY, 1)


# --- rooms (art px): id, name, asset slug, bounds, terminal -----------------------------
_ROOMS = [
    # id  name               slug           x0    y0    x1    y1     terminal at
    (1, "Central Plaza",     "plaza",       1075, 225,  1665, 805,   (1370, 512)),
    (2, "Electronics Lab",   "electronics", 700,  300,  1095, 835,   (882, 585)),
    (3, "Engine Room",       "engine",      400,  160,  715,  500,   (588, 402)),
    (4, "Greenhouse",        "greenhouse",  55,   500,  405,  960,   (343, 712)),
    (5, "Reactor Lab",       "reactor",     600,  835,  1025, 1160,  (815, 1068)),
    (6, "Med Bay",           "medbay",      1105, 860,  1465, 1225,  (1248, 1108)),
    (7, "Science Lab",       "laboratory",  1535, 680,  1905, 1215,  (1662, 815)),
    (8, "Classroom",         "classroom",   2010, 925,  2485, 1280,  (2380, 1095)),
    (9, "Auditorium",        "auditorium",  2045, 545,  2500, 830,   (2166, 702)),
    (10, "Command Lounge",   "command",     1775, 185,  2245, 485,   (1978, 290)),
]

ROOMS = []
TERMINALS = []          # T1..T10, one per room, each on a console drawn in the art
for _id, _name, _slug, _x0, _y0, _x1, _y1, _t in _ROOMS:
    _ax, _ay = from_art(_x0, _y0)
    _bx, _by = from_art(_x1, _y1)
    _tx, _ty = from_art(*_t)
    ROOMS.append({"id": _id, "name": _name, "slug": _slug, "rect": (_ax, _ay, _bx - _ax, _by - _ay)})
    TERMINALS.append({"id": _id, "x": _tx, "y": _ty, "room": _name})

# 10 spawn points on the plaza, around the university seal, assigned in join order
SPAWNS = [from_art(px, py) for px, py in [
    (1370, 395), (1370, 630), (1255, 512), (1485, 512), (1300, 430),
    (1440, 430), (1300, 595), (1440, 595), (1370, 330), (1370, 695),
]]

# --- collision ---------------------------------------------------------------------------
CELL, COLS, ROWS = map_grid.CELL, map_grid.COLS, map_grid.ROWS
_bits = zlib.decompress(base64.b64decode("".join(map_grid.DATA)))
_STEP = CELL * 0.9


def walkable_cell(cx, cy):
    if cx < 0 or cy < 0 or cx >= COLS or cy >= ROWS:
        return False
    i = cy * COLS + cx
    return bool(_bits[i >> 3] & (0x80 >> (i & 7)))


def blocked(x, y, r=None):
    """True if a player standing at (x, y) is inside a wall, furniture or space.

    `r` is accepted for compatibility; the grid already includes the foot radius.
    """
    return not walkable_cell(int(x // CELL), int(y // CELL))


_ASSIST_CELLS = 5          # how far (in cells) a blocked straight move looks sideways for an opening


def _side_opening(x, y, ax, ay):
    """Moving by (ax, ay) along one axis is blocked: which way (-1 / +1) along the other
    axis is the nearest spot from which that move is free? 0 if none is close.

    This is the classic "corner correction": clipping a door frame by a pixel or two
    slides you into the doorway instead of stopping you dead.
    """
    for k in range(1, _ASSIST_CELLS + 1):
        for sign in (1, -1):
            ox, oy = (0, sign * k * CELL) if ax else (sign * k * CELL, 0)
            if all(not blocked(x + (0 if ax else sign * j * CELL), y + (sign * j * CELL if ax else 0))
                   for j in range(1, k + 1)) and not blocked(x + ox + ax, y + oy + ay):
                return sign
    return 0


def move(x, y, dx, dy, r=None):
    """Move in small steps with per-axis collision so players slide along walls, and
    with corner correction so a straight move that just clips an edge slips past it.

    Each sub-step moves at most the requested step length, so the speed never grows.
    """
    n = max(1, int(max(abs(dx), abs(dy)) / _STEP) + 1)
    sx, sy = dx / n, dy / n
    for _ in range(n):
        moved = False
        if sx:
            if not blocked(x + sx, y):
                x += sx
                moved = True
        if sy:
            if not blocked(x, y + sy):
                y += sy
                moved = True
        if moved:
            continue
        if sx and not sy:
            side = _side_opening(x, y, sx, 0)
            if side and not blocked(x, y + side * abs(sx)):
                y += side * abs(sx)
        elif sy and not sx:
            side = _side_opening(x, y, 0, sy)
            if side and not blocked(x + side * abs(sy), y):
                x += side * abs(sy)
    return x, y


def room_at(x, y):
    """The room dict containing (x, y), or None in a corridor."""
    for room in ROOMS:
        rx, ry, rw, rh = room["rect"]
        if rx <= x <= rx + rw and ry <= y <= ry + rh:
            return room
    return None


def room_by_id(rid):
    for room in ROOMS:
        if room["id"] == rid:
            return room
    return None


def terminal_by_id(tid):
    for t in TERMINALS:
        if t["id"] == tid:
            return t
    return None


def payload():
    """Map description sent inside GAME_STARTED (the wall grid ships with both sides)."""
    return {"width": W, "height": H, "cell": CELL, "cols": COLS, "rows": ROWS,
            "rooms": [{"id": r["id"], "name": r["name"], "rect": list(r["rect"])} for r in ROOMS]}


def _reachable(tx, ty, radius):
    """Is there floor close enough to press E at this terminal?"""
    n = int(radius // CELL)
    cx, cy = int(tx // CELL), int(ty // CELL)
    for j in range(-n, n + 1):
        for i in range(-n, n + 1):
            if i * i + j * j <= n * n and walkable_cell(cx + i, cy + j):
                return True
    return False


# Sanity check at import: spawns stand on floor, every terminal can be used.
for _sx, _sy in SPAWNS:
    assert not blocked(_sx, _sy), f"spawn {(_sx, _sy)} is inside a wall"
for _t in TERMINALS:
    assert _reachable(_t["x"], _t["y"], config.INTERACT_RADIUS * 0.6), f"terminal {_t['id']} is out of reach"
