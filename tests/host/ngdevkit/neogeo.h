/* host stand-in for <ngdevkit/neogeo.h>: just what the pure-logic sources
 * (src/ship.c, src/missiles.c, src/rules.c, src/cracks.c) use, so tests/
 * can build them with the host gcc. The LSPC registers are plain volatile
 * words (src/cracks.c's hardware half compiles; the host never runs it). */
#ifndef HOST_NEOGEO_H
#define HOST_NEOGEO_H
#include <stddef.h>
#include "types.h"
#define CNT_UP    (1 << 0)      /* as ngdevkit's bios-ram.h */
#define CNT_DOWN  (1 << 1)
#define CNT_LEFT  (1 << 2)
#define CNT_RIGHT (1 << 3)
#define CNT_A     (1 << 4)
#define CNT_B     (1 << 5)
#define CNT_C     (1 << 6)
#define CNT_D     (1 << 7)

/* the LSPC registers, as volatile words (like registers.h but plain) */
extern volatile u16 host_vram_addr;
extern volatile u16 host_vram_rw;
extern volatile u16 host_vram_mod;
#define REG_VRAMADDR ((volatile u16 *)&host_vram_addr)
#define REG_VRAMRW   ((volatile u16 *)&host_vram_rw)
#define REG_VRAMMOD  ((volatile u16 *)&host_vram_mod)
#define ADDR_SCB1 0
#define ADDR_SCB2 0x8000
#define ADDR_SCB3 0x8200
#define ADDR_SCB4 0x8400
#define ADDR_FIXMAP 0x7000
/* the sprite palette banks (cracks.c writes them) */
extern volatile u16 host_palbanks[16 * 16];
#define MMAP_PALBANK1 (host_palbanks)
/* the host build has no BIOS joypad RAM */
#define bios_p1current 0
#define bios_p1change  0
#endif
