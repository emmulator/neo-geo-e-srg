"""The cartridge image: every chip present at the size the Makefile promises."""
import os
import zipfile

ROM = os.path.join(os.path.dirname(__file__), "..", "build", "rom")
SIZES = {
    "esrg-p1.p1": 1048576,
    "esrg-s1.s1": 131072,
    "esrg-c1.c1": 4194304,          # 4 MB: the back-to-back content is
    "esrg-c2.c2": 4194304,          # 3,104,960 bytes (48,515 tiles
                                    # including the 256 BIOS zeros; 48,259
                                    # game tiles; the 8-heading hovercraft
                                    # is 20,032 tiles), so 2 MB
                                    # would not fit (the smallest power of
                                    # two >= the data; see Makefile's
                                    # CROMSIZE comment)
    "esrg-m1.m1": 131072,
}


def test_cart_zip_members_and_sizes():
    with zipfile.ZipFile(os.path.join(ROM, "esrg.zip")) as z:
        names = {i.filename: i.file_size for i in z.infolist()}
    for name, size in SIZES.items():
        assert names.get(name) == size, (name, names.get(name))
    assert names.get("esrg-v1.v1", 0) >= 1


def test_prom_header_is_neogeo():
    # the P ROM is stored byte-swapped; the 68k sees "NEO-GEO" at $100
    p = open(os.path.join(ROM, "esrg-p1.p1"), "rb").read()
    swapped = bytes(b for i in range(0x100, 0x108, 2) for b in (p[i + 1], p[i]))
    assert swapped[:7] == b"NEO-GEO"


def test_crom_bios_tiles_are_blank():
    # tiles 0..255 (16 KiB per plane file) are the BIOS's: we leave them zero
    for n in ("esrg-c1.c1", "esrg-c2.c2"):
        data = open(os.path.join(ROM, n), "rb").read(16384)
        assert data == bytes(16384)
