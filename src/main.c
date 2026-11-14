/* main.c: E-SRG for the Neo Geo.
 *
 * The entry points. The cart boots to a title (M6 Task 1); the whole flow —
 * the title, a Start press, the game, and the GAME OVER return to the
 * title — lives in src/flow.c (flow_run). main() and main_mvs_title() both
 * enter that one loop; MVS's becomes different in Task 2. Here is only the
 * one-time init shared by both entries. */
#include <ngdevkit/neogeo.h>
#include <ngdevkit/ng-video.h>
#include "flow.h"
#include "fix.h"
#include "dome.h"
#include "ship.h"
#include "ship_gfx.h"
#include "missiles.h"
#include "mis_gfx.h"
#include "rules.h"
#include "cracks.h"
#include "hud.h"
#include "stars.h"
#include "radar.h"
#include "radar_gfx.h"

#define PAL_TEXT 0   /* reserved (hud.c uses PAL_HUD = 7 for the HUD text) */

static void palettes_init(void)
{
    MMAP_PALBANK1[0] = 0x8000;                    /* reference colour: black */
    MMAP_PALBANK1[PAL_TEXT * 16 + 1] = 0x0fff;    /* text: white */
    *((volatile u16 *)0x401ffe) = 0x0000;         /* backdrop: black */
}

/* the one-time init, shared by every BIOS entry: the palettes, a blank fix
 * layer, and every drawing layer's init. The game's state (ship, missiles,
 * rules) is NOT reset here: that happens at a Start (src/flow.c game_begin),
 * so the title never carries a running game's state. */
static void init_all(void)
{
    palettes_init();
    fix_clear();
    dome_init();
    ship_gfx_init();
    mis_gfx_init();
    cracks_init();
    hud_palette_init();            /* the PAL_HUD text palette only: the title
                                    * draws its own rows and the HUD's constant
                                    * rows are not drawn until a Start */
    stars_init();
    radar_gfx_init();
}

int main(void)
{
    init_all();
    flow_run(0);                  /* 0: an attract boot — the flow's title
                                   * says INSERT COIN on MVS, PRESS START on
                                   * AES (M6 Task 3) */
    return 0;
}

int main_mvs_title(void)
{
    /* Task 2: the same flow as main; Tasks 3/4 make the MVS title different
     * (it runs after a coin, with the compulsion timer). 1: the post-coin
     * title — the flow's title says PRESS START and shows the timer. */
    init_all();
    flow_run(1);
    return 0;
}
