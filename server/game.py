"""Game rules: phases, terminals, the answer race, scoring and the timer.

Every function here runs with room.lock held. The claim race between two
near-simultaneous correct answers is decided by that lock: whichever ANSWER is
processed first wins, and the second finds the terminal's question_id changed.
"""
import json
import math
import os
import random
import time

from common import config, map_data
from common import protocol as P

_BANK = {}          # question_id -> {id, topic, text, choices, answer}


def load_questions(path):
    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    for q in items:
        assert len(q["choices"]) == 4 and 0 <= q["answer"] <= 3, f"bad question {q.get('id')}"
        _BANK[q["id"]] = q
    return len(_BANK)


class Terminal:
    def __init__(self, tid, x, y):
        self.id = tid
        self.x = x
        self.y = y
        self.state = P.TERMINAL_ACTIVE
        self.question = None
        self.claimed_by = None
        self.ready_at = 0.0

    def payload(self, now):
        return {
            "terminal_id": self.id,
            "x": self.x,
            "y": self.y,
            "state": self.state,
            "claimed_by": self.claimed_by,
            "ready_in_ms": max(0, int((self.ready_at - now) * 1000)) if self.state == P.TERMINAL_COOLDOWN else 0,
        }


# --- helpers ------------------------------------------------------------------------
def _draw_question(room):
    """Next question; no repeats within a game until the bank runs out."""
    if not room.question_pool:
        on_terminals = {t.question["id"] for t in room.terminals.values() if t.question}
        room.question_pool = [qid for qid in _BANK if qid not in on_terminals] or list(_BANK)
        random.shuffle(room.question_pool)
    return _BANK[room.question_pool.pop()]


def scores_payload(room):
    ranked = sorted(room.players.values(), key=_rank_key)
    return [
        {"id": p.id, "name": p.name, "score": p.score, "connected": p.connected,
         "status": p.status, "color": p.color}
        for p in ranked
    ]


def _rank_key(p):
    # higher score first; on a tie, whoever reached that score first
    return (-p.score, p.score_time if p.score > 0 else 0.0, p.join_index)


def _set_score(p, new_score, now):
    new_score = max(0, new_score)
    if new_score != p.score:
        p.score = new_score
        p.score_time = now


def remaining_ms(room, now):
    if room.phase == P.PHASE_PLAYING:
        return max(0, int((room.end_time - now) * 1000))
    if room.phase == P.PHASE_COUNTDOWN:
        return config.GAME_DURATION_S * 1000
    return 0


def started_message(room):
    """GAME_STARTED: everything a client needs to draw the game (also used for RESUME)."""
    now = time.monotonic()
    return P.msg(
        P.GAME_STARTED,
        phase=room.phase,
        duration_ms=config.GAME_DURATION_S * 1000,
        remaining_ms=remaining_ms(room, now),
        countdown_ms=max(0, int((room.countdown_end - now) * 1000)) if room.phase == P.PHASE_COUNTDOWN else 0,
        map=map_data.payload(),
        terminals=[t.payload(now) for t in room.terminals.values()],
        spawns=[{"id": p.id, "x": p.x, "y": p.y} for p in room.players.values()],
        players=[{"id": p.id, "name": p.name, "color": p.color, "status": p.status}
                 for p in room.players.values()],
        positions=[{"id": p.id, "x": round(p.x, 1), "y": round(p.y, 1), "dir": p.dir}
                   for p in room.players.values()],
        scores=scores_payload(room),
    )


# --- phases -----------------------------------------------------------------------
def start_game(room, session):
    if session.player_id != room.host_id:
        session.send(P.error(P.E_NOT_HOST, "Only the host can start the game"))
        return
    if room.phase != P.PHASE_WAITING:
        session.send(P.error(P.E_ROOM_STARTED, "The game is already running"))
        return
    n = len(room.connected_players())
    if n < config.MIN_PLAYERS:
        session.send(P.error(P.E_NOT_ENOUGH_PLAYERS,
                             f"Need at least {config.MIN_PLAYERS} players to start (have {n})"))
        return
    now = time.monotonic()
    # drop anyone who is not connected before the game starts
    for pid, p in list(room.players.items()):
        if not p.connected:
            del room.players[pid]
    room.phase = P.PHASE_COUNTDOWN
    room.countdown_end = now + config.COUNTDOWN_S
    room.question_pool = []
    room.terminals = {}
    for t in map_data.TERMINALS:
        term = Terminal(t["id"], t["x"], t["y"])
        room.terminals[term.id] = term
    for term in room.terminals.values():
        term.question = _draw_question(room)
    for i, p in enumerate(room.players.values()):
        p.score = 0
        p.score_time = 0.0
        p.lockouts = {}
        p.x, p.y = map_data.SPAWNS[i % len(map_data.SPAWNS)]
        p.dir = "down"
        p.last_seq = -1
        p.last_pos_time = now
    room.broadcast(P.msg(P.GAME_COUNTDOWN, seconds=config.COUNTDOWN_S))
    room.broadcast(room.roster())


def tick(room, now):
    """Advance timers. Called 20 times a second by the server tick loop."""
    if room.phase == P.PHASE_COUNTDOWN:
        if len(room.connected_players()) < 2:
            game_over(room, now)
        elif now >= room.countdown_end:
            room.phase = P.PHASE_PLAYING
            room.end_time = now + config.GAME_DURATION_S
            room.next_sync = now + config.TIME_SYNC_INTERVAL_S
            for p in room.players.values():
                p.last_pos_time = now
            room.broadcast(started_message(room))
            room.broadcast(room.roster())
    elif room.phase == P.PHASE_PLAYING:
        for t in room.terminals.values():
            if t.state == P.TERMINAL_COOLDOWN and now >= t.ready_at:
                t.state = P.TERMINAL_ACTIVE
                t.claimed_by = None
                t.question = _draw_question(room)
                room.broadcast(P.msg(P.TERMINAL_STATE, **t.payload(now)))
        if now >= room.next_sync:
            room.next_sync = now + config.TIME_SYNC_INTERVAL_S
            room.broadcast(P.msg(P.TIME_SYNC, remaining_ms=remaining_ms(room, now)))
        if now >= room.end_time or len(room.connected_players()) < 2:
            game_over(room, now)


def game_over(room, now):
    ranked = sorted(room.players.values(), key=_rank_key)
    leaderboard = [
        {"rank": i + 1, "id": p.id, "name": p.name, "score": p.score,
         "connected": p.connected, "color": p.color}
        for i, p in enumerate(ranked)
    ]
    winner = ranked[0].name if ranked and ranked[0].score > 0 else None
    room.phase = P.PHASE_WAITING
    room.terminals = {}
    room.broadcast(P.msg(P.GAME_OVER, leaderboard=leaderboard, winner=winner))
    room.needs_cleanup = True          # server removes gone players under server.lock


# --- terminals -------------------------------------------------------------------
def open_terminal(room, p, terminal_id, now):
    s = p.session
    if room.phase != P.PHASE_PLAYING:
        s.send(P.error(P.E_NOT_PLAYING, "The game is not running"))
        return
    t = room.terminals.get(terminal_id)
    if t is None:
        s.send(P.error(P.E_BAD_TERMINAL, "No such terminal"))
        return
    # use the server-validated position, never the client's claim
    if math.hypot(p.x - t.x, p.y - t.y) > config.INTERACT_RADIUS + config.INTERACT_SLACK:
        s.send(P.error(P.E_TOO_FAR, "Too far from the terminal", terminal_id=t.id))
        return
    until = p.lockouts.get(t.id, 0)
    if now < until:
        s.send(P.error(P.E_LOCKED_OUT, "Locked out of this terminal",
                       terminal_id=t.id, remaining_ms=int((until - now) * 1000)))
        return
    if t.state == P.TERMINAL_COOLDOWN:
        s.send(P.error(P.E_COOLDOWN, "Terminal is cooling down",
                       terminal_id=t.id, remaining_ms=int((t.ready_at - now) * 1000)))
        return
    q = t.question
    s.send(P.msg(P.TERMINAL_QUESTION, terminal_id=t.id, question_id=q["id"],
                 topic=q.get("topic", ""), text=q["text"], choices=q["choices"]))
    # note: the "answer" field never leaves the server


def answer(room, p, terminal_id, question_id, choice, now):
    s = p.session
    if room.phase != P.PHASE_PLAYING:
        s.send(P.error(P.E_NOT_PLAYING, "The game is not running"))
        return
    t = room.terminals.get(terminal_id)
    if t is None:
        s.send(P.error(P.E_BAD_TERMINAL, "No such terminal"))
        return
    if not isinstance(choice, int) or not 0 <= choice <= 3:
        s.send(P.error(P.E_INVALID, "choice must be 0..3"))
        return

    def result(status, points, **extra):
        s.send(P.msg(P.ANSWER_RESULT, terminal_id=t.id, status=status, points=points,
                     score=p.score, **extra))

    until = p.lockouts.get(t.id, 0)
    if now < until:
        result(P.RESULT_LOCKED, 0, remaining_ms=int((until - now) * 1000))
        return
    # someone else already claimed it: the question moved on
    if t.state != P.TERMINAL_ACTIVE or t.question is None or t.question["id"] != question_id:
        result(P.RESULT_TOO_LATE, 0)
        return

    if choice == t.question["answer"]:
        _set_score(p, p.score + config.POINTS_CORRECT, now)
        t.state = P.TERMINAL_COOLDOWN
        t.claimed_by = p.id
        t.ready_at = now + config.TERMINAL_COOLDOWN_S
        result(P.RESULT_CORRECT, config.POINTS_CORRECT)
        room.broadcast(P.msg(P.TERMINAL_STATE, **t.payload(now)))
    else:
        before = p.score
        _set_score(p, p.score + config.POINTS_WRONG, now)
        p.lockouts[t.id] = now + config.WRONG_LOCKOUT_S
        result(P.RESULT_WRONG, p.score - before, lockout_ms=config.WRONG_LOCKOUT_S * 1000)
    room.broadcast(P.msg(P.SCORE_UPDATE, scores=scores_payload(room)))


# --- connection changes -------------------------------------------------------------
def on_player_gone(room, p, status=P.STATUS_DISCONNECTED):
    """A player dropped (or left) during countdown/playing: freeze score, grey out."""
    if p.status == P.STATUS_LEFT:
        return
    p.status = status
    room.broadcast(P.msg(P.PLAYER_STATUS, player_id=p.id, status=status, name=p.name))
    room.broadcast(P.msg(P.SCORE_UPDATE, scores=scores_payload(room)))


def on_player_back(room, p):
    p.status = P.STATUS_CONNECTED
    p.last_pos_time = time.monotonic()
    room.broadcast(P.msg(P.PLAYER_STATUS, player_id=p.id, status=P.STATUS_RECONNECTED, name=p.name))
    room.broadcast(P.msg(P.SCORE_UPDATE, scores=scores_payload(room)))


def bank_size():
    return len(_BANK)


def default_bank_path():
    return os.path.join(os.path.dirname(__file__), "data", "questions.json")
