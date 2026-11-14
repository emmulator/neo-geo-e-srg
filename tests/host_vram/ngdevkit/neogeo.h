/* host stand-in for <ngdevkit/neogeo.h> with a VRAM model: unlike
 * tests/host (whose LSPC registers are plain words), REG_VRAMRW here writes
 * host_vram[addr] and steps the address by REG_VRAMMOD, as the LSPC does, so
 * a test can run src/props.c's real prepare/commit and read back the words
 * the hardware would hold (tests/test_props_commit.c). Writes only: the
 * sources built against it never read VRAM. */
#ifndef HOST_VRAM_NEOGEO_H
#define HOST_VRAM_NEOGEO_H
#include <stddef.h>
#include "types.h"

extern u16 host_vram[0x10000];
extern u16 host_vram_addr;
extern u16 host_vram_mod;
u16 *host_vram_next(void);      /* &host_vram[addr], then addr += mod */
#define REG_VRAMADDR (&host_vram_addr)
#define REG_VRAMMOD  (&host_vram_mod)
#define REG_VRAMRW   (host_vram_next())
#define ADDR_SCB1 0
#define ADDR_SCB2 0x8000
#define ADDR_SCB3 0x8200
#define ADDR_SCB4 0x8400
#define ADDR_FIXMAP 0x7000
/* palette bank 1's 256 palettes */
extern u16 host_palbanks[256 * 16];
#define MMAP_PALBANK1 (host_palbanks)
#endif
