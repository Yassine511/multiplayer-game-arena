from client import ui

CANVAS_W, CANVAS_H = 1280, 720


class Screen:
    backdrop = None          # name of the painting behind this screen (assets bg_<name>.jpg)

    def __init__(self, app):
        self.app = app
        self.toasts = ui.Toasts()

    def handle_event(self, e):
        pass

    def handle_msg(self, m):
        if m["type"] == "ERROR":
            self.toasts.add(m.get("message", "Error"), ui.BAD)

    def update(self, dt):
        self.toasts.update(dt)

    def draw(self, surf):
        pass

    def draw_toasts(self, surf, center_x=CANVAS_W // 2, y=16):
        self.toasts.draw(surf, center_x, y)
