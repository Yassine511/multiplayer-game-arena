# PyInstaller recipe for the single-file game (server + client in one executable).
#
#   pip install pyinstaller
#   pyinstaller arena.spec            -> dist/arena.exe (Windows) or dist/arena (Linux)
#
# PyInstaller cannot cross-compile: build the Windows exe on Windows and the Linux
# binary on Linux (WSL Ubuntu works). See build.py.
import sys

datas = [
    ("client/assets", "client/assets"),
    ("server/data/questions.json", "server/data"),
    ("sample_questions.csv", "."),
]

a = Analysis(
    ["arena.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=[
        "client.screens.launch", "client.screens.login", "client.screens.lobby", "client.screens.room",
        "client.screens.game", "client.screens.spectator", "client.screens.results", "client.screens.picker",
        "client.screens.qeditor", "server.main", "qrcode",
    ],
    excludes=["tkinter", "numpy", "scipy", "PIL", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="arena",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,           # no terminal window behind the game; logs go to arena_data/arena.log
    icon=None,
)
