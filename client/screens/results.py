import pygame

from common import protocol as P
from client import ui
from client.assets import color_of
from client.screens.base import CANVAS_W, Screen


class ResultsScreen(Screen):
    def __init__(self, app, game_over):
        super().__init__(app)
        self.board = game_over.get("leaderboard", [])
        self.winner = game_over.get("winner")
        self.btn_back = ui.Button((CANVAS_W // 2 - 140, 640, 280, 52), "Back to room", self.back)

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

    def draw(self, surf):
        cx = CANVAS_W // 2
        ui.text(surf, "Game over", (cx, 60), 52, bold=True, anchor="center")
        if self.winner:
            ui.text(surf, f"{self.winner} wins!", (cx, 120), 36, ui.WARN, bold=True, anchor="center")
        else:
            ui.text(surf, "No points scored", (cx, 120), 30, ui.MUTED, anchor="center")
        box = pygame.Rect(cx - 330, 170, 660, 450)
        ui.panel(surf, box)
        me_id = self.app.me and self.app.me["player_id"]
        y = 190
        for row in self.board[:10]:
            r = pygame.Rect(box.x + 15, y, box.width - 30, 38)
            if row["id"] == me_id:
                ui.panel(surf, r, ui.PANEL_HI, 6, ui.ACCENT)
            medal = {1: ui.WARN, 2: (200, 200, 210), 3: (205, 127, 50)}.get(row["rank"], ui.MUTED)
            ui.text(surf, f"#{row['rank']}", (r.x + 15, r.centery), 24, medal, bold=True, anchor="midleft")
            pygame.draw.circle(surf, color_of(row.get("color")), (r.x + 85, r.centery), 9)
            name = row["name"] + ("" if row.get("connected", True) else "  (disconnected)")
            ui.text(surf, name, (r.x + 105, r.centery), 22,
                    ui.TEXT if row.get("connected", True) else ui.MUTED, anchor="midleft")
            ui.text(surf, str(row["score"]), (r.right - 15, r.centery), 24, bold=True, anchor="midright")
            y += 43
        self.btn_back.draw(surf)
        self.draw_toasts(surf)
