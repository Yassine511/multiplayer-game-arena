"""Read a host's question file (CSV) into question dicts.

One question per row:

    question, choice A, choice B, choice C, choice D, answer [, topic]

* answer: 1-4, A-D, or the exact text of the right choice
* a header row is optional; "," ";" and tab separators all work; quote a cell
  that contains the separator ("TCP, then UDP")
* Excel's "CSV UTF-8" and plain Windows "CSV" exports both load
"""
import csv
import io

from common import config

LETTERS = "ABCD"


def decode(data):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _delimiter(text):
    sample = "\n".join(text.splitlines()[:5])
    counts = {d: sample.count(d) for d in (",", ";", "\t")}
    return max(counts, key=counts.get) if any(counts.values()) else ","


def _answer_index(cell, choices):
    c = cell.strip()
    if c in ("1", "2", "3", "4"):
        return int(c) - 1
    if len(c) == 1 and c.upper() in LETTERS:
        return LETTERS.index(c.upper())
    low = [x.strip().lower() for x in choices]
    if c.lower() in low:
        return low.index(c.lower())
    return None


def parse(text):
    """Return (questions, errors). Each question: {text, choices[4], answer 0-3, topic}."""
    rows = list(csv.reader(io.StringIO(text), delimiter=_delimiter(text)))
    questions, errors = [], []
    for n, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells or cells[0].startswith("#"):
            continue
        if len(cells) < 6:
            if not questions and n == 1 and "question" in cells[0].lower():
                continue                       # short header row
            errors.append(f"row {n}: needs a question, 4 choices and the answer ({len(cells)} cells)")
            continue
        text_, choices, ans = cells[0], cells[1:5], cells[5]
        topic = cells[6] if len(cells) > 6 else ""
        idx = _answer_index(ans, choices)
        if idx is None:
            if n == 1 and not questions:
                continue                       # header row: "question,a,b,c,d,answer"
            errors.append(f"row {n}: answer '{ans}' is not 1-4, A-D or one of the choices")
            continue
        if not text_:
            errors.append(f"row {n}: the question is empty")
            continue
        if any(not c for c in choices):
            errors.append(f"row {n}: a choice is empty")
            continue
        if len(text_) > config.MAX_QUESTION_TEXT:
            errors.append(f"row {n}: question longer than {config.MAX_QUESTION_TEXT} characters")
            continue
        if any(len(c) > config.MAX_CHOICE_TEXT for c in choices):
            errors.append(f"row {n}: a choice is longer than {config.MAX_CHOICE_TEXT} characters")
            continue
        questions.append({"text": text_, "choices": choices, "answer": idx,
                          "topic": topic[:config.MAX_TOPIC_TEXT]})
    return questions, errors


def load(path):
    with open(path, "rb") as f:
        return parse(decode(f.read()))
