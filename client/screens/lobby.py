import pygame

from common import protocol as P
from client import ui
from client.screens.base import CANVAS_W, Screen


class LobbyScreen(Screen):
    def __init__(self, app, notice=None):
        super().__init__(app)
        self.rooms = []
        self.refresh_in = 0.0
        self.row_rects = []
        self.is_admin = app.is_admin
        self.code = ui.TextInput((880, 170, 220, 48), "6-digit code", max_len=6, allowed="0123456789")
        label = "Spectate" if self.is_admin else "Join"
        self.btn_join = ui.Button((1110, 170, 150, 48), label, self.join_code)
        self.btn_create = ui.Button((880, 250, 380, 52), "Create room", self.create)
        self.btn_logout = ui.Button((880, 620, 380, 44), "Log out", self.logout, color=(110, 60, 70))
        if notice:
            self.toasts.add(notice, ui.WARN, 4)

    def create(self):
        self.app.net.send(P.msg(P.CREATE_ROOM))

    def join(self, code):
        t = P.SPECTATE_ROOM if self.is_admin else P.JOIN_ROOM
        self.app.net.send(P.msg(t, code=code))

    def join_code(self):
        if len(self.code.value) == 6:
            self.join(self.code.value)
        else:
            self.toasts.add("Room codes have 6 digits", ui.WARN)

    def logout(self):
        self.app.net.send(P.msg(P.LOGOUT))

    def handle_event(self, e):
        self.code.handle(e)
        for b in (self.btn_join, self.btn_create, self.btn_logout):
            b.handle(e)
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.code.focused:
            self.join_code()
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, room in self.row_rects:
                if rect.collidepoint(e.pos):
                    self.join(room["code"])

    def handle_msg(self, m):
        from client.screens.room import RoomScreen
        t = m["type"]
        if t == P.ROOM_LIST:
            self.rooms = m["rooms"]
        elif t == P.ROOM_CREATED:
            self.app.room = None             # the ROOM_UPDATE right behind fills it
            self.app.set_screen(RoomScreen(self.app))
        elif t == P.ROOM_JOINED:
            self.app.room = m["room"]
            self.app.set_screen(RoomScreen(self.app))
        else:
            super().handle_msg(m)

    def update(self, dt):
        super().update(dt)
        self.refresh_in -= dt
        if self.refresh_in <= 0:
            self.refresh_in = 2.0
            self.app.net.send(P.msg(P.LIST_ROOMS))

    def draw(self, surf):
        me = self.app.me or {}
        ui.text(surf, "Lobby", (60, 50), 44, bold=True)
        role = "admin (spectator)" if self.is_admin else "player"
        ui.text(surf, f"Logged in as {me.get('username', '?')} - {role}", (60, 105), 20, ui.MUTED)

        # room list
        box = pygame.Rect(60, 150, 760, 520)
        ui.panel(surf, box)
        ui.text(surf, "Open rooms", (80, 165), 24, bold=True)
        ui.text(surf, "click a room to " + ("spectate" if self.is_admin else "join"), (800, 172), 16,
                ui.MUTED, anchor="topright")
        self.row_rects = []
        y = 210
        if not self.rooms:
            ui.text(surf, "No rooms yet. Create one!", (box.centerx, box.centery), 22, ui.MUTED, anchor="center")
        for r in self.rooms[:10]:
            row = pygame.Rect(75, y, 730, 42)
            hover = row.collidepoint(self.app.mouse_pos)
            ui.panel(surf, row, ui.PANEL_HI if hover else (36, 42, 56), 6, None)
            ui.text(surf, r["code"], (90, row.centery), 24, ui.ACCENT, bold=True, anchor="midleft")
            ui.text(surf, f"host: {r['host']}", (230, row.centery), 20, anchor="midleft")
            ui.text(surf, f"{r['players']}/{r['max']} players", (480, row.centery), 20, anchor="midleft")
            col = ui.GOOD if r["status"] == "waiting" else ui.WARN
            ui.text(surf, r["status"], (790, row.centery), 20, col, anchor="midright")
            self.row_rects.append((row, r))
            y += 48

        ui.text(surf, "Join with a code" if not self.is_admin else "Spectate a room", (880, 135), 20, ui.MUTED)
        self.code.draw(surf)
        for b in (self.btn_join, self.btn_create, self.btn_logout):
            b.draw(surf)
        hint = ("You create rooms as host-spectator: share the code / QR, then press Start."
                if self.is_admin else "Create a room to host it, or join a friend's room with its code.")
        for i, line in enumerate(ui.wrap(hint, 18, 380)):
            ui.text(surf, line, (880, 320 + i * 24), 18, ui.MUTED)
        self.draw_toasts(surf, CANVAS_W // 2)
