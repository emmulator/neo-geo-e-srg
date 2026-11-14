#!/usr/bin/env python3
"""gen_slots.py — generate build/slots.lua and build/slots.json from
src/slots.h, the one sprite slot map (M5 Task 1).

Usage:
    gen_slots.py OUTDIR [NSTARS]      # NSTARS: the build's -D override (the
                                      # -DNSTARS=16 renumbering proof); the
                                      # default uses the header's own value.

The Lua probes `dofile` build/slots.lua (it returns the map table), the
Python checkers load build/slots.json: both must reflect exactly what the
cartridge compiled, including the override, or a probe's slot ranges would
diverge from the game's. The evaluator understands the header's own shape
(#ifndef NSTARS default + plain arithmetic over earlier names); a build
that passes an override takes the #ifndef branch's define at face value
instead of guessing at preprocessor semantics.
"""
import json
import os
import re
import sys


def parse_slots_h(text, nstars=None):
    """evaluate the #defines; returns {name: value}. `text` is the file's
    contents. When nstars is given, the header's `#ifndef NSTARS` default
    is replaced by the build's override value."""
    defines = {}
    overrides = {} if nstars is None else {"NSTARS": nstars}
    if nstars is not None:
        defines["NSTARS"] = nstars
    active = True
    for raw in text.splitlines():
        line = raw.split("//")[0].split("/*")[0].strip()
        if not line:
            continue
        m = re.match(r"#ifndef\s+(\w+)", line)
        if m:
            active = m.group(1) not in overrides and m.group(1) not in defines
            continue
        if line.startswith("#endif"):
            active = True
            continue
        if not active:
            continue
        m = re.match(r"#define\s+(\w+)\s+(.+)", line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        if name == "NSTARS" and nstars is not None:
            continue
        for k in sorted(defines, key=len, reverse=True):
            expr = expr.replace(k, str(defines[k]))
        defines[name] = int(eval(expr, {"__builtins__": {}}, {}))
    return defines


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    outdir = sys.argv[1]
    nstars = int(sys.argv[2]) if len(sys.argv) == 3 else None
    header = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                          "src", "slots.h")
    values = parse_slots_h(open(header).read(), nstars=nstars)

    with open(os.path.join(outdir, "slots.json"), "w") as f:
        json.dump(values, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(outdir, "slots.lua"), "w") as f:
        f.write("-- generated from src/slots.h by tools/gen_slots.py "
                "(M5 Task 1): the one slot map; do not edit.\n")
        f.write("return {\n")
        for k in sorted(values):
            if k == "NSTARS":
                f.write("  %s = %d,\n" % (k, values[k]))   # a count the
                continue                       # probes need (the stars)
            f.write("  %s = %d,\n" % (k, values[k]))
        f.write("}\n")


if __name__ == "__main__":
    main()
