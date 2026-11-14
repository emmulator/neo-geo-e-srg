"""Check the M4 Task 4 frame-budget measurement.

  check_frame_mark.py PROBE END_ADDR [TAG]

The probe (scripts/frame_mark_probe.lua) boots the -DFRAME_MARK cart,
drives the same centred full game as the collapse boot test, and every
MAME frame records the cart's BSS marks: the LSPC line counter at the
frame's work start (right after ng_wait_vblank) and at its end
(work_start_mark / work_end_mark). lspc_vpos() = ((LSPCMODE >> 7) &
0x1FF) - 0x100; MAME's get_video_control() (neogeo_v.cpp) puts vpos + 0x100
in those bits and wraps vpos 256..263 to vpos - 8, so a stored u16 is a
signed vpos: 0..255 as-is, 0xFFF8..0xFFFF = -8..-1 = lines 256..263 (the
vblank tail).  The frame's work span ((end - start) mod 264) is the true
cost of one frame's work in scanlines, independent of where in the vblank
ng_wait_vblank returned.

No dropped frames means the work finishes before the next frame's visible
area: the LSPC latches its draw source once per frame, and a span >= 224
scanlines would end in (or after) the next frame's picture.  The centred
policy's game includes a dome death (cart frame 8359 under Task 1's seed;
8202 before it, Vectrex 1.1.0 rules) with the worst
crack/missile/collapse workload, so the worst frame is exercised.

With TAG "crackframemark" (the -DCRACK_TEST -DFRAME_MARK cart, M4-fixes
Task 3), the hook keeps the dome whole, so there is no collapse; the run
measures the worst frame with all 38 broken-window overlays plus the
missile wave (the overlay draw is the biggest single addition).  No
collapse window is reported then.

The probe reads the marks at the START of each MAME frame (before the
cart's main loop writes them), so each record carries the PREVIOUS
completed frame's values.  Before the cart's first main-loop mark all the
BSS marks are 0.
"""
import sys

WORST_LIMIT = 224            # fail: a work span that long reaches into the next visible area
FRAME_LINES = 264            # a full MAME frame (visible + blank)


def _vpos(v):
    """the signed u16 vpos the cart stored (0xFFFE = -2 = line 262 of the
    same frame's vblank tail; 0..255 = vpos 0..255 or the next frame's)."""
    return v if v < 0x8000 else v - 0x10000


def main():
    probe = sys.argv[1]
    end_addr = sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else ""
    if end_addr == "0":
        print("check_frame_mark: END_ADDR 0 (no measurement)")
        return 1

    worst_span = -1
    worst_fc = 0
    worst_end_vpos = 0
    records = []
    lines = open(probe, "rb").read().decode("ascii", "replace").splitlines()
    for line in lines:
        p = line.split()
        if len(p) >= 6 and p[0] == "M":
            fc, end, mx, mn = (int(x) for x in p[1:5])
            start = int(p[5])
            records.append((fc, end, mx, mn, start))

    if not records:
        print("FAIL frame_mark: no M records")
        return 1

    # the worst work span: (end - start) mod 264, over every completed
    # frame's marks.  Pre-seed records read BSS zeros (all four marks 0);
    # a real frame's work always spans >= 1 line (start=243, end != start).
    # The first marked frame (fc 32 in the watched run) seeds start=20/end=132:
    # the first ng_wait_vblank returned mid-frame because the main-loop
    # init had just finished, and that frame's span is its true cost too.
    worst_collapse = None
    for fc, end, mx, mn, start in records:
        if start == end == 0:
            continue
        s, e = _vpos(start), _vpos(end)
        span = (e - s) % FRAME_LINES
        if span > worst_span:
            worst_span = span
            worst_fc = fc
            worst_end_vpos = e
        # the collapse window: the centred game's first dome death at cart
        # frame 8359 and its rebuild at 8477 (tests/check_collapse.py's
        # model derivation, Task 1's seed) — the task's "most cracks,
        # missiles and the collapse at once".  (The cracks hide during the
        # death, as on the Vectrex, so this window is lighter than the
        # busiest play frame; we report it so the numbers are on record.)
        if 8359 <= fc <= 8477 and tag != "crackframemark":
            if worst_collapse is None or span > worst_collapse[0]:
                worst_collapse = (span, fc, e)

    if worst_span < 0:
        print("FAIL frame_mark: the cart never wrote a work mark")
        return 1

    # the span is the gate: a span >= 224 scanlines would overlap the next
    # frame's picture (the LSPC latches the sprite list once per frame, so
    # the work must be done before the next visible area starts)
    if worst_span >= WORST_LIMIT:
        print(f"FAIL frame_mark: worst work span {worst_span} scanlines "
              f"(>= {WORST_LIMIT}) at cart frame {worst_fc}: the frame's work "
              f"could not finish at 60 Hz")
        return 1

    frac = worst_span / FRAME_LINES
    what = "the centred game (dome death + collapse + cracks/missiles)"
    extra = ""
    if tag == "crackframemark":
        what = ("the 38-broken-tiles + missile-wave cart (M4-fixes Task 3: "
                "no collapse happens — the hook keeps the dome whole)")
    elif worst_collapse:
        extra = (f", during the collapse (fc 8359..8477) worst span "
                 f"{worst_collapse[0]} at fc {worst_collapse[1]}")
    print(f"PASS frame_mark ({what}): worst work end vpos {worst_end_vpos} "
          f"(line {worst_end_vpos % FRAME_LINES}) at cart frame {worst_fc}, "
          f"worst work span {worst_span} scanlines ({frac:.1%} of the "
          f"264-line frame){extra} - no dropped frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
