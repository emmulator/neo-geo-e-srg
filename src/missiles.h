/* missiles.h: enemy missiles and the player's bullets, ported from the
 * Vectrex game (e-srg.c spawn/fire/collide/missiles_update, missile_draw.s
 * missiles_step) v1.1.0: the target rings open at LOW_RINGS_AT kills or
 * LOW_RINGS_AT hits on the dome that broke a whole cell (#1), and EASY's
 * missiles fly at 0.75x (mis_dr_easy). Pure logic, no hardware: tests/
 * builds it on the host too.
 *
 * A missile flies a straight line through a cell's centre toward the centre
 * of the sphere the dome is cut from, fixed in the dome's frame; it is just
 * its ring and azimuth (the cell's) and its distance r from the centre
 * (2^-19 radii). A bullet flies the same kind of line outward from the
 * ship's cell, so it can only meet missiles aimed at that cell: it hits one
 * when their distances cross. */
#ifndef MISSILES_H
#define MISSILES_H
#include <ngdevkit/neogeo.h>
#include "ship.h"

#ifndef RULES_H                        /* rules_t comes from rules.h when both are used */
struct rules_t;                        /* (a voider here would not be the same type) */
typedef struct rules_t rules_t;
#endif

#define NMIS 3                  /* missile slots: obj[0 .. NMIS-1] */
#define NBUL 2                  /* bullet slots: obj[NMIS .. NOBJ-1] */
#define NOBJ (NMIS + NBUL)
#define KIND_MISSILE 0
#define KIND_BULLET  1

/* the Vectrex's rules (e-srg.c), frame counts x 59/50 */
#define WAVE_RINGS    5         /* targets in rings 0..4 (up to 34 deg) ... */
#define LOW_RINGS_AT  6         /* ... and in every ring from this many kills on,
                                 * or from this many missiles that hit the dome,
                                 * each breaking a whole cell (e-srg.c v1.0.1:
                                 * hits++ in break_tile after its is_broken early
                                 * return), whichever comes first. A missile
                                 * landing on a cell that broke after it launched
                                 * does not count. The count resets where kills
                                 * does, at a new game. */
#define WAVE_LIVE     2         /* at most this many missiles at once */
#define SPAWN_FIRST   59        /* frames to the first launch (the Vectrex's 50) */
#define SPAWN_GAP     40        /* then (SPAWN_GAP + 0..63) x 59/50 between launches */
#define RNG_SEED      0xACE1
#define SCORE_MAX     9999999UL /* score / 10 */

/* M7: the frame's sound events, a bitmask in mis_t.sfx (missiles.h): fire
 * — a bullet left this frame; hit — a missile was shot down (nhit > 0,
 * also off screen); crack — a landing broke a fresh cell. The models set
 * the same bits at the same frames; flow.c turns them into the sound
 * commands after the frame's logic, with the Vectrex's same-frame rule
 * (a crack takes channel C over a hit: e-srg.c's `if (snd_hit && snd_crack)
 * snd_crack = 0` — the opposite of the play order). */
#define SFX_FIRE  1
#define SFX_HIT   2
#define SFX_CRACK 4

typedef struct {
    u8 state;                   /* 0 free, 1 flying, 2 just reached the dome */
    u8 kind;                    /* KIND_MISSILE or KIND_BULLET */
    u8 ring, phi;               /* its cell's ring and azimuth (rotation steps) */
    u8 life;                    /* bullet: frames left */
    s32 r;                      /* distance from the sphere's centre, 2^-19 radii */
    s32 dr;                     /* per frame: missiles subtract, bullets add */
} mis_obj_t;

typedef struct {
    u8 ring, phi;               /* where a missile was shot down ... */
    s32 r;                      /* ... and how far out */
} mis_hit_t;

typedef struct {
    mis_obj_t obj[NOBJ];
    u16 rng;                    /* xorshift16, as on the Vectrex */
    u8 spawn_timer;             /* frames until the next launch */
    u8 level;                   /* LEVEL_EASY / LEVEL_NORMAL / LEVEL_HARD:
                                 * EASY's missiles fly at 0.75x (mis_dr_easy);
                                 * set with the rules' level at a new game */
    u8 kills;                   /* missiles shot down (stops at 255) */
    u8 dome_hits;               /* missiles that hit the dome this game, each
                                 * breaking a whole cell (stops at 255; opens
                                 * the targets with kills: LOW_RINGS_AT, see
                                 * above). Resets with kills. */
    u32 score10;                /* score / 10 */
    u8 integ_pct;               /* dome integrity: a kill scores this (M4 lowers it) */
    u8 fire_req;                /* A pressed: fire once the ship rests */
    u8 nhit;                    /* this frame: missiles shot down ... */
    mis_hit_t hit[NMIS];
    u8 nland;                   /* ... and cells missiles reached (M4: cracks) */
    u8 land_cell[NMIS];
    u8 sfx;                     /* M7: this frame's sound events: SFX_FIRE |
                                 * SFX_HIT | SFX_CRACK (see above), cleared at
                                 * the frame's start */
} mis_t;

/* the seed a new game starts the missile RNG from, given the number of title
 * frames the title has been up when Start was pressed: RNG_SEED ^ frames,
 * and RNG_SEED instead if that is 0 — xorshift16 never leaves 0, so a 0 seed
 * would launch every missile at cell 0 forever. Pure, 16-bit: no library
 * calls in game_begin's per-Start path. */
u16 mis_seed_from(u16 frames);

void mis_reset(mis_t *m);
/* once per frame, after ship_frame: pressed = bios_p1change (A = fire) */
void mis_frame(mis_t *m, const ship_t *s, u8 pressed);
/* the game's update (e-srg.c game_step + missiles_update): the fire
 * handling, the missiles' step and collide, the landings (through the
 * rules), and the launches. busy is rules_begin's return: while it is 1
 * (GAME OVER, a dead ship's countdown, even the frame it came back) the
 * fire branch is skipped — and launches are too, while the ship is gone
 * (e-srg.c's `if (dead_t || game_over) return`), with the spawn timer
 * counting only then. Call once per frame between rules_begin and
 * rules_end; pressed = bios_p1change (A = fire). */
void mis_update(mis_t *m, ship_t *s, rules_t *r, u8 pressed, u8 busy);
#endif
