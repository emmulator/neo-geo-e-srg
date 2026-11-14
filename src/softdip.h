/* softdip.h: the cart's MVS soft-DIP table and the demo-sound gate
 * (Attract Tasks A4 and D1).
 *
 * The cart declares one enum DIP, "DEMO SOUND", with the choices "ON" and
 * "OFF" (index 0 and 1) and defaults to OFF (index 1). The MVS BIOS shows it
 * in its game-settings screen and copies the selected value into
 * bios_game_dip (enum DIP #0 is byte 6, see <ngdevkit/soft-dip.h>). The AES
 * has no BIOS game-settings screen: the demo is silent at power-on and a D
 * press on a title page toggles it (not saved).
 *
 * softdip_demo_sound() is the demo's sound gate: 1 when the demo may play
 * its effects, 0 when it must stay silent. On MVS it follows the DIP; on
 * AES it follows the runtime toggle.
 *
 * softdip_demo_sound_toggle() flips the AES toggle (src/flow.c calls it on
 * a title D press). The debug exports let the MAME demo probe state the
 * toggle value and count the presses: softdip_dbg_aes_on is the current
 * state, softdip_dbg_toggles the number of AES toggles since boot. */
#ifndef SOFTDIP_H
#define SOFTDIP_H
#include <ngdevkit/types.h>

u8 softdip_demo_sound(void);
void softdip_demo_sound_toggle(void);

extern volatile u8 softdip_dbg_aes_on;
extern volatile u16 softdip_dbg_toggles;

#endif
