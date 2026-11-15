"""Shared constants for server and clients.

Network values can be overridden with environment variables (or the client's
--server / --tcp-port flags) so the same code runs on a LAN or over Tailscale.
"""
import os


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --- Network -----------------------------------------------------------------
SERVER_HOST = os.environ.get("ARENA_SERVER", "127.0.0.1")   # client default target
BIND_HOST = os.environ.get("ARENA_BIND", "0.0.0.0")         # server listens on all interfaces
TCP_PORT = _env_int("ARENA_TCP_PORT", 5000)
UDP_PORT = _env_int("ARENA_UDP_PORT", 5001)
PUBLIC_HOST = os.environ.get("ARENA_PUBLIC_HOST", "")       # address put in join string / QR (auto if empty)

MAX_DATAGRAM = 1200          # bytes; below Tailscale's 1280 MTU, so never fragmented
MAX_LINE = 512 * 1024        # longest TCP line we accept (a full question bank fits) before dropping the client

# --- Rooms ---------------------------------------------------------------------
MIN_PLAYERS = max(1, _env_int("ARENA_MIN_PLAYERS", 3))   # set to 1 on the server to test alone
MAX_PLAYERS = 10
ROOM_CODE_DIGITS = 6

# --- World ---------------------------------------------------------------------
WORLD_W, WORLD_H = 1280, 720
PLAYER_SPEED = 220.0         # px/s
PLAYER_RADIUS = 7            # feet; the wall grid is pre-shrunk by about this much
INTERACT_RADIUS = 60         # px from terminal centre to press E
INTERACT_SLACK = 10          # extra px the server tolerates for latency

# --- Timing (seconds) ----------------------------------------------------------
COUNTDOWN_S = 5
GAME_DURATION_S = _env_int("ARENA_GAME_SECONDS", 180)
TERMINAL_COOLDOWN_S = 5
WRONG_LOCKOUT_S = 5
TICK_HZ = 20                 # server tick: snapshots + timers
POS_HZ = 20                  # client position updates
PING_INTERVAL_S = 1.0
HEARTBEAT_TIMEOUT_S = 5.0
RESUME_WINDOW_S = 30.0
TIME_SYNC_INTERVAL_S = 10.0

# --- Scoring -------------------------------------------------------------------
POINTS_CORRECT = 100
POINTS_WRONG = -20           # score floors at 0

# --- Terminals -----------------------------------------------------------------
# A terminal can be cracked by this many different players, once each, then it
# goes offline for the rest of the round: nobody can camp one terminal.
TERMINAL_MAX_USES = max(1, _env_int("ARENA_TERMINAL_USES", 3))

# --- Ultimate --------------------------------------------------------------------
ULT_STREAK = max(1, _env_int("ARENA_ULT_STREAK", 5))     # correct answers in a row to charge it
ULT_DAMAGE = 10                                          # points every other player loses

# --- Host question bank ----------------------------------------------------------
MAX_QUESTIONS = 200
MAX_QUESTION_TEXT = 220
MAX_CHOICE_TEXT = 90
MAX_TOPIC_TEXT = 20

# --- Accounts ------------------------------------------------------------------
PBKDF2_ITERATIONS = 200_000
