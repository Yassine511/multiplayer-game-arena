"""Build the collision grid for the station map.

    python tools/build_map.py [--debug DIR]

Reads client/assets/map.png, finds the floor (everything that is neither the
dark hull grid nor open space), removes the furniture / back walls listed in
OBSTACLES and writes common/map_grid.py, which server and client both import.
Needs Pillow, numpy and scipy (only to rebuild; the game itself does not).
"""
import base64
import os
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from common import config  # noqa: E402

MAP_PNG = os.path.join(ROOT, "client", "assets", "map.png")
OUT = os.path.join(ROOT, "common", "map_grid.py")

CELL = 2                       # world units per grid cell
HULL_MIN = 7                   # px; hull-coloured specks thinner than 2x this are floor
HULL_MIN_AREA = 9000           # px; smaller dark blobs are furniture
FOOT_RADIUS = 4.5              # world units; the grid is pre-shrunk by this much

# Everything below is in map.png pixels (2669 x 1498).
STATION = (385, 150, 2500, 1265)      # hull interior
GREENHOUSE = (55, 500, 420, 960)      # the one room that sticks out of the hull
SEED = (1368, 700)                    # a floor pixel in the plaza

# name -> (x0, y0, x1, y1) view box, used for --debug crops only
ROOMS = {
    "greenhouse": (40, 480, 440, 980), "engine": (390, 150, 730, 520),
    "electronics": (690, 290, 1100, 850), "plaza": (1070, 220, 1670, 820),
    "command": (1620, 170, 2260, 500), "auditorium": (1900, 540, 2510, 830),
    "reactor": (590, 820, 1040, 1170), "hospital": (1090, 780, 1480, 1240),
    "laboratory": (1520, 670, 1920, 1230), "classroom": (1990, 800, 2500, 1290),
    "corridors_w": (350, 480, 850, 1280),
}

# Rectangles (x0, y0, x1, y1) nobody can walk through: back walls and furniture.
OBSTACLES = [
    # greenhouse
    (55, 500, 420, 640), (130, 625, 295, 752), (85, 675, 125, 735), (302, 700, 385, 752),
    (85, 745, 125, 865), (140, 842, 250, 888), (90, 872, 125, 915), (290, 858, 320, 890),
    # engine room: only the strip in front of the machines and the stairs are floor
    (400, 150, 632, 422), (632, 150, 720, 300),
    # electronics lab
    (700, 300, 1085, 410), (805, 410, 1060, 475), (750, 390, 798, 485),
    (825, 515, 960, 655), (858, 725, 950, 810),
    # command lounge: desk, then each armchair, table and the sofa on their own
    (1790, 180, 2100, 262), (1885, 255, 2095, 318), (1830, 240, 1868, 305), (2100, 250, 2230, 300),
    (2102, 300, 2154, 340), (2178, 318, 2203, 336), (2104, 368, 2152, 393), (2182, 352, 2222, 452),
    (2100, 430, 2154, 470), (1863, 405, 1935, 462),
    # auditorium: back wall, flags, whiteboard, podium and the front desk (rows are POLYGONS)
    (2060, 545, 2500, 646), (2072, 712, 2102, 732), (2150, 695, 2188, 730), (2165, 755, 2340, 786),
    # reactor
    (600, 830, 1020, 912), (620, 880, 655, 1110), (900, 880, 1010, 960), (975, 960, 1010, 1150),
    (920, 1085, 1010, 1140),
    # hospital
    (1190, 980, 1240, 1070), (1328, 980, 1378, 1070), (1150, 985, 1190, 1045), (1380, 985, 1420, 1045),
    (1152, 1092, 1260, 1145), (1318, 1115, 1380, 1165), (1380, 1095, 1435, 1180),
    # laboratory
    (1540, 680, 1900, 800), (1610, 800, 1825, 848), (1820, 780, 1862, 842), (1555, 750, 1615, 950),
    (1558, 1105, 1725, 1180),
    # classroom (the gap in the back wall is the door from the corridor): two tables with
    # their chairs, the whiteboard, the lectern and its chair - the floor around them is open
    (2020, 930, 2335, 1028), (2400, 930, 2480, 1028), (2122, 1050, 2266, 1100), (2100, 1135, 2272, 1210),
    (2042, 1060, 2090, 1140), (2350, 1095, 2400, 1165), (2400, 1100, 2437, 1150),
]
# Polygons [(x, y), ...]: the curved auditorium desk rows.
POLYGONS = [
    [(2247, 647), (2290, 642), (2365, 652), (2420, 667), (2455, 690), (2455, 714), (2435, 716),
     (2410, 694), (2360, 676), (2290, 664), (2247, 660)],
    [(2195, 680), (2300, 690), (2365, 707), (2402, 731), (2398, 745), (2360, 733), (2290, 715), (2195, 705)],
]
# Circles (cx, cy, r): plaza tables and the reactor core.
CIRCLES = [(1245, 385, 52), (1495, 385, 52), (1245, 635, 52), (1495, 638, 52), (815, 1005, 72)]
# The plaza wall: a ring (cx, cy, r_inner, r_outer) with rectangular door gaps.
RING = (1370, 512, 256, 292)
# Rectangles forced walkable afterwards (doorways).
OPEN = [(1070, 478, 1130, 545), (1610, 475, 1670, 548), (1340, 755, 1400, 812), (2010, 664, 2112, 716), (425, 436, 700, 462), (530, 440, 590, 500)]


def classify(rgb):
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    navy = (r < 56) & (g < 64) & (b > 40) & (b < 112) & (b > r + 16)
    slate = (r > 44) & (r < 92) & (g > 52) & (g < 100) & (b > 88) & (b < 136) & (b > r + 24) & (abs(g - r) < 24)
    space = (g < 48) & (b > 56) & (r < 96) & (b > g + 40)
    return ~(navy | slate | space)


def audit(floor, reach, rad, min_area=900):
    """Report floor that a player can neither stand on nor touch: walkable-looking pockets
    cut off by a too-narrow gap, or areas missing because an obstacle box is too big."""
    touched = ndi.distance_transform_edt(~reach) <= rad + 1.5      # floor some player's body covers
    lost = floor & ~touched
    lab, n = ndi.label(lost)
    found = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        area = int((lab[sl] == i).sum())
        if area >= min_area:
            found.append((area, sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
    found.sort(reverse=True)
    print(f"audit: {len(found)} unreachable floor pockets >= {min_area} px")
    for area, x0, y0, x1, y1 in found:
        print(f"  {area:7d} px  box ({x0}, {y0}, {x1}, {y1})")
    return found


def build(debug_dir=None):
    img = Image.open(MAP_PNG).convert("RGB")
    rgb = np.asarray(img)
    h, w = rgb.shape[:2]
    hull = ~classify(rgb)
    hull = ndi.binary_closing(hull, iterations=2)            # rivets and stars are hull too
    hull = ndi.binary_opening(hull, iterations=HULL_MIN)     # dark outlines and chair legs are not
    lab, n = ndi.label(hull)
    sizes = ndi.sum(hull, lab, range(1, n + 1))
    hull = np.isin(lab, 1 + np.flatnonzero(sizes >= HULL_MIN_AREA))   # dark furniture is not hull
    floor = ~hull
    region = np.zeros_like(floor)
    for x0, y0, x1, y1 in (STATION, GREENHOUSE):
        region[y0:y1, x0:x1] = True
    floor &= region
    for x0, y0, x1, y1 in OBSTACLES:
        floor[y0:y1, x0:x1] = False
    mask = Image.new("1", (w, h), 0)
    for poly in POLYGONS:
        ImageDraw.Draw(mask).polygon(poly, fill=1)
    floor &= ~np.asarray(mask, dtype=bool)
    yy, xx = np.ogrid[:h, :w]
    for cx, cy, r in CIRCLES:
        floor[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = False
    cx, cy, r0, r1 = RING
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    floor[(d2 >= r0 * r0) & (d2 <= r1 * r1)] = False
    for x0, y0, x1, y1 in OPEN:
        floor[y0:y1, x0:x1] = True

    sx, sy = w / config.WORLD_W, h / config.WORLD_H          # map px per world unit
    # shrink by the player's foot radius so the game only tests one cell
    rad = FOOT_RADIUS * (sx + sy) / 2
    dist = ndi.distance_transform_edt(floor)
    centre_ok = dist > rad
    lab, _ = ndi.label(centre_ok)
    centre_ok = lab == lab[SEED[1], SEED[0]]                 # only what the plaza can reach
    audit(floor, centre_ok, rad)

    gw, gh = config.WORLD_W // CELL, config.WORLD_H // CELL
    gx = ((np.arange(gw) + 0.5) * CELL * sx).astype(int).clip(0, w - 1)
    gy = ((np.arange(gh) + 0.5) * CELL * sy).astype(int).clip(0, h - 1)
    grid = centre_ok[np.ix_(gy, gx)]
    # Sampling leaves 1-cell bumps along the wall edges that snag a player sliding along
    # them. A 3x3 closing fills those; walls and furniture are far thicker, so no gap opens.
    grid = ndi.binary_closing(grid, structure=np.ones((3, 3), bool), border_value=0) | grid
    lab, _ = ndi.label(grid)
    seed = lab[int(SEED[1] / sy / CELL), int(SEED[0] / sx / CELL)]
    grid = lab == seed
    packed = np.packbits(grid, axis=None).tobytes()
    blob = base64.b64encode(zlib.compress(packed, 9)).decode()
    with open(OUT, "w", newline="\n") as f:
        f.write('"""Walkable-cell grid for the station map. Generated by tools/build_map.py - do not edit."""\n')
        f.write(f"CELL = {CELL}\nCOLS = {gw}\nROWS = {gh}\n")
        f.write('DATA = (\n')
        for i in range(0, len(blob), 100):
            f.write(f'    "{blob[i:i + 100]}"\n')
        f.write(')\n')
    print(f"wrote {OUT}: {gw}x{gh} cells, {int(grid.sum())} walkable, {len(blob)} chars")

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        vis = rgb.astype(float)
        vis[~centre_ok] = vis[~centre_ok] * 0.35 + np.array([255, 0, 0]) * 0.45
        out = Image.fromarray(vis.astype("uint8"))
        out.resize((w // 2, h // 2)).save(os.path.join(debug_dir, "walk_all.png"))
        d = ImageDraw.Draw(out)
        for x in range(0, w, 50):
            d.line([(x, 0), (x, h)], fill=(255, 255, 0) if x % 100 == 0 else (255, 255, 255, 90), width=1)
        for y in range(0, h, 50):
            d.line([(0, y), (w, y)], fill=(255, 255, 0) if y % 100 == 0 else (255, 255, 255, 90), width=1)
        for x in range(0, w, 100):
            for y in range(0, h, 200):
                d.text((x + 2, y + 1), f"{x},{y}", fill=(255, 255, 0))
        for name, box in ROOMS.items():
            out.crop(box).save(os.path.join(debug_dir, f"walk_{name}.png"))


if __name__ == "__main__":
    dbg = sys.argv[sys.argv.index("--debug") + 1] if "--debug" in sys.argv else None
    build(dbg)
