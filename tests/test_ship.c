/* host unit tests for src/ship.c (built with tests/host/ngdevkit/neogeo.h) */
#include <stddef.h>
#include <stdio.h>
#include "ship.h"
#include "cells.h"

static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

static void run(ship_t *s, u8 input, int frames)
{
    while (frames--)
        ship_frame(s, input, 0);
}

int main(void)
{
    ship_t s;
    u8 to, over, top = 0;
    int i;

    /* 8-way stick -> the Vectrex's 32 directions; opposites cancel */
    CHECK(ship_dir(0) == 255);
    CHECK(ship_dir(CNT_RIGHT) == 0 && ship_dir(CNT_UP | CNT_RIGHT) == 4);
    CHECK(ship_dir(CNT_UP) == 8 && ship_dir(CNT_UP | CNT_LEFT) == 12);
    CHECK(ship_dir(CNT_LEFT) == 16 && ship_dir(CNT_DOWN | CNT_LEFT) == 20);
    CHECK(ship_dir(CNT_DOWN) == 24 && ship_dir(CNT_DOWN | CNT_RIGHT) == 28);
    CHECK(ship_dir(CNT_LEFT | CNT_RIGHT) == 255 && ship_dir(CNT_UP | CNT_DOWN) == 255);
    CHECK(ship_dir(CNT_UP | CNT_A) == 8);                  /* buttons don't count */

    /* starts at rest on the start cell, turned to the front */
    ship_reset(&s);
    CHECK(s.cell == CELL_START && s.move_left == 0 && s.lift == 0);
    CHECK(s.dome_angle == cell_step[CELL_START] && s.lat == cell_lat[CELL_START]);

    /* H4: heading is the struct's LAST field (the MAME probe reads the fields
     * before it at their old offsets) and a fresh game faces up-right (1) */
    CHECK(offsetof(ship_t, heading) == 38);
    CHECK(s.heading == 1);

    /* H4: every Vectrex stick direction 0..31 maps to its heading d / 4 */
    for (i = 0; i < 32; i++)
        CHECK(ship_heading((u8)i) == (u8)(i / 4));

    /* H4: from rest, every 8-way stick input turns the craft to its
     * direction (or keeps the heading when the stick is centred); a move,
     * jump or spin is tried after the turn */
    for (i = 0; i < 16; i++) {
        u8 d = ship_dir((u8)i);

        ship_place(&s, CELL_START);
        ship_frame(&s, (u8)i, 0);
        if (d == 255) {
            CHECK(s.heading == 1);              /* place's up-right */
        } else {
            CHECK(s.heading == ship_heading(d));
            CHECK(s.last_dir == d);
        }
    }

    /* H4: a centred stick keeps the heading */
    ship_place(&s, CELL_START);
    ship_frame(&s, CNT_UP, 0);                  /* turn up, start a move */
    CHECK(s.heading == 2);
    run(&s, CNT_UP, SHIP_MOVE_FRAMES);          /* land */
    ship_frame(&s, 0, 0);
    CHECK(s.heading == 2 && s.move_left == 0);

    /* H4: a centred jump keeps the heading its last_dir already set (Review
     * Focus 1: the craft faces the jump's way) */
    ship_place(&s, CELL_START);
    ship_frame(&s, CNT_UP, 0);
    run(&s, CNT_UP, SHIP_MOVE_FRAMES);
    ship_frame(&s, CNT_B, CNT_B);
    CHECK(s.mlen == SHIP_JUMP_FRAMES && s.heading == 2);

    /* H4: a push toward a broken cell turns the craft and does not move it */
    ship_place(&s, CELL_START);
    ship_set_broken(&s, cell_toward(CELL_START, 8));
    ship_frame(&s, CNT_UP, 0);
    CHECK(s.cell == CELL_START && s.move_left == 0 && s.heading == 2);

    /* H4: place/locate set the up-right heading */
    ship_place(&s, 0);
    CHECK(s.heading == 1);
    ship_locate(&s, 3);
    CHECK(s.heading == 1);

    /* a move: the destination is set at once, the landing is exact */
    ship_reset(&s);
    to = cell_toward(CELL_START, 8);
    CHECK(to != 255);
    ship_frame(&s, CNT_UP, 0);
    CHECK(s.cell == to && s.move_left == SHIP_MOVE_FRAMES);
    run(&s, CNT_UP, SHIP_MOVE_FRAMES - 1);
    CHECK(s.move_left == 1);
    run(&s, 0, 1);
    CHECK(s.move_left == 0 && s.dome_angle == cell_step[to] && s.lat == cell_lat[to]);

    /* a jump (B, stick up): two cells on, rising and falling on an arc */
    ship_reset(&s);
    over = cell_toward(CELL_START, 8);
    to = cell_toward(over, 8);
    ship_frame(&s, CNT_UP | CNT_B, CNT_B);
    CHECK(s.cell == to && s.move_left == SHIP_JUMP_FRAMES);
    for (i = 0; i < SHIP_JUMP_FRAMES; i++) {
        ship_frame(&s, 0, 0);
        if (s.lift > top)
            top = s.lift;
    }
    CHECK(top == SHIP_LIFT_PX && s.lift == 0 && s.move_left == 0);
    CHECK(s.dome_angle == cell_step[to] && s.lat == cell_lat[to]);

    /* B with the stick centred jumps the way it last pointed (up at start) */
    ship_reset(&s);
    ship_frame(&s, CNT_B, CNT_B);
    CHECK(s.cell == to);

    /* B pressed mid-move: the jump waits for the landing */
    ship_reset(&s);
    ship_frame(&s, CNT_UP, 0);                            /* move to `over` */
    ship_frame(&s, 0, CNT_B);
    run(&s, 0, SHIP_MOVE_FRAMES - 1);
    CHECK(s.cell == over && s.move_left == 0 && s.jump_req == 1);
    ship_frame(&s, 0, 0);                                 /* jumps on, up */
    CHECK(s.cell == cell_toward(cell_toward(over, 8), 8) && s.move_left == SHIP_JUMP_FRAMES);

    /* broken cells: no moving onto one, but jumping over one is fine */
    ship_reset(&s);
    ship_set_broken(&s, over);
    ship_frame(&s, CNT_UP, 0);
    CHECK(s.cell == CELL_START && s.move_left == 0);
    ship_frame(&s, CNT_UP | CNT_B, CNT_B);
    CHECK(s.cell == to);

    /* the peak: right/left spin the dome, wrapping, at the Vectrex's 50 steps
     * a second (a spin's first frame steps at once); down leaves */
    ship_place(&s, 0);
    CHECK(s.dome_angle == 0 && s.lat == 0 && s.heading == 1);
    ship_frame(&s, CNT_RIGHT, 0);
    CHECK(s.dome_angle == SHIP_TURN - 1 && s.cell == 0 && s.heading == 0);
    ship_frame(&s, CNT_UP, 0);                            /* a pause ends the spin */
    ship_frame(&s, CNT_LEFT, 0);
    CHECK(s.dome_angle == 0 && s.heading == 4);
    ship_frame(&s, CNT_UP, 0);
    ship_frame(&s, CNT_LEFT, 0);
    CHECK(s.dome_angle == 1);
    {                                   /* held: 50 steps in 59 frames */
        u8 i, a0 = s.dome_angle, n = 0;
        for (i = 1; i < SHIP_SPIN_DEN; i++) {
            u8 a = s.dome_angle;
            ship_frame(&s, CNT_LEFT, 0);
            n = (u8)(n + (s.dome_angle != a));
        }
        CHECK(n == SHIP_SPIN_NUM - 1);  /* + the spin's first step above */
        CHECK(s.dome_angle == (u8)(a0 + SHIP_SPIN_NUM - 1));
        while (s.dome_angle != 1) {     /* back to 1, a step at a time */
            ship_frame(&s, CNT_UP, 0);
            ship_frame(&s, s.dome_angle > 1 ? CNT_RIGHT : CNT_LEFT, 0);
        }
    }
    ship_frame(&s, CNT_UP, 0);                            /* up at the peak: nothing */
    CHECK(s.dome_angle == 1 && s.move_left == 0);
    ship_frame(&s, CNT_DOWN, 0);
    CHECK(s.cell == peak_down[1] && s.move_left == SHIP_MOVE_FRAMES);

    if (!fails)
        printf("test_ship: all passed\n");
    return fails != 0;
}
