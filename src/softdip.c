/* softdip.c: the cart's MVS soft-DIP table (Attract Task A4), laid out as
 * ngdevkit's examples/08-software-dips do. The three region tables live in
 * .text.softdip, which ngdevkit's link script places in the ROM header right
 * after crt0; the BIOS reads the region's table, shows "DEMO SOUND" with
 * its "ON"/"OFF" choices, and copies the selected index into
 * bios_game_dip[6] (enum DIP #0).
 *
 * The table is the one place the MVS DIP exists; src/flow.c asks
 * softdip_demo_sound() whether the title's demo may send its sound effects.
 * The default is OFF (enum index 1), as the user's 10-28 note asks; ON is
 * index 0. On AES the gate is a runtime toggle instead (below), because the
 * AES BIOS has no game-settings screen.
 *
 * Attract D1: on AES the demo is silent at power-on and a D press on any
 * title page toggles it. The toggle is not saved: it lives in _backup_ram
 * (.bss.bram), which survives the BIOS re-entry after a game (so the
 * setting holds across games) but is per-boot on AES (so it is gone after a
 * power-off). The valid marker distinguishes a fresh/garbage byte (fresh
 * MAME RAM reads 0x00, which would otherwise be OFF anyway) from a chosen
 * state, exactly as src/flow.c's flow_level marker does. */
#include <ngdevkit/neogeo.h>
#include <ngdevkit/bios-ram.h>
#include "softdip.h"

/* "ON" is choice 0; "OFF" is choice 1 and the default. */
#define DIP_ENUM_OPTS(opt) \
    opt(0, "DEMO SOUND", ("ON", "OFF"), 1)

/* GENERATE_DIP fills every enum slot with {0,0} and then overrides the used
 * ones (and the padded strings' tail bytes); -Wextra's -Woverride-init
 * warns about that by design. Scope the diagnostic around the macro only,
 * as the generated-header lesson does. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Woverride-init"
#include <ngdevkit/soft-dip.h>

GENERATE_DIP(jp, "E-SRG");
GENERATE_DIP(us, "E-SRG");
GENERATE_DIP(eu, "E-SRG");
#pragma GCC diagnostic pop

#define DEMO_SOUND_ON 0

/* the AES toggle's backup-RAM state and validity marker */
#define AES_DEMO_SOUND_MAGIC 0x5d
static u8 _backup_ram aes_demo_sound_on;
static u8 _backup_ram aes_demo_sound_valid;

/* Attract D1's debug exports (like src/demo.c's demo_dbg_*): the MAME demo
 * probe reads the AES state and the toggle count, so a 60-frame D hold that
 * toggled once is distinguishable from one that toggled on every held
 * frame. Tiny .bss words, no behaviour in the normal cart. */
volatile u8 softdip_dbg_aes_on;
volatile u16 softdip_dbg_toggles;

/* the AES setting: silent unless a valid toggle state was stored */
static u8 aes_demo_sound(void)
{
    if (aes_demo_sound_valid != AES_DEMO_SOUND_MAGIC)
        return 0;
    return (u8)(aes_demo_sound_on & 1);
}

void softdip_demo_sound_toggle(void)
{
    u8 on = aes_demo_sound();

    on = (u8)(!on);
    aes_demo_sound_on = on;
    aes_demo_sound_valid = AES_DEMO_SOUND_MAGIC;
    softdip_dbg_aes_on = on;
    softdip_dbg_toggles++;
}

u8 softdip_demo_sound(void)
{
    /* AES: the toggle, silent at power-on. */
    if (bios_mvs_flag != 0x80) {
        u8 on = aes_demo_sound();

        softdip_dbg_aes_on = on;
        return on;
    }
    /* MVS: enum DIP #0 (byte 6). The BIOS stores the selected index. */
    return (u8)(DIP_ENUM[0] == DEMO_SOUND_ON);
}
