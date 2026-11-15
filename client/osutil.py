"""Small bridges to the operating system: the clipboard and a native "open file" dialog.

pygame 2.x has no reliable text clipboard (pygame.scrap.get_text only exists in
pygame-ce), so on Windows this talks to user32 directly. It also understands a
file copied in Explorer (Ctrl+C on the file itself): the clipboard then holds a
file list, not text, and its first path is returned.
"""
import os
import shutil
import subprocess
import sys

CF_UNICODETEXT = 13
CF_HDROP = 15


# --- clipboard --------------------------------------------------------------------------------
def _win_clipboard():
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT

    if not user32.OpenClipboard(None):
        return ""
    try:
        if user32.IsClipboardFormatAvailable(CF_HDROP):          # a file copied in Explorer
            h = user32.GetClipboardData(CF_HDROP)
            if h and shell32.DragQueryFileW(h, 0xFFFFFFFF, None, 0) > 0:
                n = shell32.DragQueryFileW(h, 0, None, 0)
                buf = ctypes.create_unicode_buffer(n + 1)
                shell32.DragQueryFileW(h, 0, buf, n + 1)
                return buf.value
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if h:
                p = kernel32.GlobalLock(h)
                if p:
                    try:
                        return ctypes.wstring_at(p)
                    finally:
                        kernel32.GlobalUnlock(h)
        return ""
    finally:
        user32.CloseClipboard()


def _run(cmd, timeout=2.0):
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def _unix_clipboard():
    for cmd in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"], ["pbpaste"]):
        if shutil.which(cmd[0]):
            text = _run(cmd)
            if text:
                return text
    try:                                                      # last resort: SDL through pygame.scrap
        import pygame
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        for kind in ("text/plain;charset=utf-8", "UTF8_STRING", pygame.SCRAP_TEXT):
            data = pygame.scrap.get(kind)
            if data:
                return data.decode("utf-8", "replace").replace("\x00", "")
    except Exception:
        pass
    return ""


def clipboard_text():
    """Text on the system clipboard (or the path of a copied file), "" if none. Never raises."""
    try:
        text = _win_clipboard() if sys.platform == "win32" else _unix_clipboard()
    except Exception:
        text = ""
    if text.startswith("file://"):                           # Linux file managers copy URIs
        from urllib.parse import unquote, urlparse
        text = unquote(urlparse(text.splitlines()[0]).path)
    return text or ""


# --- open-file dialog -----------------------------------------------------------------------------
def _win_pick(title, patterns):
    import ctypes
    from ctypes import wintypes

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND),
                    ("hInstance", wintypes.HINSTANCE), ("lpstrFilter", wintypes.LPCWSTR),
                    ("lpstrCustomFilter", wintypes.LPWSTR), ("nMaxCustFilter", wintypes.DWORD),
                    ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR),
                    ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR),
                    ("nMaxFileTitle", wintypes.DWORD), ("lpstrInitialDir", wintypes.LPCWSTR),
                    ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD),
                    ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD),
                    ("lpstrDefExt", wintypes.LPCWSTR), ("lCustData", wintypes.LPARAM),
                    ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wintypes.LPCWSTR),
                    ("pvReserved", ctypes.c_void_p), ("dwReserved", wintypes.DWORD),
                    ("FlagsEx", wintypes.DWORD)]

    comdlg32 = ctypes.WinDLL("comdlg32")
    comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
    buf = ctypes.create_unicode_buffer(1024)
    spec = ";".join(patterns)
    filt = ctypes.create_unicode_buffer(f"Question files ({spec})\0{spec}\0All files (*.*)\0*.*\0\0", 256)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.lpstrFilter = ctypes.cast(filt, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrTitle = title
    ofn.Flags = 0x00001000 | 0x00000800 | 0x00080000 | 0x00000008   # FILE/PATH MUSTEXIST, EXPLORER, NOCHANGEDIR
    if comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return buf.value
    return None


def _unix_pick(title, patterns):
    if shutil.which("zenity"):
        out = _run(["zenity", "--file-selection", f"--title={title}",
                    f"--file-filter={' '.join(patterns)}", "--file-filter=*"], timeout=600)
    elif shutil.which("kdialog"):
        out = _run(["kdialog", "--title", title, "--getopenfilename", os.path.expanduser("~"),
                    " ".join(patterns)], timeout=600)
    else:
        return ""                                            # no dialog tool: caller says so
    return out.strip() if out else None


def can_pick_file():
    return sys.platform == "win32" or bool(shutil.which("zenity") or shutil.which("kdialog"))


def pick_file(title="Choose a file", patterns=("*.csv",)):
    """Blocking native file dialog. Returns the path, None if cancelled, "" if unavailable.
    Run it from a worker thread so the game window keeps drawing meanwhile."""
    try:
        return _win_pick(title, patterns) if sys.platform == "win32" else _unix_pick(title, patterns)
    except Exception:
        return ""
