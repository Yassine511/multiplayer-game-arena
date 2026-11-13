import math

import pygame

from common import config
from common import protocol as P
from client import ui
from client.screens.base import CANVAS_H, CANVAS_W, Screen


class LoginScreen(Screen):
    backdrop = "login"

    def __init__(self, app, notice=None):
        super().__init__(app)
        cx = CANVAS_W // 2
        self.box = pygame.Rect(cx - 230, 268, 460, 348)
        fx, fw = self.box.x + 36, self.box.w - 72
        self.user = ui.TextInput((fx, self.box.y + 62, fw, 46), "your call sign", max_len=16, label="USERNAME")
        self.pw = ui.TextInput((fx, self.box.y + 144, fw, 46), "secret", secret=True, max_len=64, label="PASSWORD")
        self.user.focused = True
        if app.admin_mode:
            self.user.value = config.ADMIN_USERNAME
            self.user.focused, self.pw.focused = False, True
        half = (fw - 12) // 2
        self.btn_login = ui.Button((fx, self.box.y + 212, half, 50), "LOG IN", self.login, size=18)
        self.btn_register = ui.Button((fx + half + 12, self.box.y + 212, half, 50), "REGISTER", self.register,
                                      color=ui.BTN_QUIET, size=18)
        self.status = notice
        self.status_color = ui.WARN if notice else ui.MUTED
        self._auto_login = False

    def _creds(self):
        return self.user.value.strip(), self.pw.value

    def _set_status(self, s, color=ui.MUTED):
        self.status, self.status_color = s, color

    def login(self):
        u, p = self._creds()
        if not u or not p:
            self._set_status("Enter a username and a password", ui.WARN)
            return
        if not self.app.net.send(P.msg(P.LOGIN, username=u, password=p)):
            self._set_status("Not connected to the server yet", ui.BAD)
            return
        self._set_status("Logging in...")

    def register(self):
        u, p = self._creds()
        if not u or not p:
            self._set_status("Choose a username and a password", ui.WARN)
            return
        if not self.app.net.send(P.msg(P.REGISTER, username=u, password=p)):
            self._set_status("Not connected to the server yet", ui.BAD)
            return
        self._auto_login = True
        self._set_status("Creating account...")

    def handle_event(self, e):
        for w in (self.user, self.pw):
            w.handle(e)
        self.btn_login.handle(e)
        self.btn_register.handle(e)
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_TAB:
                self.user.focused, self.pw.focused = not self.user.focused, self.user.focused
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.login()

    def handle_msg(self, m):
        t = m["type"]
        if t == P.LOGIN_OK:
            from client.screens.lobby import LobbyScreen
            self.app.on_login(m)
            self.app.set_screen(LobbyScreen(self.app))
        elif t == P.REGISTER_OK:
            self._set_status("Account created - logging in...", ui.GOOD)
            if self._auto_login:
                self._auto_login = False
                self.login()
        elif t == P.ERROR:
            self._auto_login = False
            self._set_status(m.get("message", "Error"), ui.BAD)

    def draw(self, surf):
        cx = CANVAS_W // 2
        t = pygame.time.get_ticks() / 1000

        # title, floating
        ty = 70 + int(math.sin(t * 1.3) * 4)
        ui.text(surf, "GAME ARENA", (cx + 5, ty + 6), 84, ui.INK, bold=True, anchor="midtop", shadow=False)
        ui.text(surf, "GAME ARENA", (cx, ty), 84, ui.ICE, bold=True, anchor="midtop")
        sub = "MEDITERRANEAN UNIVERSITY STATION"
        w = ui.text_width(sub, 16, True) + 40
        tag = pygame.Rect(0, 0, w, 34)
        tag.midtop = (cx, 186)
        ui.plate(surf, tag, ui.INK, 190, 4)
        ui.text(surf, sub, (tag.centerx, tag.centery), 16, ui.CYAN, bold=True, anchor="center")
        ui.text(surf, "Race to the terminals. Answer networking questions. Be first.", (cx, 228), 20,
                ui.ICE, anchor="midtop")

        ui.panel(surf, self.box, ui.PANEL, 18, ui.CYAN, 238)
        admin = self.app.admin_mode
        ui.heading(surf, "ADMIN ACCESS" if admin else "CREW LOGIN", (self.box.x + 36, self.box.y + 16),
                   self.box.w - 72, ui.WARN if admin else ui.CYAN, 14)
        for w in (self.user, self.pw):
            w.draw(surf)
        self.btn_login.draw(surf)
        self.btn_register.draw(surf)
        if self.status:
            for i, line in enumerate(ui.wrap(self.status, 14, self.box.w - 60, True)[:2]):
                ui.text(surf, line, (cx, self.box.y + 282 + i * 20), 14, self.status_color, bold=True, anchor="midtop")
        else:
            ui.text(surf, "TAB switches field  -  ENTER logs in", (cx, self.box.y + 290), 12, ui.MUTED,
                    bold=True, anchor="midtop")

        # server link
        net = self.app.net
        ok = self.app.connected
        label = f"SERVER {net.host}:{net.tcp_port}   {'ONLINE' if ok else 'CONNECTING...'}"
        w = ui.text_width(label, 12, True) + 52
        bar = pygame.Rect(0, 0, w, 32)
        bar.midbottom = (cx, CANVAS_H - 18)
        ui.plate(surf, bar, ui.INK, 200, 4)
        lamp = ui.GOOD if ok else ui.WARN if int(t * 3) % 2 else ui.shade(ui.WARN, 0.5)
        pygame.draw.rect(surf, lamp, (bar.x + 16, bar.centery - 5, 10, 10))
        ui.text(surf, label, (bar.x + 36, bar.centery), 12, ui.ICE if ok else ui.WARN, bold=True, anchor="midleft")
        self.draw_toasts(surf)
