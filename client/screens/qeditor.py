"""Host tools in the room: write questions one by one, or import a CSV file."""
import os

import pygame

from common import config, qcsv
from common import protocol as P
from client import ui
from client.screens.base import CANVAS_H, CANVAS_W

LETTERS = "ABCD"


def bank_count(app):
    q = app.questions or {}
    return len(q.get("questions", []))


def send_questions(app, questions, source, replace=False):
    """Send questions to the server, trimmed to the room's limit. Returns (sent, trimmed)."""
    room_left = config.MAX_QUESTIONS - (0 if replace else bank_count(app))
    trimmed = max(0, len(questions) - room_left)
    questions = questions[:max(0, room_left)]
    if questions:
        app.net.send(P.msg(P.SET_QUESTIONS, action="replace" if replace else "append",
                           questions=questions, source=source))
    return len(questions), trimmed


def import_csv(app, path, replace=False):
    """Read a CSV and send it. Returns (message, colour) for a toast."""
    path = path.strip().strip('"').strip("'")
    if not path:
        return "Type or paste the path of a .csv file", ui.WARN
    try:
        questions, errors = qcsv.load(path)
    except OSError as e:
        return f"Cannot open {os.path.basename(path) or path}: {e.strerror or e}", ui.BAD
    if not questions:
        first = errors[0] if errors else "the file is empty"
        return f"No questions found ({first})", ui.BAD
    sent, trimmed = send_questions(app, questions, os.path.basename(path), replace)
    msg = f"Imported {sent} question{'s' if sent != 1 else ''} from {os.path.basename(path)}"
    if errors:
        msg += f"  -  {len(errors)} row(s) skipped: {errors[0]}"
    if trimmed:
        msg += f"  -  {trimmed} over the {config.MAX_QUESTIONS} limit left out"
    return msg, ui.WARN if errors or trimmed else ui.GOOD


class QuestionEditor:
    """Modal: type a question, four choices, click the right letter, ADD. Repeat."""

    def __init__(self, app, on_close, toasts):
        self.app = app
        self.on_close = on_close
        self.toasts = toasts
        self.box = pygame.Rect(0, 0, 940, 600)
        self.box.center = (CANVAS_W // 2, CANVAS_H // 2)
        x, w = self.box.x + 40, self.box.w - 80
        y = self.box.y + 96
        self.q = ui.TextInput((x, y, w - 250, 46), "What does TCP guarantee?", max_len=config.MAX_QUESTION_TEXT,
                              label="QUESTION")
        self.topic = ui.TextInput((x + w - 230, y, 230, 46), "optional", max_len=config.MAX_TOPIC_TEXT,
                                  label="TOPIC")
        self.choices = []
        self.letter_rects = []
        for i in range(4):
            cy = y + 96 + i * 66
            self.letter_rects.append(pygame.Rect(x, cy, 56, 46))
            self.choices.append(ui.TextInput((x + 70, cy, w - 70, 46), f"choice {LETTERS[i]}",
                                             max_len=config.MAX_CHOICE_TEXT, label=f"CHOICE {LETTERS[i]}" if i == 0 else None))
        self.correct = 0
        self.fields = [self.q, self.topic] + self.choices
        self.q.focused = True
        by = self.box.bottom - 82
        self.btn_add = ui.Button((self.box.right - 40 - 300, by, 300, 54), "ADD QUESTION  (ENTER)", self.add,
                                 color=ui.BTN_GO, size=16)
        self.btn_done = ui.Button((self.box.right - 40 - 300 - 16 - 160, by, 160, 54), "DONE", self.on_close,
                                  color=ui.BTN_QUIET, size=16)
        self.error = None

    def _focus(self, step):
        i = next((k for k, f in enumerate(self.fields) if f.focused), -1)
        for f in self.fields:
            f.focused = False
        self.fields[(i + step) % len(self.fields)].focused = True

    def add(self):
        text = self.q.value.strip()
        choices = [c.value.strip() for c in self.choices]
        if not text:
            self.error = "Write the question first"
            return
        missing = [LETTERS[i] for i, c in enumerate(choices) if not c]
        if missing:
            self.error = f"Fill in choice {', '.join(missing)}"
            return
        if len({c.lower() for c in choices}) < 4:
            self.error = "Two choices are the same"
            return
        if bank_count(self.app) >= config.MAX_QUESTIONS:
            self.error = f"The bank is full ({config.MAX_QUESTIONS} questions)"
            return
        send_questions(self.app, [{"text": text, "choices": choices, "answer": self.correct,
                                   "topic": self.topic.value.strip()}], "written by the host")
        self.toasts.add(f"Added: {ui.fit(text, 18, 640, True)}", ui.GOOD, 2.5)
        self.error = None
        self.q.value = ""
        for c in self.choices:
            c.value = ""
        for f in self.fields:
            f.focused = False
        self.q.focused = True               # topic and the correct letter stay for the next one

    def handle(self, e):
        if self.btn_add.handle(e) or self.btn_done.handle(e):
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.letter_rects):
                if r.collidepoint(e.pos):
                    self.correct = i
                    return
            for f in self.fields:
                f.handle(e)
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.on_close()
                return
            if e.key == pygame.K_TAB:
                self._focus(-1 if e.mod & pygame.KMOD_SHIFT else 1)
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.add()
                return
            if e.key in (pygame.K_UP, pygame.K_DOWN) and any(c.focused for c in self.choices) and e.mod & pygame.KMOD_ALT:
                self.correct = (self.correct + (1 if e.key == pygame.K_DOWN else -1)) % 4
                return
            for f in self.fields:
                f.handle(e)

    def draw(self, surf):
        ui.dim(surf, 175)
        b = self.box
        ui.panel(surf, b, ui.PANEL, 20, ui.CYAN, 250)
        ui.hazard(surf, (b.x + 30, b.y + 26, 40, 22))
        ui.text(surf, "WRITE A QUESTION", (b.x + 84, b.y + 22), 24, ui.CYAN, bold=True)
        ui.text(surf, f"{bank_count(self.app)} / {config.MAX_QUESTIONS} IN THE BANK", (b.right - 40, b.y + 30), 12,
                ui.MUTED, bold=True, anchor="topright")
        for f in self.fields:
            f.draw(surf)
        for i, r in enumerate(self.letter_rects):
            on = i == self.correct
            ui.panel(surf, r, ui.BTN_GO if on else ui.FIELD, 6, ui.GOOD if on else ui.TEAL_DK, 255, rivets=False)
            ui.text(surf, LETTERS[i], r.center, 20, ui.ICE if on else ui.MUTED, bold=True, anchor="center")
        ui.text(surf, "CLICK A LETTER TO MARK THE RIGHT ANSWER  -  TAB NEXT FIELD  -  CTRL+V PASTES",
                (b.x + 40, self.letter_rects[-1].bottom + 18), 12, ui.MUTED, bold=True)
        if self.error:
            ui.text(surf, self.error.upper(), (b.x + 40, self.btn_add.rect.centery), 14, ui.BAD, bold=True,
                    anchor="midleft")
        self.btn_done.draw(surf)
        self.btn_add.draw(surf)


class CsvImport:
    """Modal: a path field (or drop the file on the window), then ADD or REPLACE."""

    def __init__(self, app, on_close, toasts):
        self.app = app
        self.on_close = on_close
        self.toasts = toasts
        self.box = pygame.Rect(0, 0, 900, 470)
        self.box.center = (CANVAS_W // 2, CANVAS_H // 2)
        x, w = self.box.x + 40, self.box.w - 80
        self.path = ui.TextInput((x, self.box.y + 110, w, 46), "C:\\Users\\me\\questions.csv", max_len=400,
                                 label="CSV FILE PATH")
        self.path.focused = True
        by = self.box.bottom - 80
        self.btn_add = ui.Button((self.box.right - 40 - 220, by, 220, 52), "ADD TO BANK", lambda: self.run(False),
                                 color=ui.BTN_GO, size=16)
        self.btn_replace = ui.Button((self.box.right - 40 - 220 - 14 - 220, by, 220, 52), "REPLACE BANK",
                                     lambda: self.run(True), color=ui.BTN_DANGER, size=16)
        self.btn_close = ui.Button((x, by, 150, 52), "CANCEL", self.on_close, color=ui.BTN_QUIET, size=16)

    def run(self, replace):
        msg, col = import_csv(self.app, self.path.value, replace)
        self.toasts.add(msg, col, 5)
        if col is not ui.BAD:
            self.on_close()

    def drop(self, path):
        self.path.value = path

    def handle(self, e):
        for b in (self.btn_add, self.btn_replace, self.btn_close):
            if b.handle(e):
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.on_close()
            return
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.run(False)
            return
        self.path.handle(e)

    def draw(self, surf):
        ui.dim(surf, 175)
        b = self.box
        ui.panel(surf, b, ui.PANEL, 20, ui.CYAN, 250)
        ui.hazard(surf, (b.x + 30, b.y + 26, 40, 22))
        ui.text(surf, "IMPORT A CSV", (b.x + 84, b.y + 22), 24, ui.CYAN, bold=True)
        self.path.draw(surf)
        y = self.path.rect.bottom + 24
        tips = [("FORMAT", "question, choice A, choice B, choice C, choice D, answer, topic (optional)"),
                ("ANSWER", "1-4, A-D, or the exact text of the right choice"),
                ("TIP", "drag the .csv file onto this window - a header row is fine - ; or , separators"),
                ("SAMPLE", "sample_questions.csv next to the game")]
        for label, what in tips:
            ui.text(surf, label, (b.x + 40, y), 12, ui.WARN, bold=True)
            for i, part in enumerate(ui.wrap(what, 16, b.w - 200)[:2]):
                ui.text(surf, part, (b.x + 150, y - 2 + i * 22), 16, ui.ICE)
            y += 46
        for btn in (self.btn_close, self.btn_replace, self.btn_add):
            btn.draw(surf)
