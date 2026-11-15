"""First screen of the single executable: host the server on this PC, or join one."""
import math

import pygame

from common import config
from client import ui
from client.screens.base import CANVAS_H, CANVAS_W, Screen

ADDRESS_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:_"


class LaunchScreen(Screen):
    backdrop = "login"

    def __init__(self, app, notice=None):
        super().__init__(app)
        cx = CANVAS_W // 2
        self.host_box = pygame.Rect(cx - 520, 270, 500, 330)
        self.join_box = pygame.Rect(cx + 20, 270, 500, 330)
        hx, hw = self.host_box.x + 36, self.host_box.w - 72
        self.btn_host = ui.Button((hx, self.host_box.bottom - 98, hw, 56), "HOST ON THIS PC", self.host,
                                  color=ui.BTN_GO, size=20)
        jx, jw = self.join_box.x + 36, self.join_box.w - 72
        self.addr = ui.TextInput((jx, self.join_box.y + 150, jw, 46), "e.g. 192.168.1.20", max_len=40,
                                 allowed=ADDRESS_CHARS, label="SERVER ADDRESS")
        self.addr.value = str(app.prefs.get("server") or "")
        if self.addr.value in ("127.0.0.1", "localhost"):
            self.addr.value = ""
        self.addr.focused = True
        self.btn_join = ui.Button((jx, self.join_box.bottom - 98, jw, 56), "CONNECT", self.join, size=20)
        if notice:
            self.toasts.add(notice, ui.WARN, 4)

    def host(self):
        from client.screens.login import LoginScreen
        notice = self.app.host_server()
        self.app.set_screen(LoginScreen(self.app, notice))

    def join(self):
        from client.screens.login import LoginScreen
        host = self.addr.value.strip()
        if not host:
            self.toasts.add("Type the host's IP address (shown on the host's screen)", ui.WARN)
            return
        self.app.connect(host)
        self.app.set_screen(LoginScreen(self.app))

    def handle_event(self, e):
        self.addr.handle(e)
        self.btn_host.handle(e)
        self.btn_join.handle(e)
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.join()

    def draw(self, surf):
        cx = CANVAS_W // 2
        t = pygame.time.get_ticks() / 1000
        ty = 70 + int(math.sin(t * 1.3) * 4)
        ui.text(surf, "ULTIMATE SLOP SHOWDOWN", (cx + 5, ty + 6), 84, ui.INK, bold=True, anchor="midtop", shadow=False)
        ui.text(surf, "ULTIMATE SLOP SHOWDOWN", (cx, ty), 84, ui.ICE, bold=True, anchor="midtop")
        sub = "MEDITERRANEAN UNIVERSITY STATION"
        w = ui.text_width(sub, 16, True) + 40
        tag = pygame.Rect(0, 0, w, 34)
        tag.midtop = (cx, 186)
        ui.plate(surf, tag, ui.INK, 190, 4)
        ui.text(surf, sub, (tag.centerx, tag.centery), 16, ui.CYAN, bold=True, anchor="center")

        hb = self.host_box
        ui.panel(surf, hb, ui.PANEL, 18, ui.GOOD, 238)
        ui.heading(surf, "HOST THE SERVER", (hb.x + 36, hb.y + 18), hb.w - 72, ui.GOOD, 14)
        lines = ["Runs the game server inside this window.",
                 "Then log in, create a room and pick the questions.",
                 f"Others join with your IP. Ports TCP {config.TCP_PORT} / UDP {config.UDP_PORT}."]
        y = hb.y + 62
        for line in lines:
            for part in ui.wrap(line, 16, hb.w - 72):
                ui.text(surf, part, (hb.x + 36, y), 16, ui.ICE)
                y += 26
            y += 6
        self.btn_host.draw(surf)

        jb = self.join_box
        ui.panel(surf, jb, ui.PANEL, 18, ui.CYAN, 238)
        ui.heading(surf, "JOIN A SERVER", (jb.x + 36, jb.y + 18), jb.w - 72, ui.CYAN, 14)
        for i, part in enumerate(ui.wrap("Type the address shown on the host's login screen "
                                         "(LAN IP or Tailscale 100.x).", 16, jb.w - 72)):
            ui.text(surf, part, (jb.x + 36, jb.y + 62 + i * 26), 16, ui.ICE)
        self.addr.draw(surf)
        self.btn_join.draw(surf)
        ui.text(surf, "OR PRESS ENTER", (jb.centerx, self.btn_join.rect.bottom + 10), 12, ui.MUTED, bold=True,
                anchor="midtop")
        ui.text(surf, "F11 FULLSCREEN", (cx, CANVAS_H - 30), 12, ui.MUTED, bold=True, anchor="midtop")
        self.draw_toasts(surf)
