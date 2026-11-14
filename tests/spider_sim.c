/* spider_sim: drive the game's per-frame order for src/ship_gfx.c's
 * ship_frame_of, for tests/check_spider.py --host.
 *
 * Stdin commands:
 *   "G seed level"      reset ship/missiles/rules to a fresh game
 *   "P cell"            place the ship at rest on cell (clears broken)
 *   "L cell"            locate the ship at rest on cell (keeps broken)
 *   "B cell"            mark cell broken
 *   "R"                 reset the animation to REST (a hide/respawn/demo)
 *   "input pressed"     one game frame (bios_p1current, bios_p1change)
 *
 * After each frame print:
 *   cell move_left mlen angle lat lift jumped spinning shot frame dead game_over
 * exactly as the cart's frame order (rules_begin, ship_frame, mis_update,
 * rules_end; hide -> ship_anim_rest, else ship_frame_of(mis.sfx & SFX_FIRE)). */
#include <stdio.h>
#include "ship.h"
#include "missiles.h"
#include "rules.h"
#include "ship_gfx.h"

/* the host stand-in's LSPC registers (ship_gfx.c's hardware half links,
 * but this sim never calls it) */
volatile u16 host_vram_addr;
volatile u16 host_vram_rw;
volatile u16 host_vram_mod;
volatile u16 host_palbanks[16 * 16];

int main(void)
{
    ship_t ship;
    mis_t mis;
    rules_t rules;
    ship_anim_t anim;
    char line[64];
    unsigned a, b;

    ship_reset(&ship);
    mis_reset(&mis);
    rules_reset(&rules);
    ship_anim_rest(&anim);

    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "G %u %u", &a, &b) == 2) {
            ship_reset(&ship);
            mis_reset(&mis);
            rules_reset(&rules);
            rules.level = (u8)b;
            mis.level = (u8)b;
            mis.rng = (u16)a;
            ship_anim_rest(&anim);
        } else if (sscanf(line, "P %u", &a) == 1) {
            ship_place(&ship, (u8)a);
            ship_anim_rest(&anim);
        } else if (sscanf(line, "L %u", &a) == 1) {
            ship_locate(&ship, (u8)a);
            ship_anim_rest(&anim);
        } else if (sscanf(line, "B %u", &a) == 1) {
            ship_set_broken(&ship, (u8)a);
        } else if (line[0] == 'R') {
            ship_anim_rest(&anim);
        } else if (sscanf(line, "%u %u", &a, &b) == 2) {
            u8 busy = rules_begin(&rules, &ship, &mis, (u8)b);
            u8 shot;
            u8 frame;
            u8 dead;

            if (!busy)
                ship_frame(&ship, (u8)a, (u8)b);
            mis_update(&mis, &ship, &rules, (u8)b, busy);
            rules_end(&rules, &ship, &mis);
            dead = (u8)(rules.dead_t || rules.game_over);
            if (dead) {
                ship_anim_rest(&anim);
                frame = ship_frame_of(&ship, 0, &anim);   /* REST */
            } else {
                shot = (u8)(mis.sfx & SFX_FIRE);
                frame = ship_frame_of(&ship, shot, &anim);
            }
            printf("%u %u %u %u %u %u %u %u %u %u %u %u\n",
                   ship.cell, ship.move_left, ship.mlen, ship.dome_angle,
                   ship.lat, ship.lift, ship.jumped, ship.spinning,
                   (unsigned)(mis.sfx & SFX_FIRE), frame, dead,
                   rules.game_over);
        }
    }
    return 0;
}
