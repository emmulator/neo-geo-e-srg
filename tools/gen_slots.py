#!/usr/bin/env python3
"""gen_slots.py — generate build/slots.lua and build/slots.json from
src/slots.h, the one sprite slot map (M5 Task 1; stars retired by
dome-scenery Task 4).

Usage:
    gen_slots.py OUTDIR

The Lua probes `dofile` build/slots.lua (it returns the map table), the
Python checkers load build/slots.json: both must reflect exactly what the
cartridge compiled, or a probe's slot ranges would diverge from the game's.
The evaluator understands the header's own shape (#ifndef guards + plain
arithmetic over earlier names).

The header includes the generated build/dome_map.h for DOME_COLS (the dome
size knob's one source), so the Makefile generates dome_map.h first; this
script resolves the same constant straight from tools/geometry.py instead
of reading the generated file.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as g  # noqa: E402  (DOME_COLS: the dome size knob)


def parse_slots_h(text):
    """evaluate the #defines; returns {name: value}. `text` is the file's
    contents. DOME_COLS, included from build/dome_map.h, is seeded from
    geometry.py (its one source) and is NOT written to the output map: it
    is not a slot, and the JSON holds exactly what src/slots.h defines."""
    defines = {"DOME_COLS": g.DOME_COLS}
    for raw in text.splitlines():
        line = raw.split("//")[0].split("/*")[0].strip()
        if not line:
            continue
        if line.startswith("#include"):
            continue                        # dome_map.h: DOME_COLS seeded above
        if line.startswith("#ifndef") or line.startswith("#endif"):
            continue
        m = re.match(r"#define\s+(\w+)\s+(.+)", line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        for k in sorted(defines, key=len, reverse=True):
            expr = expr.replace(k, str(defines[k]))
        defines[name] = int(eval(expr, {"__builtins__": {}}, {}))
    return defines


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    outdir = sys.argv[1]
    header = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "src", "slots.h")
    values = parse_slots_h(open(header).read())
    values.pop("DOME_COLS", None)          # the knob, not a slot

    with open(os.path.join(outdir, "slots.json"), "w") as f:
        json.dump(values, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(outdir, "slots.lua"), "w") as f:
        f.write("-- generated from src/slots.h by tools/gen_slots.py "
                "(M5 Task 1): the one slot map; do not edit.\n")
        f.write("return {\n")
        for k in sorted(values):
            f.write("  %s = %d,\n" % (k, values[k]))
        f.write("}\n")


if __name__ == "__main__":
    main()
