/* host stand-in for <ngdevkit/types.h>: the fixed-width types the game
 * headers use, so pure code that includes them builds with the host gcc.
 * (neogeo.h includes this.) */
#ifndef HOST_NGDEVKIT_TYPES_H
#define HOST_NGDEVKIT_TYPES_H
#include <stdint.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
#endif
