"""The arena map, shared by server (validation) and client (drawing + prediction).

Coordinates are in world pixels (1280 x 720). Walls are axis-aligned
rectangles (x, y, w, h). If the art teammate supplies client/assets/map.png,
the wall rectangles below must line up with the walls drawn in that image.
"""
from common import config

W, H = config.WORLD_W, config.WORLD_H
B = 16  # border thickness

WALLS = [
    # outer border
    (0, 0, W, B),
    (0, H - B, W, B),
    (0, 0, B, H),
    (W - B, 0, B, H),
    # interior
    (300, 120, 40, 200),
    (940, 120, 40, 200),
    (300, 420, 40, 180),
    (940, 420, 40, 180),
    (520, 300, 240, 30),
    (560, 100, 160, 30),
    (560, 590, 160, 30),
]

# T1..T10, one per location
TERMINALS = [
    {"id": 1, "x": 110, "y": 100},
    {"id": 2, "x": 640, "y": 200},
    {"id": 3, "x": 1170, "y": 100},
    {"id": 4, "x": 110, "y": 360},
    {"id": 5, "x": 440, "y": 360},
    {"id": 6, "x": 840, "y": 360},
    {"id": 7, "x": 1170, "y": 360},
    {"id": 8, "x": 110, "y": 620},
    {"id": 9, "x": 640, "y": 500},
    {"id": 10, "x": 1170, "y": 620},
]

# 10 spawn points, assigned in join order
SPAWNS = [
    (200, 220), (1080, 220), (200, 500), (1080, 500), (640, 255),
    (640, 400), (440, 200), (840, 200), (440, 520), (840, 520),
]


def _circle_hits_rect(cx, cy, r, rect):
    x, y, w, h = rect
    nx = min(max(cx, x), x + w)
    ny = min(max(cy, y), y + h)
    dx, dy = cx - nx, cy - ny
    return dx * dx + dy * dy < r * r


def blocked(x, y, r=config.PLAYER_RADIUS):
    """True if a player circle at (x, y) overlaps a wall or leaves the world."""
    if x - r < 0 or y - r < 0 or x + r > W or y + r > H:
        return True
    return any(_circle_hits_rect(x, y, r, wall) for wall in WALLS)


def move(x, y, dx, dy, r=config.PLAYER_RADIUS):
    """Move with per-axis collision so players slide along walls."""
    if dx and not blocked(x + dx, y, r):
        x += dx
    if dy and not blocked(x, y + dy, r):
        y += dy
    return x, y


def terminal_by_id(tid):
    for t in TERMINALS:
        if t["id"] == tid:
            return t
    return None


def payload():
    """Map description sent inside GAME_STARTED."""
    return {"width": W, "height": H, "walls": [list(w) for w in WALLS]}


# Sanity check at import: nothing important may start inside a wall.
for _sx, _sy in SPAWNS:
    assert not blocked(_sx, _sy), f"spawn {(_sx, _sy)} is inside a wall"
for _t in TERMINALS:
    assert not blocked(_t["x"], _t["y"]), f"terminal {_t['id']} is inside a wall"
