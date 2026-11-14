"""The screen layout's one source of truth (the HUD layout plan, Global
rules): the test checkers and the generators read the game's position
constants from the C headers — src/dome.h (DOME_X, DOME_Y), src/radar.h
(RADAR_CX, RADAR_CY, RADAR_RX, RADAR_RY, RADAR_H), src/hud.h (the HUD's
rows/columns) and src/title.h (the title's rows and the MVS countdown's
position) — never as literals.

The dome BOX's size (DOME_W, DOME_H, DOME_COLS, DOME_ROWS) is not a
per-machine choice like DOME_X/DOME_Y: it is the one size knob in
`tools/geometry.py` (DOME_COLS, DOME_ROWS, DOME_SCALE), read here from that
file so no test or checker carries its own copy of the box size. The
generated build/dome_map.h writes the same DOME_COLS/DOME_ROWS for the C.

A `#define NAME value` line is parsed straight (a simple integer). RADAR_CY
used to be an expression in the dome (DOME_Y + 112); Dome-scenery Task 2
made it the literal 184, and Task 8 moved it to 206 (22 px down onto the
console's left wing). The parser still evaluates an expression (`DOME_Y` is
substituted) so a future header may use one; a check that compares a
position fails on a wrong position because the tolerance the checker
applies is unchanged.

    from layout import d
    d.DOME_X, d.DOME_Y            # the dome box's screen top-left (px)
    d.DOME_COLS, d.DOME_ROWS      # the box in sprite columns / tiles
    d.DOME_W, d.DOME_H            # 16 * DOME_COLS, 16 * DOME_ROWS
    d.DOME_BOX                    # (X, Y, X + W - 1, Y + H - 1)
    d.BOX_BOTTOM                  # DOME_Y + DOME_H (the box's bottom line)
    d.RADAR_CX, d.RADAR_CY        # the radar ellipse's centre
    d.hud("HUD_GAMEOVER_ROW")     # a src/hud.h #define (an int)
    d.title("TITLE_COUNTDOWN_ROW")  # a src/title.h #define (an int)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import geometry as _geo  # noqa: E402  (the dome size knob: DOME_COLS/ROWS/SCALE)


def _defs(path):
    txt = open(path).read()
    return {m.group(1): m.group(2) for m in
            re.finditer(r"#define\s+(\w+)\s+([^\n]+)", txt)}


def _int_value(name, value):
    """resolve a define's value to an int: a plain integer (RADAR_CY is the
    literal 206 since dome-scenery Task 8) or an expression with DOME_Y in
    it (the parser still supports one)."""
    value = value.split("/*")[0].strip()
    dy = _DOME_INT.get("DOME_Y")
    return eval(value.replace("DOME_Y", str(dy)))


_DOME_TXT = open(os.path.join(SRC, "dome.h")).read()
_DOME_DEFS = dict(_defs(os.path.join(SRC, "dome.h")))
_DOME_INT = {k: int(v.split("/*")[0].strip()) for k, v in _DOME_DEFS.items()
             if re.fullmatch(r"\d+", v.split("/*")[0].strip())}
assert "DOME_X" in _DOME_INT and "DOME_Y" in _DOME_INT, \
    "src/dome.h must define DOME_X and DOME_Y"

_RADAR_DEFS = dict(_defs(os.path.join(SRC, "radar.h")))
_HUD_DEFS = dict(_defs(os.path.join(SRC, "hud.h")))
_TITLE_DEFS = dict(_defs(os.path.join(SRC, "title.h")))


class _Layout(object):
    @property
    def DOME_X(self):
        return _DOME_INT["DOME_X"]

    @property
    def DOME_Y(self):
        return _DOME_INT["DOME_Y"]

    @property
    def DOME_COLS(self):
        return _geo.DOME_COLS

    @property
    def DOME_ROWS(self):
        return _geo.DOME_ROWS

    @property
    def DOME_W(self):
        return _geo.DOME_W

    @property
    def DOME_H(self):
        return _geo.DOME_H

    @property
    def DOME_BOX(self):
        """its on-screen x/y span (the box's last pixel)."""
        return (self.DOME_X, self.DOME_Y,
                self.DOME_X + self.DOME_W - 1, self.DOME_Y + self.DOME_H - 1)

    @property
    def BOX_BOTTOM(self):
        return self.DOME_Y + self.DOME_H      # the box's bottom line (y)

    @property
    def RADAR_CX(self):
        return _int_value("RADAR_CX", _RADAR_DEFS["RADAR_CX"])

    @property
    def RADAR_CY(self):
        return _int_value("RADAR_CY", _RADAR_DEFS["RADAR_CY"])

    @property
    def RADAR_RX(self):
        return int(_RADAR_DEFS["RADAR_RX"].split("/*")[0].strip())

    @property
    def RADAR_RY(self):
        return int(_RADAR_DEFS["RADAR_RY"].split("/*")[0].strip())

    @property
    def RADAR_H(self):
        return int(_RADAR_DEFS["RADAR_H"].split("/*")[0].strip())

    def hud(self, name):
        """a src/hud.h #define's integer value (the HUD's rows/columns)."""
        return int(_HUD_DEFS[name].split("/*")[0].strip())

    def title(self, name):
        """a src/title.h #define's integer value (the title's rows and the
        MVS countdown's position)."""
        return int(_TITLE_DEFS[name].split("/*")[0].strip())


d = _Layout()
