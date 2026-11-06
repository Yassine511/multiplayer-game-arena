import pygame

from common import config
from common import protocol as P
from client import ui
from client.screens.base import CANVAS_W, Screen


class LoginScreen(Screen):
    def __init__(self, app, notice=None):
        super().__init__(app)
        cx = CANVAS_W // 2
        self.user = ui.TextInput((cx - 170, 270, 340, 48), "username", max_len=16)
        self.pw = ui.TextInput((cx - 170, 330, 340, 48), "password", secret=True, max_len=64)
        self.user.focused = True
        if app.admin_mode:
            self.user.value = config.ADMIN_USERNAME
            self.user.focused, self.pw.focused = False, True
        self.btn_login = ui.Button((cx - 170, 400, 165, 48), "Log in", self.login)
        self.btn_register = ui.Button((cx + 5, 400, 165, 48), "Register", self.register, color=(70, 90, 120))
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
        ui.text(surf, "Multiplayer Game Arena", (cx, 120), 52, ui.TEXT, bold=True, anchor="center")
        ui.text(surf, "Race to the terminals. Answer networking questions. Be first.",
                (cx, 172), 22, ui.MUTED, anchor="center")
        if self.app.admin_mode:
            ui.text(surf, "ADMIN CLIENT", (cx, 215), 20, ui.WARN, bold=True, anchor="center")
        for w in (self.user, self.pw):
            w.draw(surf)
        self.btn_login.draw(surf)
        self.btn_register.draw(surf)
        if self.status:
            ui.text(surf, self.status, (cx, 480), 20, self.status_color, anchor="center")
        net = self.app.net
        state = ("connected" if self.app.connected else "connecting...")
        ui.text(surf, f"Server {net.host}:{net.tcp_port}  -  {state}", (cx, 680), 18,
                ui.GOOD if self.app.connected else ui.WARN, anchor="center")
        self.draw_toasts(surf)
