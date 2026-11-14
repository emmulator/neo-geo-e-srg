/* card.h: the AES memory card calls (M6 Task 10). See card.c.
 *
 * Only the cart's BIOS RAM + BIOS card function: no ngdevkit library
 * beyond <ngdevkit/memory-card.h>. Runs only at an entry (the first one
 * after power-on) and at GAME OVER, never per frame, so 32-bit maths and
 * the BIOS calls are allowed here.
 */
#ifndef CARD_H
#define CARD_H
#include <ngdevkit/types.h>
#include "best.h"

/* load the best table from the memory card into *b: 1 if a valid table
 * was loaded (the caller copies it into flow_best), 0 otherwise (no
 * card, unformatted, missing slot, or the loaded bytes fail
 * best_valid). Logs the call's answers through card_log. */
u8 card_load_best(best_t *b);

/* save the best table to the memory card: if the first save answers
 * 0x81 (unformatted), FORMAT first, then save again; 0x80 (no card)
 * skips everything. Returns the last save's answer (0 on success). */
u8 card_save_best(const best_t *b);

/* a probe-facing log of the card calls this entry made. The MAME probe
 * reads these words from RAM to record the sequence — fresh card: a
 * LOAD answering 0x81, then a SAVE answering 0x81, a FORMAT answering 0
 * and a SAVE answering 0; no card: LOAD/SAVE answering 0x80 — and
 * tests/check_flow.py asserts them. The sentinel is 0xffff, NOT 0: the
 * FORMAT command is MC_CMD_FORMAT == 0, so a 0 command word would look
 * like an empty slot and the next call would overwrite it. Lives in
 * .data (initialised to 0xffff), which the runtime re-copies on every
 * entry, so the log starts empty each entry and survives a GAME OVER's
 * writes within it. */
extern volatile u16 card_log[8];     /* pairs: command, answer; 0xffff terminates */
#endif
