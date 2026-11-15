"""The ten playable characters, shared by server (validation) and client (art).

A character is just an index into CHARACTERS on the wire. Several players may
pick the same one; the name plate and colour above each sprite tell them apart.
The art is baked by tools/import_characters.py into client/assets/characters/.
"""

CHARACTERS = [
    {"slug": "gojo", "name": "Gojo"},
    {"slug": "mia", "name": "Mia"},
    {"slug": "leo", "name": "Leo"},
    {"slug": "mui-goku", "name": "MUI Goku"},
    {"slug": "epstein", "name": "Epstein"},
    {"slug": "sukuna", "name": "Sukuna"},
    {"slug": "claude", "name": "Claude"},
    {"slug": "palantir-patrick", "name": "Palantir Patrick"},
    {"slug": "sam-altman", "name": "Sam Altman"},
    {"slug": "trump", "name": "Trump"},
]

COUNT = len(CHARACTERS)


def valid(c):
    return isinstance(c, int) and not isinstance(c, bool) and 0 <= c < COUNT


def name_of(c):
    return CHARACTERS[c]["name"] if valid(c) else "?"
