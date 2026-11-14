#!/usr/bin/env python3
"""Build a MAME-readable aes.zip from a Neo Geo BIOS zip (FBNeo/MAME/RA layout).

`make mame` with MAME_BIOS_DIR pointed at the output directory then boots the
real AES BIOS instead of ngdevkit's nullbios.

Why this script exists: the org.mamedev.MAME flatpak's zip reader will not open
archives produced by Info-ZIP `zip` or by torrentzip - it silently reports the
members as "NOT FOUND". A stored (uncompressed) archive written by Python's
zipfile works. It also only honours the FIRST -rompath entry, so everything
MAME needs for the machine has to sit in one directory; for `aes` that is just
this aes.zip (neo-epo.bin + neo-po.bin + 000-lo.lo).

Usage:  scripts/mame_bios.py <source-neogeo-bios.zip> <output-dir>
Example: scripts/mame_bios.py ~/Development/emulators/bios/fbneo/neogeo.zip \\
                              ~/Development/emulators/roms/mame-neogeo
"""
import sys, os, zipfile, zlib

# MAME 0.289 `aes`, default bios (asia) + the L0 ROM. CRC32s are checked so a
# wrong or renamed dump fails loudly here rather than as a boot error.
WANT = {
    "neo-epo.bin": 0xd27a71f1,
    "neo-po.bin":  0x16d0c132,
    "000-lo.lo":   0x5a86cff2,
}

def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "aes.zip")
    with zipfile.ZipFile(os.path.expanduser(src)) as z:
        names = set(z.namelist())
        for n in WANT:
            if n not in names:
                sys.exit(f"{src}: missing {n} (has: {sorted(names)})")
        data = {n: z.read(n) for n in WANT}
    for n, want_crc in WANT.items():
        got = zlib.crc32(data[n]) & 0xffffffff
        if got != want_crc:
            sys.exit(f"{n}: CRC {got:08x}, MAME wants {want_crc:08x} - wrong dump")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for n in WANT:
            z.writestr(n, data[n])
    print(f"wrote {out}  ({', '.join(WANT)})")
    print(f"run:  MAME_BIOS_DIR={outdir} make mame")

if __name__ == "__main__":
    main()
