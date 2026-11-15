"""Copy the art from Map_and_rooms_charac/ into client/assets/ under the names the
client loads. Re-run after the art changes, then run build_map.py.

    python tools/import_art.py
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "Map_and_rooms_charac")
DST = os.path.join(ROOT, "client", "assets")

ROOMS = {
    "plaza": "Mediterranean University Pixel Arena.png",
    "electronics": "Pixel Art Electronics Lab Layout.png",
    "engine": "Isometric Sci-Fi Engine Room Tile.png",
    "greenhouse": "Cozy Pixel Art Greenhouse Workspace.png",
    "reactor": "Futuristic Pixel Lab Reactor Room.png",
    "medbay": "Futuristic Pixel Art Hospital Room.png",
    "laboratory": "Pixel Art Laboratory Room Tile.png",
    "classroom": "Pixel Art Classroom Game Map.png",
    "command": "Cyan Sci-Fi Command Lounge.png",
}
# output name -> (source file, crop box or None); crops drop the letterbox bars
BACKDROPS = {
    "bg_login.jpg": ("login bk.jpg", (0, 0, 1374, 770)),
    "bg_space.jpg": ("bk_1.jpg", None),
    "bg_scene.jpg": ("secen1.jpg", (0, 18, 1376, 768)),
}
AUDITORIUM_BOX = (2040, 545, 2500, 830)      # no separate file: cut it out of the map
ROOM_MAX = 560                                # px, longest side of a room card


def main():
    os.makedirs(os.path.join(DST, "rooms"), exist_ok=True)
    big = Image.open(os.path.join(SRC, "map.png")).convert("RGB")
    big.save(os.path.join(DST, "map.png"), optimize=True)
    for name, fn in ROOMS.items():
        im = Image.open(os.path.join(SRC, fn)).convert("RGBA")
        im = im.crop(im.getbbox())
        im.thumbnail((ROOM_MAX, ROOM_MAX), Image.LANCZOS)
        im.save(os.path.join(DST, "rooms", name + ".png"), optimize=True)
    big.crop(AUDITORIUM_BOX).save(os.path.join(DST, "rooms", "auditorium.png"), optimize=True)
    for out, (fn, box) in BACKDROPS.items():
        im = Image.open(os.path.join(SRC, fn)).convert("RGB")
        if box:
            im = im.crop(box)
        im.save(os.path.join(DST, out), quality=92)
    print("art imported into", DST)


if __name__ == "__main__":
    main()
