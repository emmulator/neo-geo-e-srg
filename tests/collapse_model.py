"""Model of the collapse effect, translated from the Vectrex
(vectrex-e-srg v1.0.0, e-srg.c collapse_update) with the plan's x 59/50 on
the frame counts. This is the reference the C's collapse state machine
(src/rules.c: collapse_state / collapse_frac / collapse_shake /
collapse_burst / collapse_fall / collapse_dim) is checked against, exactly
like rules_model.py is for the rules.

The Vectrex runs the collapse while dead_t && dome_dead, with f =
DEAD_FRAMES - dead_t (0 on the death frame itself), and zeroes its four
effect variables (shake, burst, sink, dim) whenever the gate is off — so a
non-collapsing frame always draws the dome whole. collapse_model() mirrors
that: it takes the rules' dead_t and dome_dead (the same numbers the C
prints) and returns (draw, shake, burst, fall, dim); draw is 0 only from
f >= COLLAPSE_GONE (the dome is gone).

Frame counts, Vectrex then scaled x 59/50:
    DEAD_FRAMES   100 -> 118
    COLLAPSE_SHAKE 35 -> 41     shake: shake ramps 3, 7, 15, 31 at f 8, 16, 26
    COLLAPSE_GONE  85 -> 100     after that the dome is not drawn
The fall (g = f - 41 = 0..58, while f < 100):
    burst = g * 3                       the runs fly apart
    fall = min(120, sum_{q=1..g>>3} 8q + (g & 7) * (g>>3)) (the Vectrex's
           incremental fall += g>>3 capped at 120, in closed form)
    dim = g                             the palette fades over the fall
Exit: at f >= 100 the effects are 0 and draw is 0, through the last
countdown frames to the respawn at 118.
"""
import rules_model as rm

COLLAPSE_SHAKE = round(35 * 59 / 50)    # 41
COLLAPSE_GONE = round(85 * 59 / 50)     # 100
DEAD_FRAMES = rm.DEAD_FRAMES_NEO        # 118


def vectrex_fall(g):
    """e-srg.c: if (fall + (g >> 3) <= 120) fall += g >> 3, for each g."""
    fall = 0
    for q in range(0, g + 1):
        if fall + (q >> 3) <= 120:
            fall += q >> 3
    return fall


def collapse(dead_t, dome_dead):
    """(draw, shake, burst, fall, dim) for a rules state; 0s when off."""
    if not dead_t or not dome_dead:
        return (1, 0, 0, 0, 0)
    f = DEAD_FRAMES - dead_t
    if f >= COLLAPSE_GONE:
        return (0, 0, 0, 0, 0)
    if f < COLLAPSE_SHAKE:
        shake = 3 if f < 8 else 7 if f < 16 else 15 if f < 26 else 31
        return (1, shake, 0, 0, 0)
    g = f - COLLAPSE_SHAKE
    return (1, 31, g * 3, vectrex_fall(g), g)
