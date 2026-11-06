"""Render a QR code into a pygame Surface (needs the `qrcode` package)."""
import pygame

try:
    import qrcode
except ImportError:          # the client still works; it just shows the text instead
    qrcode = None


def make_qr_surface(data, size):
    if qrcode is None:
        return None
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    cell = max(1, size // n)
    surf = pygame.Surface((n * cell, n * cell))
    surf.fill((255, 255, 255))
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                surf.fill((0, 0, 0), (x * cell, y * cell, cell, cell))
    return surf
