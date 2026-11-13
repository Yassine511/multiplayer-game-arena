import pygame

from common import config
from common import protocol as P
from client import ui
from client.screens.base import CANVAS_W, Screen


class LobbyScreen(Screen):
    backdrop = "space"

    def __init__(self, app, notice=None):
        super().__init__(app)
        self.rooms = []
        self.refresh_in = 0.0
        self.row_rects = []
        self.is_admin = app.is_admin
        self.list_box = pygame.Rect(40, 124, 760, 560)
        self.side = pygame.Rect(824, 124, 416, 560)
        sx, sw = self.side.x + 28, self.side.w - 56
        self.code = ui.TextInput((sx, self.side.y + 72, sw - 132, 46), "6 digits", max_len=6,
                                 allowed="0123456789", label="ROOM CODE")
        label = "SPECTATE" if self.is_admin else "JOIN"
        self.btn_join = ui.Button((sx + sw - 122, self.side.y + 70, 122, 50), label, self.join_code, size=16)
        self.btn_create = ui.Button((sx, self.side.y + 148, sw, 56), "CREATE ROOM", self.create,
                                    color=ui.BTN_GO, size=20)
        self.btn_logout = ui.Button((CANVAS_W - 40 - 150, 44, 150, 44), "LOG OUT", self.logout,
                                    color=ui.BTN_DANGER, size=14)
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
        ui.text(surf, "STATION LOBBY", (40, 30), 44, ui.ICE, bold=True)
        role = "ADMIN - SPECTATOR" if self.is_admin else "PLAYER"
        ui.text(surf, f"{str(me.get('username', '?')).upper()}  -  {role}", (44, 88), 14,
                ui.WARN if self.is_admin else ui.CYAN, bold=True)
        self.btn_logout.draw(surf)

        # room list
        box = self.list_box
        ui.panel(surf, box, ui.PANEL, 18, ui.CYAN, 228)
        ui.heading(surf, "OPEN ROOMS", (box.x + 28, box.y + 20), box.w - 56, ui.CYAN, 16)
        cols = (box.x + 44, box.x + 190, box.x + 450, box.right - 44)
        for x, label, anchor in ((cols[0], "CODE", "topleft"), (cols[1], "HOST", "topleft"),
                                 (cols[2], "CREW", "topleft"), (cols[3], "STATUS", "topright")):
            ui.text(surf, label, (x, box.y + 56), 12, ui.MUTED, bold=True, anchor=anchor)
        self.row_rects = []
        y = box.y + 82
        if not self.rooms:
            ui.text(surf, "NO ROOMS YET", (box.centerx, box.centery - 16), 24, ui.MUTED, bold=True, anchor="center")
            ui.text(surf, "Create one and share the code with your crew.", (box.centerx, box.centery + 22), 20,
                    ui.MUTED, anchor="center")
        for r in self.rooms[:9]:
            row = pygame.Rect(box.x + 24, y, box.w - 48, 42)
            hover = row.collidepoint(self.app.mouse_pos)
            ui.panel(surf, row, ui.PANEL_HI if hover else (24, 28, 76), 6,
                     ui.CYAN if hover else ui.TEAL_DK, 255, rivets=False)
            cy = row.centery
            ui.text(surf, r["code"], (cols[0], cy), 20, ui.WARN, bold=True, anchor="midleft")
            ui.text(surf, ui.fit(r["host"], 20, 240), (cols[1], cy), 20, ui.ICE, anchor="midleft")
            ui.text(surf, f"{r['players']} / {r['max']}", (cols[2], cy), 16, ui.ICE, bold=True, anchor="midleft")
            waiting = r["status"] == "waiting"
            ui.text(surf, "OPEN" if waiting else str(r["status"]).upper(), (cols[3], cy), 14,
                    ui.GOOD if waiting else ui.WARN, bold=True, anchor="midright")
            self.row_rects.append((row, r))
            y += 48
        ui.text(surf, "CLICK A ROOM TO " + ("SPECTATE" if self.is_admin else "JOIN"),
                (box.right - 28, box.bottom - 18), 12, ui.MUTED, bold=True, anchor="bottomright")

        # join / create
        side = self.side
        ui.panel(surf, side, ui.PANEL, 18, ui.CYAN, 228)
        ui.heading(surf, "SPECTATE A ROOM" if self.is_admin else "JOIN WITH A CODE",
                   (side.x + 28, side.y + 20), side.w - 56, ui.CYAN, 16)
        self.code.draw(surf)
        self.btn_join.draw(surf)
        self.btn_create.draw(surf)
        hint = ("You host as spectator: share the code or the QR, then press Start."
                if self.is_admin else "Host your own room, or join a friend's with its code.")
        for i, line in enumerate(ui.wrap(hint.upper(), 12, side.w - 56, True)[:2]):
            ui.text(surf, line, (side.x + 28, side.y + 216 + i * 20), 12, ui.MUTED, bold=True)

        # the station
        ui.stitch(surf, side.x + 28, side.right - 28, side.y + 266, ui.TEAL_DK)
        mw = side.w - 56
        mini = self.app.assets.map_surface(mw / config.WORLD_W)
        mr = mini.get_rect(topleft=(side.x + 28, side.y + 284))
        pygame.draw.rect(surf, ui.INK, mr.inflate(8, 8))
        pygame.draw.rect(surf, ui.TEAL_DK, mr.inflate(4, 4))
        surf.blit(mini, mr)
        ui.text(surf, "THE STATION", (side.x + 28, mr.bottom + 12), 14, ui.ICE, bold=True)
        secs = config.GAME_DURATION_S
        length = f"{secs // 60} MIN" if secs % 60 == 0 else f"{secs} S"
        facts = f"10 ROOMS - 10 TERMINALS - {length}"
        ui.text(surf, ui.fit(facts, 12, mw, True), (side.x + 28, mr.bottom + 34), 12, ui.MUTED, bold=True)
        self.draw_toasts(surf, CANVAS_W // 2)
