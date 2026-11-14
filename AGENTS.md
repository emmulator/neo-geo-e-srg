# AGENTS.md — E-SRG for the Neo Geo

Read `docs/plan.md` (the design). Load the `neo-geo-dev` and `neo-geo-gfx-pipeline`
skills if you have them.

- Toolchain: ngdevkit at `~/Development/github/dciabrin/ngdevkit/local`
  (`NGDEVKIT_PREFIX`). The Makefile calls its tools by full path.
- Gate for every change: `make clean && make && make test` with no
  `warning:` or `error:` lines, then `make boot-test` (headless MAME).
- Never weaken or delete a test to make the gate pass.
- Generated files live in `build/` and are never committed.
- Pure-logic C (`src/ship.c`) never touches hardware and is also built for
  the host (`-Itests/host`: `tests/host/ngdevkit/neogeo.h` stands in for the
  ngdevkit header). `tests/test_ship_paths.py` checks it frame by frame
  against `tests/ship_model.py`, a model of the Vectrex game's movement.
- The dome's geometry comes from the Vectrex game
  (`~/Development/gitlocal/vectrex-e-srg/tools/gen_dome.py`), copied into
  `tools/geometry.py`; this repo's copy evolves on its own.
