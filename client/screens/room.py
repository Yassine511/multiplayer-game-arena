import pygame

from common import protocol as P
from client import ui
from client.assets import color_of
from client.qr import make_qr_surface
from client.screens.base import CANVAS_W, Screen


class RoomScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.btn_start = ui.Button((60, 600, 260, 56), "Start game", self.start, color=(50, 160, 90), size=24)
        self.btn_leave = ui.Button((340, 600, 200, 56), "Leave", self.leave, color=(110, 60, 70), size=24)
        self._qr_for = None
        self._qr = None

    def start(self):
        self.app.net.send(P.msg(P.START_GAME))

    def leave(self):
        from client.screens.lobby import LobbyScreen
        self.app.net.send(P.msg(P.LEAVE_ROOM))
        self.app.room = None
        self.app.set_screen(LobbyScreen(self.app))

    def _is_host(self):
        room, me = self.app.room, self.app.me
        return bool(room and me and room["host"] == me["player_id"])

    def handle_event(self, e):
        if self._is_host():
            self.btn_start.handle(e)
        self.btn_leave.handle(e)

    def handle_msg(self, m):
        t = m["type"]
        if t == P.GAME_COUNTDOWN:
            self.app.set_screen(self.app.make_game_screen(countdown=m["seconds"]))
        elif t == P.GAME_STARTED:
            self.app.set_screen(self.app.make_game_screen(state=m))
        else:
            super().handle_msg(m)

    def qr_surface(self, data):
        if data != self._qr_for:
            self._qr_for = data
            self._qr = make_qr_surface(data, 230)
        return self._qr

    def draw(self, surf):
        room = self.app.room
        if room is None:
            ui.text(surf, "Joining room...", (CANVAS_W // 2, 360), 30, ui.MUTED, anchor="center")
            return
        ui.text(surf, "Room code", (60, 40), 22, ui.MUTED)
        ui.text(surf, room["code"], (60, 66), 84, ui.ACCENT, bold=True)
        ui.text(surf, f"Host: {room['host_name']}", (60, 170), 22)
        n = len([p for p in room["players"] if p["status"] == "connected"])
        need = room.get("min", 3)
        col = ui.GOOD if n >= need else ui.WARN
        ui.text(surf, f"{n}/{room['max']} players  -  at least {need} to start", (60, 200), 22, col)

        # roster
        box = pygame.Rect(60, 250, 520, 330)
        ui.panel(surf, box)
        ui.text(surf, "Players", (80, 262), 22, bold=True)
        y = 300
        for p in room["players"]:
            c = color_of(p["color"])
            pygame.draw.circle(surf, c, (95, y + 13), 10)
            me = self.app.me and p["id"] == self.app.me["player_id"]
            name = p["name"] + ("  (you)" if me else "") + ("  [host]" if p["id"] == room["host"] else "")
            ui.text(surf, name, (115, y + 13), 21, ui.TEXT if p["status"] == "connected" else ui.MUTED,
                    bold=bool(me), anchor="midleft")
            y += 32
        if room.get("spectators"):
            ui.text(surf, f"{room['spectators']} spectator(s) watching", (80, box.bottom - 30), 18, ui.MUTED)

        if self._is_host():
            self.btn_start.draw(surf)
        else:
            ui.text(surf, "Waiting for the host to start...", (60, 628), 22, ui.MUTED, anchor="midleft")
            self.btn_leave.rect.x = 420
        self.btn_leave.draw(surf)

        # join info + QR (the QR encodes the same join info as the code)
        jx = 760
        ui.text(surf, "Join info", (jx, 40), 22, ui.MUTED)
        ui.text(surf, room["join_string"], (jx, 70), 22)
        qr = self.qr_surface(room["join_string"])
        if qr is not None:
            frame = qr.get_rect(topleft=(jx, 120)).inflate(16, 16)
            ui.panel(surf, frame, (255, 255, 255), 8, None)
            surf.blit(qr, (jx, 120))
        else:
            ui.text(surf, "(pip install qrcode to show a QR code)", (jx, 120), 18, ui.MUTED)
        steps = ["How to play:",
                 "WASD / arrow keys to move",
                 "E next to a terminal to open its question",
                 "1-4 or click to answer - first correct answer wins +100",
                 "Wrong answer: -20 and 5 s lockout from that terminal",
                 "Highest score after 3 minutes wins"]
        for i, s in enumerate(steps):
            ui.text(surf, s, (jx, 400 + i * 28), 20 if i else 22, ui.MUTED if i else ui.TEXT, bold=(i == 0))
        self.draw_toasts(surf)
