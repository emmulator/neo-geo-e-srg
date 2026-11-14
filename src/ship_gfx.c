/* ship_gfx.c: see ship_gfx.h. The ship is never shrunk, so its two columns
 * are a sticky chain; a new (heading, lat, frame) rewrites their SCB1 tiles,
 * the lift only moves the chain's Y. The 8 headings are in build/ship_map.h's
 * ship_anim_tile (heading h = ship_dir / 4) and their sprite y in ship_oy;
 * ship_frame_of chooses the picture from the ship's state (the design's
 * timing), and prepare/commit write it in vblank, so the ship's slots never
 * tear. */
#include <ngdevkit/neogeo.h>
#include "ship_gfx.h"
#include "dome.h"
#include "ship_map.h"

static const u16 ship_pal[16] =
#include "assets/ship.pal"
;

/* the last prepared SCB1 picture (heading, lat, frame): 255 = never, so the
 * first show writes the tiles. */
static u8 prev_heading = 255;
static u8 prev_lat = 255;
static u8 prev_frame = 255;

/* the heading on screen (the last prepared/show one): the death explosion's
 * centre uses it (Review Focus: the ship explodes where it was drawn). */
static u8 shown_heading = 1;

/* the animation state the frame choice carries from frame to frame. */
static ship_anim_t anim;

/* the staged writes: the SCB1 tile list (only when (heading, lat, frame)
 * changed), the driver's SCB3 word (every prepared frame: the lift moves), and
 * a pending hide (a death; SCB3 height 0). */
static u8 pend_tiles;
static u8 pend_place;
static u8 pend_hide;
static u8 pend_heading;
static u8 pend_lat;
static u8 pend_frame;
static u16 pend_scb3;

/* the ship is hidden (or a hide is staged): prepare/show clear it. */
static u8 hidden;

void ship_anim_rest(ship_anim_t *a)
{
    a->walk_t = 0;
    a->heave_t = SHIP_HEAVE_NONE;
    a->was_moving = 0;
    a->was_move = 0;
}

/* the jump's four poses over SHIP_JUMP_FRAMES (28): scrunch 0..6,
 * launch 7..10, airborne 11..20, land 21..27. */
static u8 jump_frame(u8 t)
{
    if (t <= 6)
        return SHIP_F_JUMP;
    if (t <= 10)
        return (u8)(SHIP_F_JUMP + 1);
    if (t <= 20)
        return (u8)(SHIP_F_JUMP + 2);
    return (u8)(SHIP_F_JUMP + 3);
}

u8 ship_frame_of(const ship_t *s, u8 shot, ship_anim_t *a)
{
    u8 move = (u8)(s->move_left != 0);
    u8 moving = (u8)(move || s->spinning);
    u8 jump = (u8)(move && s->mlen == SHIP_JUMP_FRAMES);
    u8 walk_end = (u8)(!moving && a->was_move
                       && s->mlen == SHIP_MOVE_FRAMES);

    /* a shot leaves the frame: the heave starts at once, over the landing
     * frame's REST (Review Focus 2) and over the move-end walk picture. */
    if (shot) {
        a->heave_t = 0;
        a->was_moving = moving;
        a->was_move = move;
        return SHIP_F_HEAVE;
    }

    /* the heave advances on the frames after the shot: 4 pictures of 3
     * game frames each, then idle. */
    if (a->heave_t != SHIP_HEAVE_NONE) {
        if (++a->heave_t >= SHIP_HEAVE_FRAMES)
            a->heave_t = SHIP_HEAVE_NONE;
    }

    if (moving) {
        if (!a->was_moving)
            a->walk_t = 0;               /* a move/step's first frame */
        else if (a->walk_t < SHIP_MOVE_FRAMES)
            a->walk_t++;
        a->heave_t = SHIP_HEAVE_NONE;    /* walking interrupts a heave: the
                                          * design's "a heave never overlaps
                                          * a walk or a jump" */
    } else if (walk_end) {
        /* the frame a move ends: keep the last walk picture, so a jump that
         * starts next frame goes walk -> scrunch with no REST between
         * (Review Focus 1). */
        if (a->walk_t < SHIP_MOVE_FRAMES)
            a->walk_t++;
    } else {
        a->walk_t = 0;
    }
    a->was_moving = moving;
    a->was_move = move;

    if (jump) {
        u8 t = (u8)(SHIP_JUMP_FRAMES - s->move_left);

        return jump_frame(t);
    }
    if (moving || walk_end) {
        u8 t = a->walk_t;

        if (t >= SHIP_MOVE_FRAMES)
            t = SHIP_MOVE_FRAMES - 1;    /* the move-end frame: last walk */
        return (u8)(SHIP_F_WALK + (u8)((t * 4) / SHIP_MOVE_FRAMES));
    }
    if (a->heave_t != SHIP_HEAVE_NONE)
        return (u8)(SHIP_F_HEAVE + (u8)(a->heave_t / 3));
    return SHIP_F_REST;
}

void ship_gfx_init(void)
{
    u8 i, c;

    for (i = 0; i < 16; i++)
        MMAP_PALBANK1[PAL_SHIP * 16 + i] = ship_pal[i];
    MMAP_PALBANK1[PAL_SHIP * 16] = 0x8000;       /* entry 0: transparent */

    *REG_VRAMMOD = 0x200;                         /* SCB2 -> SCB3 -> SCB4 */
    for (c = 0; c < SHIP_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB2 + SHIP_SPRITE + c;
        *REG_VRAMRW = 0x0fff;                     /* full size */
        if (c == 0) {
            *REG_VRAMRW = (u16)(((496 - DOME_Y) << 7) | SHIP_ROWS);   /* ship_gfx_prepare sets Y */
            *REG_VRAMRW = (u16)((DOME_X + SHIP_OX) << 7);
        } else {
            *REG_VRAMRW = 1 << 6;                 /* sticky: follows column c-1 */
            /* the sticky column's own SCB4 is read by nothing (it inherits
             * the driver's X), but write its box X anyway, like the dome:
             * the VRAM then holds the whole ship deterministically, so the
             * respawn boot-test can prove "the respawned ship's VRAM words
             * equal the start of the game's" word for word (an un-written
             * SCB4 would carry whatever the BIOS init left in VRAM — a
             * value the test could only accidentally agree on). */
            *REG_VRAMRW = (u16)((DOME_X + SHIP_OX + (s16)c * 16) << 7);
        }
    }
    ship_anim_rest(&anim);
    prev_heading = prev_lat = prev_frame = 255;
    shown_heading = 1;                   /* a fresh game/respawn: up-right */
    pend_tiles = pend_place = pend_hide = 0;
    hidden = 0;
}

/* write the ship's SCB1 picture from the committed (heading, lat, frame)
 * memo */
static void write_tiles(u8 heading, u8 lat, u8 frame)
{
    u8 c, r;

    *REG_VRAMMOD = 1;
    for (c = 0; c < SHIP_COLS; c++) {
        *REG_VRAMADDR = ADDR_SCB1 + (SHIP_SPRITE + c) * 64;
        for (r = 0; r < SHIP_ROWS; r++) {
            *REG_VRAMRW = ship_anim_tile[heading][lat][frame][c][r];
            *REG_VRAMRW = (u16)(PAL_SHIP << 8);
        }
    }
}

static u16 scb3_for(u8 heading, u8 lat, u8 lift)
{
    s16 y = (s16)(DOME_Y + ship_oy[heading][lat] - lift);

    return (u16)(((496 - y) << 7) | SHIP_ROWS);
}

void ship_gfx_prepare(const ship_t *s, u8 shot)
{
    u8 heading = s->heading;
    u8 frame = ship_frame_of(s, shot, &anim);

    if (heading != prev_heading || s->lat != prev_lat || frame != prev_frame) {
        pend_tiles = 1;
        pend_heading = heading;
        pend_lat = s->lat;
        pend_frame = frame;
        prev_heading = heading;         /* the memo is what commit will write */
        prev_lat = s->lat;
        prev_frame = frame;
    }
    shown_heading = heading;
    pend_scb3 = scb3_for(heading, s->lat, s->lift);
    pend_place = 1;
    pend_hide = 0;
    hidden = 0;
}

void ship_gfx_commit(void)
{
    if (pend_hide) {
        *REG_VRAMMOD = 1;
        *REG_VRAMADDR = ADDR_SCB3 + SHIP_SPRITE;
        *REG_VRAMRW = 0;
        pend_hide = 0;
        return;
    }
    if (!pend_place)
        return;
    if (pend_tiles) {
        write_tiles(pend_heading, pend_lat, pend_frame);
        pend_tiles = 0;
    }
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = ADDR_SCB3 + SHIP_SPRITE;
    *REG_VRAMRW = pend_scb3;
    pend_place = 0;
}

void ship_gfx_show(u8 lat, u8 lift, u8 frame)
{
    u8 heading = shown_heading;          /* a fresh game's 1 (init sets it) */

    if (heading != prev_heading || lat != prev_lat || frame != prev_frame) {
        write_tiles(heading, lat, frame);
        prev_heading = heading;
        prev_lat = lat;
        prev_frame = frame;
    }
    *REG_VRAMMOD = 1;
    *REG_VRAMADDR = ADDR_SCB3 + SHIP_SPRITE;
    *REG_VRAMRW = scb3_for(heading, lat, lift);
    pend_tiles = pend_place = pend_hide = 0;
    hidden = 0;
}

void ship_gfx_anim_reset(void)
{
    ship_anim_rest(&anim);
}

/* hide the ship (SCB3 height 0): the Vectrex stops drawing it while it is
 * dead (e-srg.c: if (!dead_t && !game_over) ship_draw). The hide is staged
 * for the next vblank (so it cannot tear the ship's slots), and the
 * animation resets to REST: the respawned ship shows REST, not the pose it
 * died in (Review Focus 3).
 * Only the sticky chain's DRIVER is hidden (SCB3 = 0 on column 0): the
 * follower's SCB3 (the sticky bit 1<<6 and inherited height) is left
 * intact, so the chain survives the hide and the ship comes back whole.
 * (Zeroing the follower too would clear its sticky bit; a later show
 * rewrites only the driver's SCB3, and the follower would stay a
 * non-sticky sprite with height 0 — the "only the left half" bug.) */
void ship_gfx_hide(void)
{
    ship_anim_rest(&anim);
    if (hidden)
        return;
    pend_hide = 1;
    pend_tiles = 0;
    pend_place = 0;
    prev_heading = prev_lat = prev_frame = 255;  /* force a full redraw on show */
    hidden = 1;
}

/* the centre of the ship's 2 x 2-tile picture at rest (no lift) at view
 * lat, heading shown: where its death explosion goes (e-srg.c kill_ship:
 * explode_at the ship's spot) */
void ship_gfx_centre(u8 lat, s16 *x, s16 *y)
{
    *x = (s16)(DOME_X + SHIP_OX + SHIP_COLS * 8);
    *y = (s16)(DOME_Y + ship_oy[shown_heading][lat] + SHIP_ROWS * 8);
}
