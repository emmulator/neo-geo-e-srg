#!/usr/bin/env python3
"""Generate a MAME software-list entry for an ngdevkit cartridge zip.

Why this exists
---------------
MAME's `aes` cartridge slot does not take a ROM zip by path. Handing it one
(`-cart build/rom/neo_game.zip`) loads *something* and then sits on a blue
screen, because the slot has no idea which member of the zip is the 68k
program, which is the fix layer, or how the sprite ROMs interleave. The `.neo`
extension MAME advertises for `aes` is the **memcard**, not a cart format
(`mame -listmedia aes`: `cartridge (cart) .bin` / `memcard (memc) .neo`).

The mechanism that does work is a **software list**: an XML file naming each
region (`dataarea`) and the ROMs that fill it, with the load flags that say how
bytes are placed. MAME then resolves `-cart neo_game` to that entry, opens the
zip once per dataarea, and boots.

This script reads the cart zip that `make cart` already produces and emits that
XML with the *current* CRCs — they change on every rebuild, and a stale
checksum is a hard load failure, so it must be regenerated per launch rather
than committed.

Usage:
    scripts/mame_softlist.py build/rom/neo_game.zip build/mame/hash \\
        [--name neo_game] [--description "Neo Geo One Racer"]

Writes <hashdir>/neogeo.xml. Pass that dir to MAME as -hashpath. Note that
-hashpath *replaces* MAME's own hash dir, so this list is the only one in
scope — which is fine, we only ever load our own cart.
"""
import argparse
import hashlib
import os
import sys
import zipfile

# Region layout for a Neo Geo cart, keyed by the ngdevkit filename suffix.
# Copied from the idioms in MAME's own hash/neogeo.xml — deviating from them
# fails silently rather than erroring, so they are not negotiable:
#
#   * `maincpu` MUST carry width="16" endianness="big". Without it the dataarea
#     is 8 bits wide and `load16_word_swap` is a NO-OP: the byte-swapped P ROM
#     lands unswapped, the 68k reads "EN-OEG" where the BIOS wants "NEO-GEO",
#     and the real AES BIOS parks in a watchdog-kicking halt (blue screen).
#     MAME reports no error — every checksum still matches, because the bytes
#     loaded fine, just in the wrong order.
#   * The C ROMs are an even/odd plane pair and need EXPLICIT interleave
#     offsets (+0 and +1). `load16_byte` with no offset would stack both plane
#     ROMs at 0.
#
# `attrs` goes on the <dataarea>; `flag` is the per-<rom> loadflag.
REGIONS = [
    # (order, dataarea name, suffix test, loadflag, dataarea attrs)
    (0, "maincpu",      lambda n: n.endswith(".p1"), "load16_word_swap",
        ' width="16" endianness="big"'),
    (1, "fixed",        lambda n: n.endswith(".s1"), None, ""),
    (2, "audiocpu",     lambda n: n.endswith(".m1"), None, ""),
    (3, "ymsnd:adpcma", lambda n: any(n.endswith(f".v{i}") for i in range(1, 5)),
        None, ""),
    (4, "sprites",      lambda n: any(n.endswith(f".c{i}") for i in range(1, 9)),
        "load16_byte", ""),
]

XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def xml_escape(s):
    return "".join(XML_ESCAPES.get(c, c) for c in s)


def scan(zip_path):
    """-> {dataarea: [(rom_name, size, crc_hex, sha1_hex), ...]} in member order."""
    areas = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            name = info.filename
            for _, area, matches, _flag, _attrs in REGIONS:
                if matches(name):
                    sha1 = hashlib.sha1(z.read(name)).hexdigest()
                    areas.setdefault(area, []).append(
                        (name, info.file_size, "%08x" % (info.CRC & 0xFFFFFFFF), sha1)
                    )
                    break
            else:
                print(f"mame_softlist: ignoring unrecognised member {name}",
                      file=sys.stderr)
    return areas


def rom_offsets(area, roms):
    """Explicit load offset for each rom in a dataarea.

    Sprites interleave: the C ROMs are even/odd plane pairs, so pair p covers
    [p * 2 * size, ...) with the even plane at +0 and the odd plane at +1.
    Everything else simply concatenates.
    """
    if area == "sprites":
        return [(i // 2) * 2 * roms[i][1] + (i % 2) for i in range(len(roms))]
    offs, run = [], 0
    for _name, size, _crc, _sha1 in roms:
        offs.append(run)
        run += size
    return offs


def build_xml(areas, soft_name, description, year, publisher):
    flags = {area: flag for _, area, _m, flag, _a in REGIONS}
    order = {area: o for o, area, _m, _f, _a in REGIONS}
    attrs = {area: a for _o, area, _m, _f, a in REGIONS}

    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE softwarelist SYSTEM "softwarelist.dtd">',
        '<softwarelist name="neogeo" description="SNK Neo-Geo cartridges">',
        f'\t<software name="{xml_escape(soft_name)}">',
        f"\t\t<description>{xml_escape(description)}</description>",
        f"\t\t<year>{xml_escape(year)}</year>",
        f"\t\t<publisher>{xml_escape(publisher)}</publisher>",
        '\t\t<part name="cart" interface="neo_cart">',
    ]
    for area in sorted(areas, key=lambda a: order[a]):
        roms = areas[area]
        total = sum(r[1] for r in roms)
        offs = rom_offsets(area, roms)
        lines.append(
            f'\t\t\t<dataarea name="{area}"{attrs[area]} size="0x{total:X}">'
        )
        for (name, size, crc, sha1), off in zip(roms, offs):
            flag = f' loadflag="{flags[area]}"' if flags[area] else ""
            lines.append(
                f'\t\t\t\t<rom name="{xml_escape(name)}" offset="0x{off:06X}" '
                f'size="0x{size:X}" crc="{crc}" sha1="{sha1}"{flag}/>'
            )
        lines.append("\t\t\t</dataarea>")
    lines += ["\t\t</part>", "\t</software>", "</softwarelist>", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cart_zip", help="the cartridge zip, e.g. build/rom/neo_game.zip")
    ap.add_argument("hash_dir", help="directory to write neogeo.xml into")
    ap.add_argument("--name", help="software-list entry name "
                                   "(default: cart zip basename)")
    ap.add_argument("--description", help="human title shown by MAME")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--publisher", default="homebrew")
    args = ap.parse_args()

    soft_name = args.name or os.path.splitext(os.path.basename(args.cart_zip))[0]
    description = args.description or soft_name

    areas = scan(args.cart_zip)
    if "maincpu" not in areas:
        sys.exit(f"mame_softlist: {args.cart_zip} has no *.p1 program ROM")

    os.makedirs(args.hash_dir, exist_ok=True)
    out = os.path.join(args.hash_dir, "neogeo.xml")
    with open(out, "w") as f:
        f.write(build_xml(areas, soft_name, description, args.year, args.publisher))
    print(f"mame_softlist: wrote {out} "
          f"({soft_name}: {', '.join(sorted(areas, key=len))})")


if __name__ == "__main__":
    main()
