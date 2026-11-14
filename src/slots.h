/* slots.h: THE sprite slot map — the only place slot numbers are defined
 * (M5 Task 1). A higher slot draws on top (neo-geo-dev, "Sprite drawn
 * behind something it should cover").
 *
 * The map, in draw order (low to high):
 *
 *     1..12            stars (NSTARS 12): behind everything (M5 Task 2)
 *     13..32           missiles behind the dome (MIS_BEHIND_COUNT 20)
 *     33..43           the dome's 11 columns (sticky chain)
 *     44..188          broken-window overlays (BROKEN_SLOT_COUNT 145, the
 *                      generator's span today — tools/render_broken.py; a
 *                      change there must update BROKEN_SLOT_COUNT, and
 *                      tests/test_slots.py proves the two agree)
 *     189..190         the ship
 *     191..210         front missiles (MIS_FRONT_COUNT 20)
 *     211..218         explosions (EXPL_COUNT 8)
 *     219..237         the radar (RADAR_COUNT 19, reserved for Task 4:
 *                      4 frame + 3 x (1 stick + 4 heading))
 *
 * The last slot is <= 380 (381 sprites total).
 *
 * Every range starts where the one before it ended: each start below is
 * the previous start plus the previous count, so changing a count moves
 * everything after it. The counts themselves are the art's real numbers,
 * written here with their sources in comments; tests/test_slots.py proves
 * each equals the constant it names (NOBJ x MIS_COLS_MAX, DOME_COLS, ...)
 * every build, so a drift fails the gate instead of silently shifting the
 * map. NSTARS is overridable (-DNSTARS=16), which is the M5 Task 1
 * renumbering proof: the whole map moves and every consumer (the C code,
 * the probes via build/slots.lua, the checkers via build/slots.json, the
 * broken generator) follows from this one change.
 *
 * build/slots.lua and build/slots.json are generated from THIS file by
 * the Makefile (tools/gen_slots.py): the Lua probes dofile the one, the
 * Python checkers load the other. Nothing outside this file writes a slot
 * number.
 */
#ifndef SLOTS_H
#define SLOTS_H

#ifndef NSTARS
#define NSTARS 12                    /* the sky's dim stars (the Vectrex's 12) */
#endif
#define MIS_BEHIND_COUNT 20          /* NOBJ (5) x MIS_COLS_MAX (4): the missile
                                      * / bullet slots under the dome */
#define DOME_COUNT 11                /* DOME_COLS: the dome's columns */
#define SHIP_COUNT 2                 /* SHIP_COLS: the ship's columns */
#define MIS_FRONT_COUNT 20           /* NOBJ (5) x MIS_COLS_MAX (4): over the
                                      * dome, the overlays and the ship */
#define EXPL_COUNT 8                 /* NEXPL (2) x EXPL_COLS (4) */
#define RADAR_COUNT 19               /* Task 4: 4 frame + 3 x (1 stick + 4
                                      * heading) */

/* the starts — everything after this is derived, never a bare number */
#define STAR_SPRITE 1
#define MIS_BEHIND_SPRITE (STAR_SPRITE + NSTARS)
#define DOME_SPRITE (MIS_BEHIND_SPRITE + MIS_BEHIND_COUNT)
#define BROKEN_SLOT_BASE (DOME_SPRITE + DOME_COUNT)
#define BROKEN_SLOT_COUNT 145        /* render_broken's pack span today (the
                                      * 76 cells' widest pictures, 44..188) */
#define BROKEN_SLOT_AFTER (BROKEN_SLOT_BASE + BROKEN_SLOT_COUNT)
#define SHIP_SPRITE (BROKEN_SLOT_AFTER)
#define MIS_FRONT_SPRITE (SHIP_SPRITE + SHIP_COUNT)
#define EXPL_SPRITE (MIS_FRONT_SPRITE + MIS_FRONT_COUNT)
#define RADAR_SPRITE (EXPL_SPRITE + EXPL_COUNT)

#endif
