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
MAX_LINE = 64 * 1024         # longest TCP line we accept before dropping the client

# --- Rooms ---------------------------------------------------------------------
MIN_PLAYERS = 3
MAX_PLAYERS = 10
ROOM_CODE_DIGITS = 6

# --- World ---------------------------------------------------------------------
WORLD_W, WORLD_H = 1280, 720
PLAYER_SPEED = 220.0         # px/s
PLAYER_RADIUS = 14
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

# --- Accounts ------------------------------------------------------------------
PBKDF2_ITERATIONS = 200_000
ADMIN_USERNAME = os.environ.get("ARENA_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ARENA_ADMIN_PASSWORD", "admin123")
