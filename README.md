# E-SRG for the Neo Geo

A Neo Geo port of [E-SRG](https://github.com/emmulator/vectrex-e-srg), the Vectrex game about defending
a rotating geodesic dome from incoming missiles. The Vectrex draws its vector
graphics at run time; the Neo Geo can only show pre-drawn tiles, so this port
renders every view of the dome, ship and missiles ahead of time from the same
geometry and turns them into sprites.

Status: **1.0.0**, a faithful port of Vectrex E-SRG 1.1.1 (see
[CHANGELIST.md](CHANGELIST.md)). Design and milestones:
[docs/plan.md](docs/plan.md). Tested in MAME (AES and MVS); not yet on real
hardware.

Controls: stick moves, A fires, B jumps (on the title: changes level),
C next title page, Start starts (MVS: coin first).

```
make              # build/rom/esrg.zip, the cart
make test         # host tests
make boot-test    # MAME boot tests
scripts/mame.sh   # play it in MAME (AES); MVS=1 for the arcade board
```

Toolchain: [ngdevkit](https://github.com/dciabrin/ngdevkit) (68000 gcc,
tiletool, paltool, adpcmtool); emulators: MAME, gngeo.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).
