"""Art for the map, players and terminals.

Drop image files into client/assets/ and they are used automatically; anything
missing is drawn with simple shapes. Recognised files (PNG with transparency):

  map.png                       full background, scaled to 1280x720
                                (walls must line up with common/map_data.py)
  player_<c>_<dir>.png          player of colour index c (0-9) facing dir
  player_<c>.png                player of colour index c, any direction
  player_<dir>.png              any colour, facing dir (up/down/left/right)
  player.png                    one sprite for everyone
  terminal.png                  terminal, ready to answer
  terminal_cooldown.png         terminal, just claimed (cooling down)
"""
import math
import os

import pygame

from common import config, map_data
from client import ui

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

PALETTE = [
    (66, 135, 245), (235, 87, 87), (76, 196, 120), (245, 190, 60), (168, 102, 230),
    (40, 200, 210), (245, 130, 50), (236, 100, 180), (150, 200, 70), (200, 200, 210),
]
GREY = (110, 114, 124)

PLAYER_SPRITE = 40     # px, drawn centred on the player position
TERMINAL_SPRITE = 46


def color_of(idx):
    return PALETTE[idx % len(PALETTE)] if idx is not None else GREY


class Assets:
    def __init__(self):
        self._cache = {}
        self.map_img = self._load("map.png", (config.WORLD_W, config.WORLD_H))
        self.terminal_img = self._load("terminal.png", (TERMINAL_SPRITE, TERMINAL_SPRITE))
        self.terminal_cd_img = self._load("terminal_cooldown.png", (TERMINAL_SPRITE, TERMINAL_SPRITE))

    def _load(self, name, size=None):
        if name in self._cache:
            return self._cache[name]
        path = os.path.join(ASSET_DIR, name)
        img = None
        if os.path.exists(path):
            try:
                img = pygame.image.load(path).convert_alpha()
                if size:
                    img = pygame.transform.smoothscale(img, size)
            except pygame.error as e:
                print(f"[assets] cannot load {name}: {e}")
        self._cache[name] = img
        return img

    def _player_img(self, color, direction):
        size = (PLAYER_SPRITE, PLAYER_SPRITE)
        for name in (f"player_{color}_{direction}.png", f"player_{color}.png",
                     f"player_{direction}.png", "player.png"):
            img = self._load(name, size)
            if img is not None:
                return img
        return None

    # --- drawing ------------------------------------------------------------------------
    def draw_map(self, surf):
        if self.map_img is not None:
            surf.blit(self.map_img, (0, 0))
            return
        surf.fill((34, 40, 52), pygame.Rect(0, 0, config.WORLD_W, config.WORLD_H))
        for x in range(0, config.WORLD_W, 40):
            pygame.draw.line(surf, (40, 47, 60), (x, 0), (x, config.WORLD_H))
        for y in range(0, config.WORLD_H, 40):
            pygame.draw.line(surf, (40, 47, 60), (0, y), (config.WORLD_W, y))
        for w in map_data.WALLS:
            r = pygame.Rect(w)
            pygame.draw.rect(surf, (78, 88, 108), r)
            pygame.draw.rect(surf, (110, 122, 146), r, 2)

    def draw_terminal(self, surf, t, claimer_color=None, locked_s=0.0, highlight=False):
        x, y = int(t["x"]), int(t["y"])
        cooldown = t["state"] == "cooldown"
        if highlight:
            pygame.draw.circle(surf, (255, 255, 255), (x, y), config.INTERACT_RADIUS, 1)
        img = self.terminal_cd_img if cooldown and self.terminal_cd_img else self.terminal_img
        rect = pygame.Rect(0, 0, TERMINAL_SPRITE, TERMINAL_SPRITE)
        rect.center = (x, y)
        if img is not None:
            surf.blit(img, rect)
            if cooldown and claimer_color:
                pygame.draw.rect(surf, claimer_color, rect.inflate(6, 6), 3, border_radius=8)
        else:
            body = claimer_color if cooldown and claimer_color else (40, 170, 110)
            pygame.draw.rect(surf, (20, 24, 30), rect.inflate(6, 6), border_radius=8)
            pygame.draw.rect(surf, body, rect, border_radius=6)
            screen = rect.inflate(-14, -18)
            pygame.draw.rect(surf, (12, 30, 24) if not cooldown else (30, 30, 30), screen, border_radius=3)
        ui.text(surf, f"T{t['terminal_id']}", (x, rect.top - 4), 16, ui.TEXT, bold=True, anchor="midbottom")
        if cooldown:
            secs = t.get("ready_in", 0)
            ui.text(surf, f"{math.ceil(secs)}s" if secs > 0 else "", (x, rect.bottom + 2), 15, ui.WARN, anchor="midtop")
        elif locked_s > 0:
            ui.text(surf, f"locked {math.ceil(locked_s)}s", (x, rect.bottom + 2), 15, ui.BAD, bold=True, anchor="midtop")

    def draw_player(self, surf, x, y, color_idx, direction, name, me=False, connected=True):
        x, y = int(x), int(y)
        color = color_of(color_idx) if connected else GREY
        img = self._player_img(color_idx, direction)
        if img is not None:
            if not connected:
                img = img.copy()
                img.fill((120, 120, 120, 140), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(img, img.get_rect(center=(x, y)))
        else:
            r = config.PLAYER_RADIUS
            pygame.draw.circle(surf, (15, 18, 24), (x, y + 3), r)
            pygame.draw.circle(surf, color, (x, y), r)
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.get(direction, (0, 1))
            pygame.draw.circle(surf, (255, 255, 255), (x + dx * (r - 5), y + dy * (r - 5)), 4)
        if me:
            pygame.draw.circle(surf, (255, 255, 255), (x, y), config.PLAYER_RADIUS + 4, 2)
        label = name + ("" if connected else " (offline)")
        ui.text(surf, label, (x, y - config.PLAYER_RADIUS - 6), 15,
                ui.TEXT if connected else ui.MUTED, bold=me, anchor="midbottom")
