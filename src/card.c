/* card.c: the AES memory card calls (M6 Task 10). See card.h.
 *
 * The AES keeps the per-level high scores on the memory card: at the
 * first entry after power-on (and only then — the task's "_backup_ram
 * flag says it was done") the cart LOADs the saved best table; at GAME
 * OVER, when best_update changed the table, it SAVEs it, FORMATting the
 * card first if the save answers 0x81 (unformatted). On MVS none of
 * this runs (bios_mvs_flag == 0x80): backup RAM is the persistence
 * there.
 *
 * The calls follow the confirmed sequence (plan §"The AES memory
 * card", verified 2026-10-17): unlock, set the command / start / size /
 * fcb / sub fields, call bios_card(), read bios_card_answer, lock.
 * fcb 0x0539 is the cart's rom_NGH_ID (ngdevkit's default 1337 in BCD),
 * sub 0 is the first save slot, the size is sizeof(best_t) (18 bytes).
 *
 * Runs only at an entry and at GAME OVER, never per frame: the 32-bit
 * maths (best_valid's u32 compares) and the BIOS calls are allowed.
 */
#include <ngdevkit/bios-ram.h>
#include <ngdevkit/memory-card.h>
#include "card.h"

#define CARD_FCB 0x0539              /* the cart's rom_NGH_ID, BCD */
#define CARD_SUB 0                   /* the first save slot */

/* the probe-facing call log (card.h): pairs of (command, answer),
 * 0xffff terminated. In .data (initialised all-0xffff), re-copied by the
 * runtime on every entry: an entry's log starts empty and the GAME
 * OVER's calls fill it before the return entry wipes it. */
volatile u16 card_log[8] = {
    0xffff, 0xffff, 0xffff, 0xffff,
    0xffff, 0xffff, 0xffff, 0xffff,
};

static void card_log_call(u16 command, u8 answer)
{
    u8 i;

    for (i = 0; i < 8; i += 2) {
        if (card_log[i] == 0xffff) {
            card_log[i] = command;
            card_log[i + 1] = answer;
            return;
        }
    }
}

static u8 card_call(u8 command, const best_t *b, best_t *dst)
{
    ng_memory_card_unlock();
    bios_card_command = command;
    if (command == MC_CMD_LOAD_DATA)
        bios_card_start = (u32)dst;      /* load into the caller's buffer */
    else
        bios_card_start = (u32)b;        /* save from the caller's table */
    bios_card_size = sizeof(best_t);
    bios_card_fcb = CARD_FCB;
    bios_card_sub = CARD_SUB;
    bios_card();
    ng_memory_card_lock();
    return bios_card_answer;
}

/* one save attempt (the caller owns the FORMAT retry) */
static u8 card_save_once(const best_t *b)
{
    return card_call(MC_CMD_SAVE_DATA, b, 0);
}

u8 card_load_best(best_t *b)
{
    u8 answer = card_call(MC_CMD_LOAD_DATA, 0, b);

    card_log_call(MC_CMD_LOAD_DATA, answer);
    if (answer == MC_ERR_OK && best_valid(b))
        return 1;
    return 0;
}

u8 card_save_best(const best_t *b)
{
    u8 answer = card_save_once(b);

    card_log_call(MC_CMD_SAVE_DATA, answer);
    if (answer == MC_ERR_NOT_FORMATTED) {       /* unformatted: FORMAT, then save again */
        u8 fa = card_call(MC_CMD_FORMAT, b, 0);

        card_log_call(MC_CMD_FORMAT, fa);
        if (fa == MC_ERR_OK) {
            answer = card_save_once(b);
            card_log_call(MC_CMD_SAVE_DATA, answer);
        }
    } else if (answer == MC_ERR_NO_CARD) {
        /* no card: nothing to do; the caller keeps the backup-RAM table */
    }
    return answer;
}
