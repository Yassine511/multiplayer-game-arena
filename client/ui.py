"""Tiny pygame UI kit: fonts, colours, text, buttons and text inputs."""
import pygame

BG = (18, 22, 30)
PANEL = (30, 36, 48)
PANEL_HI = (42, 50, 66)
BORDER = (70, 80, 100)
TEXT = (230, 234, 240)
MUTED = (140, 150, 168)
ACCENT = (80, 160, 255)
GOOD = (80, 200, 120)
BAD = (235, 90, 90)
WARN = (240, 190, 70)

_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("segoeui,arial,helvetica", size, bold=bold)
    return _fonts[key]


def text(surf, s, pos, size=20, color=TEXT, bold=False, anchor="topleft"):
    img = font(size, bold).render(str(s), True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def wrap(s, size, width, bold=False):
    f = font(size, bold)
    lines, line = [], ""
    for word in str(s).split():
        trial = (line + " " + word).strip()
        if f.size(trial)[0] <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def panel(surf, rect, color=PANEL, radius=10, border=BORDER):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, 1, border_radius=radius)


class Button:
    def __init__(self, rect, label, on_click, color=ACCENT, size=20, enabled=True):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.color = color
        self.size = size
        self.enabled = enabled
        self.hover = False

    def handle(self, e):
        if e.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.enabled:
            if self.rect.collidepoint(e.pos):
                self.on_click()
                return True
        return False

    def draw(self, surf):
        if not self.enabled:
            c = (60, 66, 80)
        elif self.hover:
            c = tuple(min(255, v + 30) for v in self.color)
        else:
            c = self.color
        pygame.draw.rect(surf, c, self.rect, border_radius=8)
        text(surf, self.label, self.rect.center, self.size, TEXT if self.enabled else MUTED,
             bold=True, anchor="center")


class TextInput:
    def __init__(self, rect, placeholder="", secret=False, max_len=32, allowed=None):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.secret = secret
        self.max_len = max_len
        self.allowed = allowed
        self.value = ""
        self.focused = False

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.focused = self.rect.collidepoint(e.pos)
            return self.focused
        if e.type == pygame.KEYDOWN and self.focused:
            if e.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
                return True
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB, pygame.K_ESCAPE):
                return False
            ch = e.unicode
            if ch and ch.isprintable() and len(self.value) < self.max_len:
                if self.allowed is None or ch in self.allowed:
                    self.value += ch
                return True
        return False

    def draw(self, surf):
        panel(surf, self.rect, PANEL_HI if self.focused else PANEL, 6, ACCENT if self.focused else BORDER)
        shown = ("*" * len(self.value)) if self.secret else self.value
        if shown:
            r = text(surf, shown, (self.rect.x + 10, self.rect.centery), 22, anchor="midleft")
        else:
            r = text(surf, self.placeholder, (self.rect.x + 10, self.rect.centery), 22, MUTED, anchor="midleft")
            r.width = 0
        if self.focused and (pygame.time.get_ticks() // 500) % 2 == 0:
            x = self.rect.x + 10 + (r.width if shown else 0) + 2
            pygame.draw.line(surf, TEXT, (x, self.rect.y + 9), (x, self.rect.bottom - 9), 2)


class Toasts:
    """Short messages that fade after a few seconds."""

    def __init__(self):
        self.items = []

    def add(self, msg, color=TEXT, seconds=3.0):
        self.items.append([msg, color, seconds])
        self.items = self.items[-4:]

    def update(self, dt):
        for it in self.items:
            it[2] -= dt
        self.items = [it for it in self.items if it[2] > 0]

    def draw(self, surf, center_x, y):
        for msg, color, _ in self.items:
            img = font(22, True).render(msg, True, color)
            r = img.get_rect(midtop=(center_x, y))
            bg = r.inflate(24, 12)
            panel(surf, bg, (20, 24, 32), 8, color)
            surf.blit(img, r)
            y += bg.height + 6
