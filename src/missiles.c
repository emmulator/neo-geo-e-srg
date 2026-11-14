/* missiles.c: see missiles.h. The comments name the Vectrex code each part ports. */
#include <ngdevkit/neogeo.h>
#include "missiles.h"
#include "rules.h"
#include "cells.h"
#include "missiles_tables.h"

/* missiles launch at mis_dr[k] from speed_score[k] (score / 10) on (e-srg.c);
 * EASY's missiles use mis_dr_easy, 0.75x of mis_dr (v1.1.0) */
static const u32 speed_score[MIS_SPEEDS] = { 0, 1000, 2500, 5000, 10000 };

static u8 rand8(mis_t *m)               /* e-srg.c rand8: xorshift16 */
{
    m->rng ^= (u16)(m->rng << 7);
    m->rng ^= (u16)(m->rng >> 9);
    m->rng ^= (u16)(m->rng << 8);
    return (u8)m->rng;
}

static u8 rand_below(mis_t *m, u8 n)
{
    u8 r = rand8(m);

    while (r >= n)
        r -= n;
    return r;
}

static u8 broken(const ship_t *s, u8 c)
{
    return (u8)(s->broken[c >> 3] & (1 << (c & 7)));
}

/* the RNG's seed from the title's time (missiles.h): RNG_SEED ^ frames, and
 * RNG_SEED instead if that is 0 (xorshift16 never leaves 0). The Vectrex
 * (1.1.0) seeded it once, at power-on; here a Start at a different title frame
 * starts a different missile sequence. */
u16 mis_seed_from(u16 frames)
{
    u16 s = (u16)(RNG_SEED ^ frames);

    return s ? s : RNG_SEED;
}

void mis_reset(mis_t *m)
{
    u8 i;

    for (i = 0; i < NOBJ; i++) {
        mis_obj_t *o = &m->obj[i];
        o->state = o->kind = o->ring = o->phi = o->life = 0;
        o->r = o->dr = 0;
    }
    m->rng = RNG_SEED;
    m->spawn_timer = SPAWN_FIRST;
    m->level = LEVEL_NORMAL;            /* until the rules set it at a new game */
    m->kills = 0;
    m->dome_hits = 0;
    m->score10 = 0;
    m->integ_pct = 100;
    m->fire_req = 0;
    m->nhit = m->nland = 0;
    m->sfx = 0;                          /* M7: no sound events on a fresh game */
}

/* e-srg.c free_target: whole, and no missile already aimed at it */
static u8 free_target(const mis_t *m, const ship_t *s, u8 c)
{
    u8 i;

    if (broken(s, c))
        return 0;
    for (i = 0; i < NMIS; i++)
        if (m->obj[i].state == 1 && m->obj[i].ring == mis_cell_ring[c]
            && m->obj[i].phi == mis_cell_phi[c])
            return 0;
    return 1;
}

/* e-srg.c spawn: a free cell in the rings the wave draws from. The target
 * rings open (to every ring) once this game has LOW_RINGS_AT kills or
 * LOW_RINGS_AT missiles that hit the dome, each breaking a whole cell
 * (mis_update counts only those landings; missiles.h) — the Vectrex
 * v1.0.1 rule (#1), which replaced this port's own 12-hits rule. The
 * random sequence, the 8 tries and everything else is as on the Vectrex. */
static void spawn(mis_t *m, const ship_t *s, mis_obj_t *o)
{
    const s32 *spd = m->level == LEVEL_EASY ? mis_dr_easy : mis_dr;
    u8 c, k = 8;                        /* a free cell in the wave's rings (a few tries) */

    do
        c = rand_below(m, mis_ring_end[(m->kills >= LOW_RINGS_AT
                                        || m->dome_hits >= LOW_RINGS_AT
                                        ? MIS_RINGS : WAVE_RINGS) - 1]);
    while (!free_target(m, s, c) && --k);
    if (!free_target(m, s, c))
        return;                         /* (none found this time) */
    o->ring = mis_cell_ring[c];
    o->phi = mis_cell_phi[c];
    o->r = mis_r_spawn[o->ring];
    k = MIS_SPEEDS - 1;
    while (m->score10 < speed_score[k])
        k--;
    o->dr = spd[k];
    o->kind = KIND_MISSILE;
    o->state = 1;
}

/* e-srg.c fire: along the ship's cell's line, outward (needs a free slot) */
static void fire(mis_t *m, u8 cell)
{
    mis_obj_t *b = m->obj + NMIS;
    u8 i;

    for (i = 0; i < NBUL && b->state; i++, b++)
        ;
    if (i == NBUL)
        return;
    b->ring = mis_cell_ring[cell];
    b->phi = mis_cell_phi[cell];
    b->r = BUL_R0;
    b->dr = BUL_DR;
    b->life = bul_life[b->ring];        /* until off screen, or on to the radar's */
    for (i = 0; i < NMIS; i++)          /* edge if a missile is on its line */
        if (m->obj[i].state == 1 && m->obj[i].ring == b->ring && m->obj[i].phi == b->phi)
            b->life = BUL_LIFE_FAR;
    b->kind = KIND_BULLET;
    b->state = 1;
    m->sfx |= SFX_FIRE;                  /* M7: a bullet left (sound: SND_FIRE) */
}

/* missile_draw.s missiles_step */
static void step(mis_t *m)
{
    mis_obj_t *o = m->obj;
    u8 i;

    for (i = 0; i < NOBJ; i++, o++) {
        if (o->state != 1)
            continue;
        if (o->kind == KIND_BULLET) {
            o->r += o->dr;
            if (--o->life == 0)         /* gone when its time is up */
                o->state = 0;
        } else {
            o->r -= o->dr;
            if (o->r <= MIS_R_LAND)     /* reached the dome */
                o->state = 2;
        }
    }
}

static void add_score(mis_t *m, u8 v)
{
    m->score10 += v;
    if (m->score10 > SCORE_MAX)
        m->score10 = SCORE_MAX;
}

/* e-srg.c collide: a bullet meets a missile on its line once their
 * distances cross (bullet r, outward, >= missile r, inward) */
static void collide(mis_t *m)
{
    mis_obj_t *b = m->obj + NMIS, *o;
    u8 i, j;

    for (i = 0; i < NBUL; i++, b++) {
        if (b->state != 1)
            continue;
        for (j = 0, o = m->obj; j < NMIS; j++, o++) {
            if (o->state != 1 || o->phi != b->phi || o->ring != b->ring)
                continue;
            if (b->r >= o->r) {
                m->hit[m->nhit].ring = o->ring;
                m->hit[m->nhit].phi = o->phi;
                m->hit[m->nhit].r = o->r;
                m->nhit++;
                if (m->kills != 255)
                    m->kills++;
                add_score(m, m->integ_pct);     /* 1000 points x integrity */
                m->sfx |= SFX_HIT;              /* M7: a missile shot down
                                                 * (sound: SND_HIT; also off
                                                 * screen, as the Vectrex) */
                o->state = 0;
                b->state = 0;
                break;
            }
        }
    }
}

/* e-srg.c break_tile's lookup: the cell in its ring at its azimuth */
static u8 cell_at(u8 ring, u8 phi)
{
    u8 c = ring ? mis_ring_end[ring - 1] : 0;

    while (mis_cell_phi[c] != phi)
        c++;
    return c;
}

/* e-srg.c game_step's handling of a newly pressed A: fire once the ship
 * rests (the request is set on the press, the shot comes from a cell
 * centre; while the ship is dead the request waits, the Vectrex's on the
 * same latch) */
static void press_fire(mis_t *m, const ship_t *s, u8 pressed)
{
    if (pressed & CNT_A)
        m->fire_req = 1;
    if (m->fire_req && !s->move_left) {  /* only from a cell centre */
        fire(m, s->cell);
        m->fire_req = 0;
    }
}

/* e-srg.c game_step's fire + missiles_update, with the death checks the
 * game runs each frame: everything in flight is cleared on a death, and no
 * launches happen while the ship is dead or the game over (and the spawn
 * timer does not count down then: e-srg.c's `if (dead_t || game_over)
 * return`). busy is what rules_begin returned: while it is 1 (GAME OVER, a
 * dead ship's countdown, or the very frame it came back) the Vectrex's
 * fire branch does not run — the fire request is not even latched then —
 * so press_fire is skipped; the missiles still step and land and the timer
 * still counts (on the respawn frame it can launch again). Missiles that
 * reach the dome break their cells through the rules. Use between
 * rules_begin and rules_end. */
void mis_update(mis_t *m, ship_t *s, rules_t *r, u8 pressed, u8 busy)
{
    mis_obj_t *o;
    u8 i, live = 0;

    m->sfx = 0;                          /* M7: the frame's events, cleared at
                                          * the frame's start and gathered by
                                          * press_fire / collide / the landings */
    if (!busy)
        press_fire(m, s, pressed);
    m->nhit = m->nland = 0;
    step(m);
    collide(m);
    for (i = 0, o = m->obj; i < NMIS; i++, o++) {
        if (o->state == 2) {             /* reached the dome: its cell breaks */
            u8 broke;
            m->land_cell[m->nland++] = cell_at(o->ring, o->phi);
            broke = rules_break_cell(r, s, m->land_cell[m->nland - 1]);
            if (broke && m->dome_hits != 255) {  /* broke a whole cell: count it (the
                                                  * v1.0.1 hits rule; a landing on a
                                                  * cell that broke after the missile
                                                  * launched does not count) */
                m->dome_hits++;
                m->sfx |= SFX_CRACK;     /* M7: a missile broke a fresh cell
                                          * (sound: SND_CRACK) */
            }
            o->state = 0;
        }
        if (o->state)
            live++;
    }
    if (r->dead_t || r->game_over)
        return;                          /* (no launches while the ship is gone) */
    if (m->spawn_timer) {
        m->spawn_timer--;
        return;
    }
    if (live >= WAVE_LIVE)
        return;
    for (o = m->obj; o->state; o++)
        ;
    spawn(m, s, o);
    m->spawn_timer = (u8)(((SPAWN_GAP + (rand8(m) & 63)) * 59 + 25) / 50);
}

/* the M3 frame (kept for the M3 tests): fire + step + collide + land, then
 * launches. The game itself runs mis_update, which routes the landings
 * through the rules (the cracks) and honours the dead/game-over states.
 * mis_frame has no rules and no broken set, so every landing counts as a
 * dome hit (it cannot know whether the cell broke); it opens at
 * LOW_RINGS_AT too. */
void mis_frame(mis_t *m, const ship_t *s, u8 pressed)
{
    mis_obj_t *o;
    u8 i, live = 0;

    m->sfx = 0;                          /* M7: the frame's events, cleared at
                                          * the frame's start and gathered by
                                          * press_fire / collide / the landings */
    press_fire(m, s, pressed);
    m->nhit = m->nland = 0;
    step(m);
    collide(m);
    for (i = 0, o = m->obj; i < NMIS; i++, o++) {
        if (o->state == 2) {            /* reached the dome: its cell is hit */
            m->land_cell[m->nland++] = cell_at(o->ring, o->phi);
            if (m->dome_hits != 255)    /* a missile hit the dome: count it
                                         * (every landing — see above) */
                m->dome_hits++;
            if (!broken(s, m->land_cell[m->nland - 1]))
                m->sfx |= SFX_CRACK;    /* M7: hit a fresh cell — the sound
                                         * event (mis_frame counts every
                                         * landing as a hit, but the Vectrex's
                                         * crack only sounds on a fresh
                                         * break; the model's frame() uses
                                         * the same fresh check) */
            o->state = 0;
        }
        if (o->state)
            live++;
    }
    if (m->spawn_timer) {
        m->spawn_timer--;
        return;
    }
    if (live >= WAVE_LIVE)
        return;
    for (o = m->obj; o->state; o++)
        ;
    spawn(m, s, o);
    m->spawn_timer = (u8)(((SPAWN_GAP + (rand8(m) & 63)) * 59 + 25) / 50);
}
