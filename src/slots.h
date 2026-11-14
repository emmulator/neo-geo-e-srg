/* slots.h: THE sprite slot map — the only place slot numbers are defined
 * (M5 Task 1). A higher slot draws on top (neo-geo-dev, "Sprite drawn
 * behind something it should cover").
 *
 * The map, in draw order (low to high):
 *
 *     1..20            the ground (GROUND_COUNT 20, the LOWEST sprites —
 *                      every other sprite draws over it). Dome-scenery
 *                      Task 5 moved the whole map up by 20: the grass must
 *                      be under everything, so it takes the bottom of the
 *                      range and the missiles behind the dome start after
 *                      it, not at 1.
 *     21..41           the mountains (MTN_COUNT 21, right after the ground:
 *                      they draw over nothing but the grass, and under
 *                      everything else, the missiles behind the dome
 *                      included). Dome-scenery Task 6 moved the whole map
 *                      up by 21: the mountain band is scenery on the
 *                      horizon, so it sits above the grass and below every
 *                      sprite.
 *     42..62           the band of towns and forests (BAND_COUNT 21, right
 *                      after the mountains and before the back props: it
 *                      draws over the mountains and under every prop).
 *                      Dome-scenery Task 17 moved the whole map up by 21.
 *     63..118          the BACK props (PROP_BACK_COUNT 56, right after the
 *                      band: every tree and rock whose foot is behind the
 *                      dome's centre, so they draw over the ground, the
 *                      mountains and the band and under everything else —
 *                      the missiles behind the dome included). Dome-scenery
 *                      Task 12 moved them here (51 columns then); Task 15
 *                      split them from the front pool and moved the whole
 *                      map up by 6; the shadow task's
 *                      tree (10-25) added 6 more back columns.
 *     119..133         missiles behind the dome (MIS_BEHIND_COUNT 15)
 *     134..139         the BACK smoke (SMOKE_BACK_COUNT 6, the three pairs
 *                      of plumes whose feet are on the far side of the ruin
 *                      at this angle), right below the dome so the ruin's
 *                      columns draw over them.
 *     140..147         the dome's 8 columns (sticky chain; the ruin's views)
 *     148..257         broken-window overlays (BROKEN_SLOT_COUNT 110, the
 *                      generator's span today — tools/render_broken.py; a
 *                      change there must update BROKEN_SLOT_COUNT, and
 *                      tests/test_slots.py proves the two agree). During a
 *                      dome death the overlays are hidden once, and the
 *                      collapse owns the range (Task C2): the FRONT smoke,
 *                      fragments, the fireball and the puffs, in that draw
 *                      order, all inside it. The sub-map's end must stay <=
 *                      BROKEN_SLOT_AFTER (a #error enforces it).
 *     252..253         the ship
 *     254..259         the FRONT props (PROP_FRONT_COUNT 6). Dome-scenery
 *                      Task 15: a near prop in front of the dome's centre
 *                      whose crown or stone covers the dome on screen draws
 *                      here — over the dome, its broken overlays and the
 *                      ship (10-26: such a prop's foot is always nearer the
 *                      camera than the ship wherever the two overlap, so it
 *                      covers the ship), and under the console, the front
 *                      missiles, the explosions and the radar. A prop that
 *                      changes pool leaves its old slots hidden (SCB3 0).
 *     260..279         the console (CON_COUNT 20, one sprite per column —
 *                      not a sticky chain). Dome-scenery Task 7 put it right
 *                      after the ship and before the front missiles: it
 *                      draws over the grass, the mountains, the band, the
 *                      dome, its overlays and the ship, and UNDER the front
 *                      missiles, the explosions and the radar (missiles fly
 *                      across the bottom of the screen; the console must
 *                      never hide one).
 *     280..294         front missiles (MIS_FRONT_COUNT 15)
 *     295..300         explosions (EXPL_COUNT 6)
 *     301..319         the radar (RADAR_COUNT 19: 4 frame + 3 x (1 stick +
 *                      4 heading))
 *     320..357         the high-score initials ring (RING_COUNT 38: the 37
 *                      glyph positions + the blinking pointer), the highest
 *                      sprites on screen, so the front letter draws over
 *                      the ring's other letters (high-score boards Task B6)
 *     FLY_SPRITE       the flying letter (FLY_COUNT 1, K2), right after the
 *                      ring: one copy of a picked letter in flight, above
 *                      the ring's front letter so it draws over it
 *
 * The last slot is <= 380 (381 sprites total).
 *
 * Every range starts where the one before it ended: each start below is
 * the previous start plus the previous count, so changing a count moves
 * everything after it. The counts themselves are the art's real numbers,
 * written here with their sources in comments; tests/test_slots.py proves
 * each equals the constant it names (GROUND_COLS, NOBJ x MIS_COLS_MAX,
 * DOME_COLS, ...) every build, so a drift fails the gate instead of
 * silently shifting the map.
 *
 * Dome-scenery Task 4 retired the star field: the stars' 1..12 range is
 * gone. Dome-scenery Task 5 put the ground under everything: the map now
 * starts at slot 1 with the ground, and the missiles behind the dome
 * follow it. Dome-scenery Task 6 put the mountains right after the ground.
 * Dome-scenery Task 7 put the console right after the ship. Dome-scenery
 * Task 12 put the props right after the mountains: one pool over the grass
 * and the mountains, under the missiles behind the dome. Dome-scenery
 * Task 15 split the props into a back pool there (50 columns) and a front
 * pool right after the broken overlays (6 columns), so a near tree that
 * covers the dome draws over it and under the ship. Dome-scenery Task 17
 * put the towns-and-forests band right after the mountains and before the
 * back props, moving the whole map up by 21.
 *
 * build/slots.lua and build/slots.json are generated from THIS file by
 * the Makefile (tools/gen_slots.py): the Lua probes dofile the one, the
 * Python checkers load the other. Nothing outside this file writes a slot
 * number.
 */
#ifndef SLOTS_H
#define SLOTS_H

/* DOME_COLS: the dome's sprite columns, from the one size knob in
 * tools/geometry.py, through the header tools/render_dome.py generates
 * (build/dome_map.h). Every other header here includes slots.h before its
 * own generated map, and dome_map.h's include guard keeps the duplicate
 * include harmless; the Makefile generates build/dome_map.h before the
 * slot map (tools/gen_slots.py) is evaluated, so DOME_COUNT can be
 * written in terms of DOME_COLS. */
#include "dome_map.h"

/* GROUND_COUNT: GROUND_COLS from tools/render_scenery.py, through its
 * header build/ground_map.h (the art's own number, 20). The generated
 * header is not a prerequisite of the slot-map rule, so the count is
 * written here with its one source and tests/test_slots.py proves it
 * equals build/ground_map.h's GROUND_COLS (the same pattern the other
 * art counts use). */
#define GROUND_COUNT 20              /* GROUND_COLS: the ground's columns */
#define MTN_COUNT 21                 /* MTN_SHOWN: the mountain band's columns
                                      * (21 x 16 = 336 px covers the screen at
                                      * any 16-px scroll phase) */
#define BAND_COUNT 21                /* BAND_SHOWN: the towns-and-forests
                                      * band's columns (21 x 16 = 336 px
                                      * covers the screen at any 16-px scroll
                                      * phase). Dome-scenery Task 17; the band
                                      * draws over the mountains and under
                                      * every prop. */
#define PROP_BACK_COUNT 56            /* PROP_BACK_SLOTS from tools/render_props.py,
                                      * through its header build/props_map.h
                                      * (the most columns the back pool uses
                                      * at any angle, 56). The back props draw
                                      * over the grass and the mountains and
                                      * under everything else (the missiles
                                      * behind the dome included). Dome-scenery
                                      * Task 12, split from the front pool by
                                      * Task 15. The generated header is not a
                                      * prerequisite of the slot-map rule, so
                                      * the count is written here with its one
                                      * source and tests/test_slots.py proves
                                      * it equals build/props_map.h's
                                      * PROP_BACK_SLOTS (the same pattern the
                                      * other art counts use). */
#define PROP_FRONT_COUNT 6            /* PROP_FRONT_SLOTS from tools/render_props.py,
                                      * through its header build/props_map.h:
                                      * the most columns the front pool uses at
                                      * any angle (6). Right after the broken
                                      * overlays and before the ship, so the
                                      * near tree that covers the dome draws
                                      * over the dome and its overlays and
                                      * under the ship. Dome-scenery Task 15;
                                      * tests/test_slots.py proves it equals
                                      * PROP_FRONT_SLOTS. */
#define MIS_BEHIND_COUNT 15          /* NOBJ (5) x MIS_COLS_MAX (3): the missile
                                      * / bullet slots under the dome */
#define SMOKE_BACK_COUNT 6           /* 3 back plume pairs x SMOKE_COLS (2):
                                      * the plumes whose feet are behind the
                                      * ruin at this angle; they sit right
                                      * below DOME_SPRITE, so the ruin's own
                                      * columns draw over them. */
#define DOME_COUNT DOME_COLS         /* the dome's columns: geometry.py's knob */
#define SHIP_COUNT 2                 /* SHIP_COLS: the ship's columns */
#define CON_COUNT 20                 /* CON_COLS from tools/render_console.py,
                                      * through its header build/console_map.h
                                      * (the art's own number, 20: one sprite
                                      * per column, never a sticky chain). The
                                      * generated header is not a prerequisite
                                      * of the slot-map rule, so the count is
                                      * written here with its one source and
                                      * tests/test_slots.py proves it equals
                                      * build/console_map.h's CON_COLS (the
                                      * same pattern the other art counts use). */
#define MIS_FRONT_COUNT 15           /* NOBJ (5) x MIS_COLS_MAX (3): over the
                                      * dome, the overlays and the ship */
#define EXPL_COUNT 6                 /* NEXPL (2) x EXPL_COLS (3) */
#define RADAR_COUNT 19               /* Task 4: 4 frame + 3 x (1 stick + 4
                                      * heading) */

/* the starts — everything after this is derived, never a bare number */
#define GROUND_SPRITE 1
#define MTN_SPRITE (GROUND_SPRITE + GROUND_COUNT)
#define BAND_SPRITE (MTN_SPRITE + MTN_COUNT)
#define PROP_SPRITE (BAND_SPRITE + BAND_COUNT)
#define MIS_BEHIND_SPRITE (PROP_SPRITE + PROP_BACK_COUNT)
#define SMOKE_BACK_SPRITE (MIS_BEHIND_SPRITE + MIS_BEHIND_COUNT)
#define DOME_SPRITE (SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT)
#define BROKEN_SLOT_BASE (DOME_SPRITE + DOME_COUNT)
#define BROKEN_SLOT_COUNT 110        /* render_broken's pack span today (the
                                      * 76 cells' widest pictures, 24..133;
                                      * 145 at the full box's 11x8, dome-
                                      * scenery Task 2's 2/3 is 110) */
#define BROKEN_SLOT_AFTER (BROKEN_SLOT_BASE + BROKEN_SLOT_COUNT)

/* Task C2: the collapse's sub-map, inside the overlays' range (the
 * overlays are hidden for the whole collapse, so these slots are free).
 * In draw order, low to high — the FRONT smoke under the fragments, the
 * fragments under the fireball, the fireball under the puffs. The BACK
 * smoke is outside this range, below DOME_SPRITE. The counts are the
 * generated collapse header's (build/collapse_map.h): the counts are
 * written here with their source, the way the other art counts are, and
 * the generated header is not a prerequisite of the slot-map rule, so
 * tests/test_slots.py proves each equals the header's. A higher collapse
 * sprite draws on top: the front plumes rise from the ruin in front of the
 * glass, the fireball grows over both, the puffs sit on top during the
 * shake. */
#define COLLAPSE_SMOKE_SPRITE BROKEN_SLOT_BASE
#define COLLAPSE_SMOKE_COUNT 6       /* 3 front plume pairs x SMOKE_COLS (2) */
#define COLLAPSE_FRAG_SPRITE (COLLAPSE_SMOKE_SPRITE + COLLAPSE_SMOKE_COUNT)
#define COLLAPSE_FRAG_COUNT 49       /* NFRAGS (49 in V2's generator) */
#define COLLAPSE_FIRE_SPRITE (COLLAPSE_FRAG_SPRITE + COLLAPSE_FRAG_COUNT)
#define COLLAPSE_FIRE_COUNT 12       /* FIRE_COLS */
#define COLLAPSE_PUFF_SPRITE (COLLAPSE_FIRE_SPRITE + COLLAPSE_FIRE_COUNT)
#define COLLAPSE_PUFF_COUNT 6        /* 3 puff pairs x PUFF_COLS (2): at most
                                      * 3 puffs at once, puff n in pair n%3 */
#if COLLAPSE_PUFF_SPRITE + COLLAPSE_PUFF_COUNT > BROKEN_SLOT_AFTER
#error "the collapse sub-map does not fit the broken overlays' range"
#endif

#define SHIP_SPRITE (BROKEN_SLOT_AFTER)
#define PROP_FRONT_SPRITE (SHIP_SPRITE + SHIP_COUNT)
#define CON_SPRITE (PROP_FRONT_SPRITE + PROP_FRONT_COUNT)
#define MIS_FRONT_SPRITE (CON_SPRITE + CON_COUNT)
#define EXPL_SPRITE (MIS_FRONT_SPRITE + MIS_FRONT_COUNT)
#define RADAR_SPRITE (EXPL_SPRITE + EXPL_COUNT)
#define RING_COUNT 38                /* RING_N (37 glyph positions) + the
                                      * pointer tile (build/ring_map.h
                                      * RING_TILES/RING_POINTER); high-score
                                      * boards Task B6, above the radar: the
                                      * ring's front letter is the highest
                                      * slot and draws over the other
                                      * letters. */
#define RING_SPRITE (RADAR_SPRITE + RADAR_COUNT)
#define FLY_COUNT 1                  /* K2: one flying letter's copy */
#define FLY_SPRITE (RING_SPRITE + RING_COUNT)  /* right after the ring */

#endif
