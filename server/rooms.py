"""Room registry: codes, create / join / spectate / leave, roster updates.

Locking rule: the registry (code -> room) and every Session.room field are
changed only while holding server.lock; a room's own state only while holding
room.lock. When both are needed, server.lock is always taken first.
"""
import secrets
import threading

from common import config
from common import protocol as P
from server import game

PALETTE_SIZE = 10


class PlayerState:
    def __init__(self, session, color, join_index):
        self.session = session
        self.id = session.player_id
        self.name = session.username
        self.color = color
        self.join_index = join_index
        self.status = P.STATUS_CONNECTED      # connected | disconnected | left
        self.score = 0
        self.score_time = 0.0                 # when the current score was reached (tie-break)
        self.x = self.y = 0.0
        self.dir = "down"
        self.last_seq = -1
        self.last_pos_time = 0.0
        self.lockouts = {}                    # terminal_id -> monotonic time the lockout ends

    @property
    def connected(self):
        return self.status == P.STATUS_CONNECTED


class Room:
    def __init__(self, code, host_session, public_host):
        self.code = code
        self.lock = threading.RLock()
        self.host_id = host_session.player_id
        self.host_name = host_session.username
        self.players = {}                     # player_id -> PlayerState (join order)
        self.spectators = {}                  # player_id -> Session (admins)
        self.phase = P.PHASE_WAITING
        self.join_string = f"arena://{public_host}:{config.TCP_PORT}/{code}"
        self.closed = False
        self.needs_cleanup = False
        self._join_counter = 0
        # game fields (filled by game.reset_for_game)
        self.terminals = {}
        self.question_pool = []
        self.countdown_end = 0.0
        self.end_time = 0.0
        self.next_sync = 0.0

    # --- membership -------------------------------------------------------------
    def add_player(self, session):
        used = {p.color for p in self.players.values()}
        color = next(c for c in range(PALETTE_SIZE) if c not in used)
        self.players[session.player_id] = PlayerState(session, color, self._join_counter)
        self._join_counter += 1

    def connected_players(self):
        return [p for p in self.players.values() if p.connected]

    def member_sessions(self):
        """Everyone who should receive room broadcasts right now."""
        out = [p.session for p in self.players.values() if p.connected]
        out.extend(self.spectators.values())
        return out

    def broadcast(self, obj):
        for s in self.member_sessions():
            s.send(obj)

    # --- payloads ---------------------------------------------------------------
    def roster(self):
        return P.msg(
            P.ROOM_UPDATE,
            code=self.code,
            host=self.host_id,
            host_name=self.host_name,
            players=[
                {"id": p.id, "name": p.name, "status": p.status, "color": p.color, "score": p.score}
                for p in self.players.values() if p.status != P.STATUS_LEFT
            ],
            status=self.phase,
            max=config.MAX_PLAYERS,
            min=config.MIN_PLAYERS,
            join_string=self.join_string,
            spectators=len(self.spectators),
        )

    def summary(self):
        return {
            "code": self.code,
            "host": self.host_name,
            "players": len([p for p in self.players.values() if p.status != P.STATUS_LEFT]),
            "max": config.MAX_PLAYERS,
            "status": self.phase,
        }


class RoomRegistry:
    def __init__(self, server):
        self.server = server
        self.rooms = {}

    def _new_code(self):
        while True:
            code = f"{secrets.randbelow(10 ** config.ROOM_CODE_DIGITS):0{config.ROOM_CODE_DIGITS}d}"
            if code not in self.rooms:
                return code

    # --- handlers ---------------------------------------------------------------
    def list_rooms(self, session):
        with self.server.lock:
            rooms = list(self.rooms.values())
        data = []
        for r in rooms:
            with r.lock:
                data.append(r.summary())
        session.send(P.msg(P.ROOM_LIST, rooms=data))

    def create_room(self, session):
        with self.server.lock:
            if session.room is not None:
                session.send(P.error(P.E_ALREADY_IN_ROOM, "Leave your current room first"))
                return
            room = Room(self._new_code(), session, self.server.public_host)
            self.rooms[room.code] = room
            with room.lock:
                if session.is_admin:
                    room.spectators[session.player_id] = session   # admin: host-spectator
                else:
                    room.add_player(session)                        # player: host and player
                session.room = room
                session.send(P.msg(P.ROOM_CREATED, code=room.code, join_string=room.join_string))
                room.broadcast(room.roster())
        self.server.log.info("room %s created by %s", room.code, session.username)

    def join_room(self, session, code):
        if session.is_admin:
            session.send(P.error(P.E_FORBIDDEN, "Admins cannot play; use Spectate"))
            return
        code = str(code or "").strip()
        with self.server.lock:
            if session.room is not None:
                session.send(P.error(P.E_ALREADY_IN_ROOM, "Leave your current room first"))
                return
            room = self.rooms.get(code)
            if room is None:
                session.send(P.error(P.E_BAD_CODE, f"No room with code {code}"))
                return
            with room.lock:
                if room.phase != P.PHASE_WAITING:
                    session.send(P.error(P.E_ROOM_STARTED, "That game has already started"))
                    return
                if len(room.players) >= config.MAX_PLAYERS:
                    session.send(P.error(P.E_ROOM_FULL, "Room is full"))
                    return
                room.add_player(session)
                session.room = room
                roster = room.roster()
                session.send(P.msg(P.ROOM_JOINED, room=roster, spectator=False))
                room.broadcast(roster)

    def spectate_room(self, session, code):
        if not session.is_admin:
            session.send(P.error(P.E_FORBIDDEN, "Only the admin can spectate"))
            return
        code = str(code or "").strip()
        with self.server.lock:
            room = self.rooms.get(code)
            if room is None:
                session.send(P.error(P.E_BAD_CODE, f"No room with code {code}"))
                return
            if session.room is not None and session.room is not room:
                session.send(P.error(P.E_ALREADY_IN_ROOM, "Leave your current room first"))
                return
            with room.lock:
                room.spectators[session.player_id] = session
                session.room = room
                roster = room.roster()
                session.send(P.msg(P.ROOM_JOINED, room=roster, spectator=True))
                if room.phase != P.PHASE_WAITING:      # joining mid-game: send the full state
                    session.send(game.started_message(room))
                room.broadcast(roster)

    def leave_room(self, session, reason="left"):
        """LEAVE_ROOM, LOGOUT, or a drop while the room is waiting."""
        with self.server.lock:
            room = session.room
            if room is None:
                return
            with room.lock:
                self._remove_member_locked(room, session, reason)

    # --- internals (server.lock and room.lock held) -------------------------------
    def _remove_member_locked(self, room, session, reason):
        pid = session.player_id
        session.room = None
        is_host = pid == room.host_id
        if pid in room.spectators:
            del room.spectators[pid]
            if is_host and room.phase == P.PHASE_WAITING:
                self.close_room_locked(room, "The host left")
                return
        elif pid in room.players:
            if room.phase == P.PHASE_WAITING:
                del room.players[pid]
                if is_host:
                    self.close_room_locked(room, "The host left")
                    return
            else:
                # mid-game: keep the frozen score on the board
                game.on_player_gone(room, room.players[pid], P.STATUS_LEFT)
        if not room.closed:
            room.broadcast(room.roster())

    def close_room_locked(self, room, reason):
        room.closed = True
        self.rooms.pop(room.code, None)
        sessions = [p.session for p in room.players.values()] + list(room.spectators.values())
        for s in sessions:
            if s.room is room:
                s.room = None
                s.send(P.msg(P.ROOM_CLOSED, reason=reason))
        room.players.clear()
        room.spectators.clear()
        self.server.log.info("room %s closed: %s", room.code, reason)

    def post_game_cleanup(self, room):
        """After GAME_OVER: drop players who left or are gone; close if host is gone."""
        with self.server.lock:
            with room.lock:
                room.needs_cleanup = False
                if room.closed:
                    return
                for pid, p in list(room.players.items()):
                    if not p.connected:
                        del room.players[pid]
                        if p.session.room is room:
                            p.session.room = None
                host_here = room.host_id in room.players or room.host_id in room.spectators
                if not host_here:
                    self.close_room_locked(room, "The host left")
                else:
                    room.broadcast(room.roster())

    def expire_session(self, session):
        """Session token expired (30 s after a drop). server.lock is held by the caller."""
        room = session.room
        if room is None:
            return
        with room.lock:
            pid = session.player_id
            if pid in room.spectators:
                self._remove_member_locked(room, session, "expired")
            elif pid in room.players:
                if room.phase == P.PHASE_WAITING:
                    self._remove_member_locked(room, session, "expired")
                else:
                    session.room = None   # stays greyed on the board until game over
