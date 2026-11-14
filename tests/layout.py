"""The screen layout's one source of truth (the HUD layout plan, Global
rules): the test checkers and the generators read the game's position
constants from the C headers — src/dome.h (DOME_X, DOME_Y and the 176x128
box), src/radar.h (RADAR_CX, RADAR_CY, RADAR_RX, RADAR_RY, RADAR_H),
src/hud.h (the HUD's rows/columns) and src/title.h (the title's rows and
the MVS countdown's position) — never as literals.

A `#define NAME value` line is parsed straight (a simple integer), except
that RADAR_CY is defined in terms of the dome (DOME_Y + 112: the radar
keeps its place beside the dome's rim), so it is resolved through
DOME_Y here: whoever changes the dome's Y moves the radar's with it, and a
check that compares a position still fails on a wrong position because the
tolerance the checker applies is unchanged.

    from layout import d
    d.DOME_X, d.DOME_Y            # the dome box's screen top-left (px)
    d.DOME_BOX                    # (DOME_X, DOME_Y, DOME_X+175, DOME_Y+127)
    d.BOX_BOTTOM                  # DOME_Y + 128 (the box's bottom line)
    d.RADAR_CX, d.RADAR_CY        # the radar ellipse's centre
    d.hud("HUD_GAMEOVER_ROW")     # a src/hud.h #define (an int)
    d.title("TITLE_COUNTDOWN_ROW")  # a src/title.h #define (an int)
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")


def _defs(path):
    txt = open(path).read()
    return {m.group(1): m.group(2) for m in
            re.finditer(r"#define\s+(\w+)\s+([^\n]+)", txt)}


def _int_value(name, value):
    """resolve a define's value to an int: plain integers, or the
    DOME_Y + 112 expression radar.h uses for RADAR_CY (whose comment runs
    to the next line's configuration)."""
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
    def DOME_W(self):
        return 176                     # the box: 11 sprite columns x 16 px

    @property
    def DOME_H(self):
        return 128                     # ... 8 tiles tall

    @property
    def DOME_BOX(self):
        """its on-screen x/y span (the box's last pixel: X + 175, Y + 127)."""
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
