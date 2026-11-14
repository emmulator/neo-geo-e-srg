"""The cart's NGH number (10-30): the Makefile's NGH_ID is the header's
rom_NGH_ID (the 68k word at 0x108, which the BIOS keys the MVS backup RAM
and the AES memory card's save by) and the card calls' fcb, not ngdevkit's
default 1337 (0x0539) that other ngdevkit homebrew shares."""
import os
import re
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELF = os.path.join(REPO, "build", "rom.elf")


def makefile_ngh():
    text = open(os.path.join(REPO, "Makefile")).read()
    return int(re.search(r"^NGH_ID\s*=\s*(0x[0-9a-fA-F]+)", text, re.M).group(1), 16)


def header_word(addr):
    out = subprocess.run(["m68k-neogeo-elf-objcopy", "-O", "binary", "--only-section=.text.boot",
                          ELF, "/dev/stdout"], capture_output=True, check=True).stdout
    return (out[addr] << 8) | out[addr + 1]


def test_ngh_is_bcd_and_not_the_default():
    ngh = makefile_ngh()
    assert all(int(d, 16) <= 9 for d in "%04x" % ngh), "NGH_ID must be BCD"
    assert ngh != 0x0539


def test_header_carries_the_ngh():
    assert header_word(0x108) == makefile_ngh()


def test_card_uses_the_ngh():
    src = open(os.path.join(REPO, "src", "card.c")).read()
    assert re.search(r"#define CARD_FCB NGH_ID\b", src)
