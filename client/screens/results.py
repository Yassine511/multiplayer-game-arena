import math

import pygame

from common import protocol as P
from client import ui
from client.assets import color_of
from client.screens.base import CANVAS_W, Screen

MEDALS = {1: ui.WARN, 2: (206, 212, 230), 3: (214, 136, 72)}


class ResultsScreen(Screen):
    backdrop = "space"

    def __init__(self, app, game_over):
        super().__init__(app)
        self.board = game_over.get("leaderboard", [])
        self.winner = game_over.get("winner")
        self.box = pygame.Rect(560, 150, 680, 470)
        self.btn_back = ui.Button((self.box.right - 280, 640, 280, 52), "BACK TO ROOM", self.back, size=18)
        self.t0 = pygame.time.get_ticks()

    def back(self):
        from client.screens.lobby import LobbyScreen
        from client.screens.room import RoomScreen
        if self.app.room is not None:
            self.app.set_screen(RoomScreen(self.app))
        else:
            self.app.set_screen(LobbyScreen(self.app))

    def handle_event(self, e):
        self.btn_back.handle(e)
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self.back()

    def handle_msg(self, m):
        if m["type"] == P.GAME_COUNTDOWN:         # host started a rematch
            self.app.set_screen(self.app.make_game_screen(countdown=m["seconds"]))
        else:
            super().handle_msg(m)

    def _podium(self, surf):
        """Top three on hull-plate steps, winner in the middle."""
        assets = self.app.assets
        age = (pygame.time.get_ticks() - self.t0) / 1000
        base_y = 640
        slots = [(2, 150, 96), (1, 290, 150), (3, 430, 64)]          # rank, centre x, step height
        top = [r for r in self.board if r["rank"] <= 3 and r["score"] > 0]
        for rank, cx, h in slots:
            rise = min(1.0, max(0.0, age * 2.2 - (3 - rank) * 0.25))  # third, second, then first
            hh = int(h * rise)
            step = pygame.Rect(cx - 66, base_y - hh, 132, hh + 8)
            ui.panel(surf, step, ui.HULL, 6, MEDALS[rank], 255, rivets=False)
            if hh > 40:
                ui.text(surf, str(rank), (cx, step.y + 16), 30, MEDALS[rank], bold=True, anchor="midtop")
            row = next((r for r in top if r["rank"] == rank), None)
            if row is None or rise < 1.0:
                continue
            hop = abs(math.sin(age * 4.2)) * 10 if rank == 1 else 0
            sprite = assets.player_sprite(row.get("color"), "down", 0, 5 if rank == 1 else 4, row.get("connected", True))
            r = sprite.get_rect(midbottom=(cx, step.y + 6 - int(hop)))
            surf.blit(sprite, r)
            name = ui.fit(row["name"], 14, 136, True)
            tag = pygame.Rect(0, 0, ui.text_width(name, 14, True) + 14, 24)
            tag.midbottom = (cx, r.top - 6)
            ui.plate(surf, tag, ui.INK, 190, 2)
            ui.text(surf, name, (tag.centerx, tag.centery), 14, color_of(row.get("color")),
                    bold=True, anchor="center")
            if rank == 1:                                             # crown
                cy = tag.top - 20
                pts = [(cx - 14, cy + 12), (cx - 14, cy), (cx - 7, cy + 6), (cx, cy - 4), (cx + 7, cy + 6),
                       (cx + 14, cy), (cx + 14, cy + 12)]
                pygame.draw.polygon(surf, ui.INK, [(x, y + 2) for x, y in pts], 0)
                pygame.draw.polygon(surf, ui.WARN, pts)
                pygame.draw.polygon(surf, ui.INK, pts, 2)

    def draw(self, surf):
        ui.text(surf, "TIME IS UP", (40, 30), 44, ui.ICE, bold=True)
        if self.winner:
            ui.text(surf, f"{str(self.winner).upper()} WINS THE STATION", (44, 88), 20, ui.WARN, bold=True)
        else:
            ui.text(surf, "NO POINTS SCORED - THE TERMINALS WIN", (44, 88), 20, ui.MUTED, bold=True)
        self._podium(surf)

        box = self.box
        ui.panel(surf, box, ui.PANEL, 18, ui.CYAN, 232)
        ui.heading(surf, "LEADERBOARD", (box.x + 28, box.y + 20), box.w - 56, ui.CYAN, 16)
        me_id = self.app.me and self.app.me["player_id"]
        y = box.y + 56
        for row in self.board[:10]:
            r = pygame.Rect(box.x + 22, y, box.w - 44, 36)
            on = row.get("connected", True)
            if row["id"] == me_id:
                ui.panel(surf, r, ui.PANEL_HI, 6, ui.CYAN, 255, rivets=False)
            medal = MEDALS.get(row["rank"], ui.MUTED)
            ui.text(surf, f"#{row['rank']}", (r.x + 18, r.centery), 18, medal, bold=True, anchor="midleft")
            ui.chip(surf, color_of(row.get("color")) if on else ui.GREY, (r.x + 84, r.centery), 12)
            name = ui.fit(row["name"], 20, 300) + ("" if on else "  (offline)")
            ui.text(surf, name, (r.x + 104, r.centery), 20, ui.ICE if on else ui.MUTED, anchor="midleft")
            ui.text(surf, str(row["score"]), (r.right - 18, r.centery), 18, ui.ICE, bold=True, anchor="midright")
            y += 40
        self.btn_back.draw(surf)
        ui.text(surf, "ENTER", (self.btn_back.rect.x - 16, self.btn_back.rect.centery), 12, ui.MUTED,
                bold=True, anchor="midright")
        self.draw_toasts(surf)
