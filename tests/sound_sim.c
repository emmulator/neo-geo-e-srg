/* sound_sim: the frame's sound command list, host-built from the real
 * src/ship.c / src/missiles.c / src/rules.c / src/radar.c and src/sound.h's
 * sound_frame_cmds (the same function src/flow.c's game_sound calls), for
 * tests/test_sound_host.py.
 *
 * Stdin commands:
 *   "G seed level"      reset ship/missiles/rules/radar/sound to a fresh game
 *   "P cell"            place the ship at rest on cell (clears broken)
 *   "L cell"            locate the ship at rest on cell (keeps broken)
 *   "B cell"            mark cell broken (rules_break_cell, with its cascade)
 *   "M cell"            put a missile one step from landing on cell
 *   "K cell"            put a missile and a bullet on a collision course
 *   "input pressed"     one game frame (bios_p1current, bios_p1change)
 *
 * After each frame print:
 *   S n c0 c1 ...       the frame's command list, exactly as game_sound sends
 *                       it (src/sound.h sound_frame_cmds). No command = "S 0".
 *
 * The injected M/K objects are test harness events: the checker's Python
 * model injects the same state before the frame, so the comparison still
 * covers the real ship/missile/rules logic and the real sound decision. */
#include <stdio.h>
#include <string.h>
#include "sound.h"
#include "ship.h"
#include "missiles.h"
#include "rules.h"
#include "radar.h"
#include "cells.h"
/* missiles_tables.h holds the cell ring/phi tables and the flight constants
 * the injections use; the rest of its generated tables are unused here, so
 * silence only their unused-variable warnings (the cart's build uses them). */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
#include "missiles_tables.h"
#pragma GCC diagnostic pop

/* a missile one step from the dome: the frame's step lands it, and the
 * landing breaks its fresh cell (SFX_CRACK) */
static void inject_land(mis_t *m, u8 c)
{
    mis_obj_t *o = &m->obj[0];

    o->state = 1;
    o->kind = KIND_MISSILE;
    o->ring = mis_cell_ring[c];
    o->phi = mis_cell_phi[c];
    o->r = MIS_R_LAND + 1;
    o->dr = 1;
    o->life = 0;
}

/* a missile and a bullet on the same line, behind one another: the frame's
 * step crosses them and the collision shoots the missile down (SFX_HIT) */
static void inject_kill(mis_t *m, u8 c)
{
    mis_obj_t *o = &m->obj[0], *b = &m->obj[NMIS];

    o->state = 1;
    o->kind = KIND_MISSILE;
    o->ring = mis_cell_ring[c];
    o->phi = mis_cell_phi[c];
    o->r = 600000;
    o->dr = 60000;
    o->life = 0;
    b->state = 1;
    b->kind = KIND_BULLET;
    b->ring = o->ring;
    b->phi = o->phi;
    b->r = 590000;
    b->dr = BUL_DR;
    b->life = 10;
}

int main(void)
{
    ship_t ship;
    mis_t mis;
    rules_t rules;
    radar_t radar;
    sound_state_t sound;
    sound_frame_t fr;
    char line[64];
    unsigned a, b, i;

    ship_reset(&ship);
    mis_reset(&mis);
    rules_reset(&rules);
    memset(&radar, 0, sizeof radar);
    memset(&sound, 0, sizeof sound);

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "G %u %u", &a, &b) == 2) {
            ship_reset(&ship);
            mis_reset(&mis);
            rules_reset(&rules);
            rules.level = (u8)b;
            mis.level = (u8)b;
            mis.rng = (u16)a;
            memset(&radar, 0, sizeof radar);
            memset(&sound, 0, sizeof sound);
        } else if (sscanf(line, "P %u", &a) == 1) {
            ship_place(&ship, (u8)a);
        } else if (sscanf(line, "L %u", &a) == 1) {
            ship_locate(&ship, (u8)a);
        } else if (sscanf(line, "B %u", &a) == 1) {
            rules_break_cell(&rules, &ship, (u8)a);
        } else if (sscanf(line, "M %u", &a) == 1) {
            inject_land(&mis, (u8)a);
        } else if (sscanf(line, "K %u", &a) == 1) {
            inject_kill(&mis, (u8)a);
        } else if (sscanf(line, "%u %u", &a, &b) == 2) {
            u8 busy = rules_begin(&rules, &ship, &mis, (u8)b);
            u8 died;
            u8 cmds[SOUND_CMDS_MAX];
            u8 n;

            if (!busy)
                ship_frame(&ship, (u8)a, (u8)b);
            mis_update(&mis, &ship, &rules, (u8)b, busy);
            died = (u8)rules_end(&rules, &ship, &mis);
            radar_frame(&radar, &mis, &ship);

            fr.jumped = ship.jumped;
            fr.move_left = ship.move_left;
            fr.mlen = ship.mlen;
            fr.spinning = ship.spinning;
            fr.sfx = mis.sfx;
            fr.died = died;
            fr.alive = (u8)(!rules.dead_t && !rules.game_over);
            fr.dead_t = rules.dead_t;
            fr.dome_dead = rules.dome_dead;
            fr.collapse_frac = collapse_frac(&rules);
            fr.locked = radar.locked;
            n = sound_frame_cmds(&sound, &fr, cmds);
            printf("S %u", n);
            for (i = 0; i < n; i++)
                printf(" %u", cmds[i]);
            printf("\n");
        }
    }
    return 0;
}
