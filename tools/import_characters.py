"""Bake the ten characters into small game-ready atlases.

    python tools/import_characters.py

Reads the originals in Map_and_rooms_charac/ and writes, for every character in
common/characters.py, client/assets/characters/<slug>.png plus one shared
client/assets/characters/characters.json describing the animations.

Two kinds of source art:
  * Codex pet sheets (Map_and_rooms_charac/characters/*.webp): an 8 x N grid of
    192x208 cells. Row 0 idle, row 1 run right, row 2 run left, row 7 run
    toward the viewer. Empty cells are skipped.
  * Turnaround sheets (front, side facing left, back) on a light background:
    the background and the drop shadow are removed, the three views split.
    They have no walk frames, so the client makes them hop while walking.

Every character is scaled so its idle pose is TARGET_H px tall, cropped to the
union of all its frames (so animations keep their offsets) and anchored on the
feet. Needs `pip install pillow numpy scipy`; playing does not.
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from common.characters import CHARACTERS  # noqa: E402

SRC = os.path.join(ROOT, "Map_and_rooms_charac")
DST = os.path.join(ROOT, "client", "assets", "characters")

TARGET_H = 160            # idle height in the baked atlas (the client scales down from it)
PAD = 2

# slug -> ("pet", sheet file, size factor) or ("turn", image file, size factor)
SOURCES = {
    "gojo": ("turn", "Gemini_Generated_Image_4qptzo4qptzo4qpt.jpg", 1.0),
    "mia": ("turn", "Gemini_Generated_Image_dyi1podyi1podyi1.jpg", 1.0),
    "leo": ("turn", "f279116e-57ea-4ba1-aa42-a62890051bd6.webp", 1.0),
    "mui-goku": ("pet", "characters/mui-goku.webp", 1.0),
    "epstein": ("pet", "characters/epstein.webp", 1.0),
    "sukuna": ("pet", "characters/sukuna.webp", 1.0),
    "claude": ("pet", "characters/clawd-chef.webp", 0.8),
    "palantir-patrick": ("pet", "characters/palantir-patrick.webp", 1.0),
    "sam-altman": ("pet", "characters/mini-sama.webp", 1.0),
    "trump": ("pet", "characters/trump.webp", 1.0),
}

PET_CELL = (192, 208)
PET_ROWS = {"idle": 0, "right": 1, "left": 2, "front": 7}
# sheets with extra rows (Clawd Chef has four cooking rows): where their front walk is
PET_FRONT_ROW = {"clawd-chef.webp": 9}
IDLE_MS, RUN_MS = 150, 85


# --- helpers ---------------------------------------------------------------------------------
def bbox(alpha, thresh=16):
    ys, xs = np.nonzero(alpha > thresh)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def union(boxes):
    boxes = [b for b in boxes if b is not None]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def bake(rows, anchor, idle_box, factor):
    """rows: list of lists of RGBA frames sharing one coordinate frame.
    Returns (atlas image, cell size, anchor in cell px, frame counts)."""
    ub = union([bbox(np.asarray(f)[..., 3]) for row in rows for f in row])
    s = TARGET_H * factor / (idle_box[3] - idle_box[1])
    ax, ay = anchor
    # crop symmetric around the anchor so flipping left/right keeps the feet in place
    half = max(ax - ub[0], ub[2] - ax)
    x0, x1, y0, y1 = ax - half, ax + half, ub[1], max(ub[3], ay)
    cw = int(round((x1 - x0) * s)) + 2 * PAD
    ch = int(round((y1 - y0) * s)) + 2 * PAD
    cols = max(len(r) for r in rows)
    atlas = Image.new("RGBA", (cw * cols, ch * len(rows)), (0, 0, 0, 0))
    for ri, row in enumerate(rows):
        for ci, f in enumerate(row):
            crop = f.crop((int(x0), int(y0), int(x1), int(y1)))
            crop = crop.resize((cw - 2 * PAD, ch - 2 * PAD), Image.LANCZOS)
            a = np.asarray(crop).copy()
            a[..., 3] = np.where(a[..., 3] < 24, 0, a[..., 3])   # no faint halo
            atlas.paste(Image.fromarray(a, "RGBA"), (ci * cw + PAD, ri * ch + PAD))
    anchor_px = (cw // 2, int(round((ay - y0) * s)) + PAD)
    return atlas, (cw, ch), anchor_px, [len(r) for r in rows]


# --- codex pet sheets ------------------------------------------------------------------------
def load_pet(path):
    sheet = Image.open(path).convert("RGBA")
    cw, ch = PET_CELL
    ncols = sheet.width // cw

    def row(r):
        out = []
        for c in range(ncols):
            cell = sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            if bbox(np.asarray(cell)[..., 3]) is not None:
                out.append(cell)
        return out

    front = PET_FRONT_ROW.get(os.path.basename(path), PET_ROWS["front"])
    rows = [row(PET_ROWS["idle"]), row(PET_ROWS["right"]), row(PET_ROWS["left"]), row(front)]
    idle_box = union([bbox(np.asarray(f)[..., 3]) for f in rows[0]])
    anchor = ((idle_box[0] + idle_box[2]) / 2, idle_box[3])
    anims = {}
    for d in ("down", "up", "left", "right"):
        anims[f"idle_{d}"] = [0, IDLE_MS, False]
    anims["walk_right"] = [1, RUN_MS, False]
    anims["walk_left"] = [2, RUN_MS, False]
    anims["walk_down"] = [3, RUN_MS, False]
    anims["walk_up"] = [3, RUN_MS, False]
    return rows, anchor, idle_box, anims, False


# --- turnaround sheets -----------------------------------------------------------------------
def _background(light, radius):
    st = ndimage.generate_binary_structure(2, 1)
    er = ndimage.binary_erosion(light, st, iterations=radius, border_value=1)
    lab, _ = ndimage.label(er)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    seed = np.isin(lab, list(edge))
    return ndimage.binary_dilation(seed, st, iterations=radius + 2) & light


def load_turnaround(path):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(int)
    mx, mn = rgb.max(-1), rgb.min(-1)
    light = (mn > 140) & (mx - mn < 30)                 # paper background and its lavender shadow
    st = ndimage.generate_binary_structure(2, 1)
    light = ~ndimage.binary_opening(~light, st, iterations=2)    # ignore jpeg speckle
    # A wide radius cannot leak through gaps in the outline (white hair), a narrow one
    # also clears the slots between arms and legs: narrow below the shoulders only.
    wide, narrow = _background(light, 7), _background(light, 3)
    fg0 = ~wide
    rows_on = np.nonzero(fg0.any(1))[0]
    split = int(rows_on[0] + 0.45 * (rows_on[-1] - rows_on[0]))
    bg = wide.copy()
    bg[split:] |= narrow[split:]
    fg = ~bg
    lab, n = ndimage.label(fg)
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    fg = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz > 400])
    img = Image.fromarray(np.dstack([rgb, fg * 255]).astype(np.uint8), "RGBA")

    # three views, left to right: front, side (facing left), back
    on = fg.any(0)
    runs, start = [], None
    for x, v in enumerate(on):
        if v and start is None:
            start = x
        elif not v and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, len(on)))
    runs = sorted(sorted(runs, key=lambda r: r[1] - r[0])[-3:])
    if len(runs) != 3:
        raise SystemExit(f"{path}: expected 3 views, found {len(runs)}")

    # put every view on a common canvas, centred on its own feet
    views = []
    for x0, x1 in runs:
        v = img.crop((x0, 0, x1, img.height))
        b = bbox(np.asarray(v)[..., 3])
        views.append(v.crop((b[0], b[1], b[2], b[3])))
    W = max(v.width for v in views) + 8
    H = max(v.height for v in views) + 8
    framed = []
    for v in views:
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        c.paste(v, ((W - v.width) // 2, H - 4 - v.height))
        framed.append(c)
    front, side_left, back = framed
    side_right = side_left.transpose(Image.FLIP_LEFT_RIGHT)
    rows = [[front], [back], [side_left], [side_right]]
    idle_box = bbox(np.asarray(front)[..., 3])
    anchor = (W / 2, H - 4)
    anims = {}
    for i, d in enumerate(("down", "up", "left", "right")):
        anims[f"idle_{d}"] = [i, IDLE_MS, False]
        anims[f"walk_{d}"] = [i, RUN_MS, True]
    return rows, anchor, idle_box, anims, True


def main():
    os.makedirs(DST, exist_ok=True)
    meta = {}
    for ch in CHARACTERS:
        slug = ch["slug"]
        kind, name, factor = SOURCES[slug]
        path = os.path.join(SRC, *name.split("/"))
        rows, anchor, idle_box, anims, hop = (load_pet if kind == "pet" else load_turnaround)(path)
        atlas, cell, anchor_px, counts = bake(rows, anchor, idle_box, factor)
        atlas.save(os.path.join(DST, f"{slug}.png"), optimize=True)
        meta[slug] = {"cell": list(cell), "anchor": list(anchor_px), "frames": counts,
                      "anims": anims, "hop": hop}
        print(f"{slug:18s} {kind:5s} cell {cell[0]}x{cell[1]}  frames {counts}")
    with open(os.path.join(DST, "characters.json"), "w") as f:
        json.dump({"target_h": TARGET_H, "characters": meta}, f, indent=1)
    print("wrote", DST)


if __name__ == "__main__":
    main()
