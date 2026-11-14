# E-SRG for the Neo Geo — ngdevkit build. See AGENTS.md.
SHELL = /bin/bash

NGDEVKIT_PREFIX ?= $(HOME)/Development/github/dciabrin/ngdevkit/local
BIN       = $(NGDEVKIT_PREFIX)/bin
CC68K     = $(BIN)/m68k-neogeo-elf-gcc
OBJCOPY68 = $(BIN)/m68k-neogeo-elf-objcopy
Z80OBJCOPY= $(BIN)/z80-neogeo-ihx-sdobjcopy
NGSHARE   = $(NGDEVKIT_PREFIX)/share/ngdevkit

BUILDDIR = build
ROMDIR   = $(BUILDDIR)/rom
GAMEROM  = esrg
GAMETITLE= E-SRG

override CFLAGS += -I$(NGDEVKIT_PREFIX)/m68k-neogeo-elf/include -Isrc -I$(BUILDDIR) \
	-std=c99 -fomit-frame-pointer -O2 -g -Wall -Wextra \
	$(if $(NSTARS),-DNSTARS=$(NSTARS),)
# rom_eye_catcher_mode=2: no BIOS boot logo. The BIOS draws its "MAX 330 MEGA"
# animation from the cart's own S/C ROM tiles (SNK's art in commercial carts);
# ours hold the font there, so mode 0 showed stray letters.
LDFLAGS = -specs ngdevkit -L$(NGDEVKIT_PREFIX)/m68k-neogeo-elf/lib -lngdevkit \
	-Wl,--defsym,rom_eye_catcher_mode=2

PROMSIZE = 1048576
# CROMSIZE: power of two >= the back-to-back content, 16 KiB BIOS zeros +
# dome + ship + missile + explosion sheets + the broken tiles. The broken
# tiles are now PACKED (render_broken.py emits them directly in the runtime's
# fetch order: 7,909 tiles instead of the old sheet's 20,735 places, so the
# "mostly empty" padding is gone), but the whole C ROM is still 1,224,768
# bytes (718,592 pre-broken + 506,176 broken), so the smallest power of two
# that fits is 2 MB per chip (the task: "as low as the data allows").
CROMSIZE = 2097152
MROMSIZE = 131072

PROM1 = $(ROMDIR)/$(GAMEROM)-p1.p1
SROM1 = $(ROMDIR)/$(GAMEROM)-s1.s1
CROM1 = $(ROMDIR)/$(GAMEROM)-c1.c1
CROM2 = $(ROMDIR)/$(GAMEROM)-c2.c2
MROM1 = $(ROMDIR)/$(GAMEROM)-m1.m1
VROM1 = $(ROMDIR)/$(GAMEROM)-v1.v1
CART  = $(ROMDIR)/$(GAMEROM).zip

SRCS = $(wildcard src/*.c)
OBJS = $(patsubst src/%.c,$(BUILDDIR)/%.o,$(SRCS))
ELF  = $(BUILDDIR)/rom.elf

ASSETS = $(BUILDDIR)/assets
DOME_GIF = $(ASSETS)/dome.gif
DOME_C1  = $(ASSETS)/dome.c1
DOME_C2  = $(ASSETS)/dome.c2
DOME_PAL = $(ASSETS)/dome.pal
DOME_MAP = $(BUILDDIR)/dome_map.h
CELLS_H  = $(BUILDDIR)/cells.h
FIX_PAL  = $(BUILDDIR)/fix_pal.h
# the one sprite slot map (M5 Task 1): build/slots.lua (the MAME probes
# dofile it) and build/slots.json (the Python checkers load it) are
# generated from src/slots.h, the only place slot numbers are defined.
# SLOTS_NSTARS passes a build's -DNSTARS override (the renumbering proof)
# through to the generated files, so the probes read the same map the
# cartridge compiled; NSTARS (the override) is a Makefile variable, NOT a
# CFLAGS -D, so the C sources keep compiling with plain `make`.
SLOTS_LUA  = $(BUILDDIR)/slots.lua
SLOTS_JSON = $(BUILDDIR)/slots.json
SHIP_GIF = $(ASSETS)/ship.gif
SHIP_C1  = $(ASSETS)/ship.c1
SHIP_C2  = $(ASSETS)/ship.c2
SHIP_PAL = $(ASSETS)/ship.pal
SHIP_MAP = $(BUILDDIR)/ship_map.h
MIS_TABLES = $(BUILDDIR)/missiles_tables.h
MIS_MAP    = $(BUILDDIR)/missile_map.h
MIS_SHEETS = $(addprefix $(ASSETS)/,mis_l.gif mis_m.gif mis_s.gif expl.gif)
BROKEN_PART  = $(ASSETS)/broken.c1
BROKEN_MAP   = $(BUILDDIR)/broken_map.h
BROKEN_C2    = $(ASSETS)/broken.c2
# M5 Task 2: the stars' tables (positions, palette, the picture's tile
# number) and the C ROM tile itself, both from tools/render_stars.py: one
# tile right after the broken sheet (STAR_TILE_BASE), in c1/c2 byte pairs.
STARS_MAP   = $(BUILDDIR)/stars_map.h
STARS_C1    = $(ASSETS)/stars.c1
STARS_C2    = $(ASSETS)/stars.c2
# M5 Task 3: the radar's per-ring and per-step tables (tools/gen_radar.py,
# reading the constants from src/radar.h), used by src/radar.c's per-frame
# 16-bit maths.
RADAR_TABLES = $(BUILDDIR)/radar_tables.h
# M5 Task 4: the radar's pictures and tables — the static frame picture (a
# 1-px ellipse + the Vectrex's roof), the per-height stick pictures and the
# per-(dx,dy) heading tiles, solved against the Neo Geo's zoom tables, all
# by tools/render_radar.py (from src/radar.h's constants and the "000-lo.lo"
# zoom table in aes.zip). The map header (tile bases + the palette) and the
# c1/c2 payloads join the C ROM right after the stars, the radar's part of
# CROMSIZE (2 MB) budget.
RADAR_MAP    = $(BUILDDIR)/radar_map.h
RADAR_C1     = $(ASSETS)/radar-frame.c1 $(ASSETS)/radar-stick.c1 $(ASSETS)/radar-head.c1
RADAR_C2     = $(ASSETS)/radar-frame.c2 $(ASSETS)/radar-stick.c2 $(ASSETS)/radar-head.c2
# M7 Task 1: the sound pipeline. tools/render_sfx.py renders the five
# Vectrex effects as mono 16-bit WAVs at 187500 Hz (the AY's clock / 8);
# sox resamples them to 18500 Hz, the ADPCM-A encoder's rate; vromtool.py
# packs them into the 524288-byte V ROM and emits build/samples.inc, the
# START/STOP ASM defines sound/user_commands.s includes. The M ROM is
# nullsound + user_commands.s (the command table: 3 reset, 4..8 play the
# samples), assembled/linked/objcopied instead of the stock
# nullsound_driver.ihx.
SFX_RAW      = $(addprefix $(BUILDDIR)/sfx-raw/,fire.wav jump.wav hit.wav crack.wav pip.wav)
SFX_DIR      = $(BUILDDIR)/sfx
SFX_WAVS     = $(addprefix $(SFX_DIR)/,fire.wav jump.wav hit.wav crack.wav pip.wav)
SFX_MAP      = sound/samples-map.yaml
SAMPLES_INC  = $(BUILDDIR)/samples.inc
SOUND_REL    = $(BUILDDIR)/user_commands.rel
SOUND_IHX    = $(BUILDDIR)/sound_driver.ihx

# generated headers every object may include (later tasks add to this)
GEN_HEADERS = $(FIX_PAL) $(DOME_MAP) $(DOME_PAL) $(CELLS_H) $(SHIP_MAP) $(SHIP_PAL) $(MIS_TABLES) $(MIS_MAP) $(BROKEN_MAP) $(STARS_MAP) $(STARS_C1) $(STARS_C2) $(RADAR_TABLES) $(RADAR_MAP) $(RADAR_C1) $(RADAR_C2)
CROM1_PARTS = $(DOME_C1) $(SHIP_C1) $(MIS_SHEETS:.gif=.c1) $(BROKEN_PART) $(STARS_C1) $(RADAR_C1)
CROM2_PARTS = $(DOME_C2) $(SHIP_C2) $(MIS_SHEETS:.gif=.c2) $(BROKEN_C2) $(STARS_C2) $(RADAR_C2)

.PHONY: all cart test clean boot-test mame
all: cart
$(ASSETS):
	mkdir -p $@

# slots.lua/json are generated from src/slots.h plus the build's NSTARS
# override; the stamp (named for the effective NSTARS) forces a regenerate
# when the value changes between invocations (the -DNSTARS=16 proof), while
# a build whose NSTARS did not change stays incremental.
SLOTS_STAMP = $(BUILDDIR)/.slots-nstars-$(if $(NSTARS),$(NSTARS),12)
$(SLOTS_LUA) $(SLOTS_JSON) &: src/slots.h tools/gen_slots.py $(SLOTS_STAMP) | $(BUILDDIR)
	python3 tools/gen_slots.py $(BUILDDIR) $(if $(SLOTS_NSTARS),$(SLOTS_NSTARS),$(NSTARS))
$(SLOTS_STAMP):
	mkdir -p $(BUILDDIR)
	rm -f $(BUILDDIR)/.slots-nstars-*   # a value switch removes the other
	touch $@                           # stamps, so the next build of a
	                                   # different NSTARS regenerates the
	                                   # files (the renumbering proof)

$(DOME_GIF) $(DOME_MAP) &: tools/render_dome.py tools/geometry.py | $(ASSETS)
	python3 tools/render_dome.py $(DOME_GIF) $(DOME_MAP)

$(DOME_C1) $(DOME_C2) &: $(DOME_GIF)
	$(BIN)/tiletool.py -c --sprite $< -o $(DOME_C1) $(DOME_C2)

# paltool writes "{ ... }," (an initialiser list entry); dome.c includes it
# as a whole initialiser, so the trailing comma is dropped
$(DOME_PAL): $(DOME_GIF)
	$(BIN)/paltool.py $< -o $@.tmp
	sed 's/},[[:space:]]*$$/}/' $@.tmp > $@ && rm $@.tmp

# the ship's movement tables (the Vectrex game's)
$(CELLS_H): tools/gen_cells.py tools/geometry.py | $(BUILDDIR)
	python3 tools/gen_cells.py $@ > /dev/null

# the ship: 48 latitude views, tiles right after the dome's
$(SHIP_GIF) $(SHIP_MAP) &: tools/render_ship.py tools/render_dome.py tools/geometry.py | $(ASSETS)
	python3 tools/render_ship.py $(SHIP_GIF) $(SHIP_MAP) > /dev/null

$(SHIP_C1) $(SHIP_C2) &: $(SHIP_GIF)
	$(BIN)/tiletool.py -c --sprite $< -o $(SHIP_C1) $(SHIP_C2)

$(SHIP_PAL): $(SHIP_GIF)
	$(BIN)/paltool.py $< -o $@.tmp
	sed 's/},[[:space:]]*$$/}/' $@.tmp > $@ && rm $@.tmp

# missiles and bullets: tables (rings, flights, projection) and pictures
$(MIS_TABLES): tools/gen_missiles.py tools/geometry.py tools/vectrex_missiles.json | $(BUILDDIR)
	python3 tools/gen_missiles.py $@ > /dev/null

$(MIS_SHEETS) $(MIS_MAP) &: tools/render_missiles.py tools/gen_missiles.py tools/render_ship.py \
		tools/render_dome.py tools/geometry.py tools/vectrex_missiles.json | $(ASSETS)
	python3 tools/render_missiles.py $(ASSETS) $(MIS_MAP) > /dev/null

# broken-window overlays: the art + the per-cell tables (M4-fixes Task 3).
# render_broken.py writes broken.c1/c2 itself — the tiles are packed in the
# runtime's fetch order (BROKEN_TILE_BASE + tile0[cell] + view_t0[cell][view]
# + r*w + c), which no tiletool sheet (row-major over a rectangle) can
# express, and that packing is what keeps the C ROM as small as the content
# allows (the old sheet's 20,735 padded places are gone; the whole C ROM is
# 1.22 MB, so CROMSIZE = 2 MB — the smallest power of two that fits).
$(BROKEN_PART) $(BROKEN_C2) $(BROKEN_MAP) &: tools/render_broken.py tools/render_missiles.py tools/render_ship.py \
		tools/render_dome.py tools/gen_missiles.py tools/geometry.py $(SLOTS_JSON) | $(ASSETS)
	python3 tools/render_broken.py $(ASSETS) $(BROKEN_MAP) > /dev/null

# the stars: the map header is generated first (the .c1/.c2 need its tile
# number only to verify it — render_stars.py prints it); the stamp forces a
# regenerate when NSTARS changes (so a -DNSTARS=16 build's stars.c1 sits at
# the right offset), see the STARS_C1 comment above. The stamp is
# order-only, so a build whose NSTARS did not change stays incremental.
STARS_STAMP = $(BUILDDIR)/.stars-nstars-$(if $(NSTARS),$(NSTARS),12)
$(STARS_MAP): tools/render_stars.py tools/render_broken.py $(SLOTS_JSON) | $(BUILDDIR) $(STARS_STAMP)
	python3 tools/render_stars.py $@ > /dev/null
$(STARS_C1) $(STARS_C2): tools/render_stars.py tools/render_broken.py $(SLOTS_JSON) $(STARS_MAP) | $(ASSETS) $(STARS_STAMP)
	python3 tools/render_stars.py $(STARS_MAP) $(STARS_C1) $(STARS_C2) > /dev/null
$(STARS_STAMP):
	mkdir -p $(BUILDDIR)
	rm -f $(BUILDDIR)/.stars-nstars-*   # as the slots stamp: a value switch
	touch $@                           # invalidates the other stamps, so the
	                                   # next build of the old value
	                                   # regenerates (the renumbering proof)

$(ASSETS)/%.c1 $(ASSETS)/%.c2: $(ASSETS)/%.gif
	$(BIN)/tiletool.py -c --sprite $< -o $(ASSETS)/$*.c1 $(ASSETS)/$*.c2

# the radar's pictures (M5 Task 4): one grouped rule emits the map header
# and the three c1/c2 part pairs (frame, sticks, headings) in the C ROM
# order, after the stars. The generator reads the constants from
# src/radar.h and the Neo Geo's zoom table from aes.zip (the headings are
# solved against it) and verifies its own output as it goes.
$(RADAR_MAP) $(RADAR_C1) $(RADAR_C2) &: tools/render_radar.py tools/render_broken.py src/radar.h $(SLOTS_JSON) | $(BUILDDIR) $(ASSETS)
	python3 tools/render_radar.py $(RADAR_MAP) $(ASSETS)/radar-frame.c1 $(ASSETS)/radar-frame.c2 \
		$(ASSETS)/radar-stick.c1 $(ASSETS)/radar-stick.c2 \
		$(ASSETS)/radar-head.c1 $(ASSETS)/radar-head.c2 > /dev/null

# the radar's tables: per ring the spot's x factor, y factor and stick
# height (all / (R/6), from src/radar.h's constants and the rings' polar
# angles), per screen azimuth j sin and cos — the 16-bit tables
# src/radar.c's per-frame maths read
$(RADAR_TABLES): tools/gen_radar.py tools/geometry.py tools/gen_missiles.py src/radar.h $(MIS_TABLES) | $(BUILDDIR)
	python3 tools/gen_radar.py $@ > /dev/null

$(BUILDDIR) $(ROMDIR):
	mkdir -p $@

$(BUILDDIR)/%.o: src/%.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -c $< -o $@

$(ELF): $(OBJS)
	$(CC68K) -o $@ $^ $(LDFLAGS)

# P ROM: binary, padded, byte-swapped for the cartridge
$(PROM1): $(ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none

# S ROM: ASCII fix tiles (tile = character code)
$(SROM1) $(FIX_PAL): tools/generate_srom.py src/title.h | $(ROMDIR) $(BUILDDIR)
	python3 tools/generate_srom.py --ascii --output $(SROM1) --pal-header $(FIX_PAL)
	@test $$(stat -c%s $(SROM1)) -eq 16384 || { echo "S ROM must be 16384 bytes"; exit 1; }

# C ROM: 16 KiB of BIOS tiles (zero), then game tiles (later tasks), padded
$(CROM1): $(CROM1_PARTS) | $(ROMDIR)
	{ dd if=/dev/zero bs=16384 count=1 status=none; for f in $(CROM1_PARTS); do cat $$f; done; } > $@
	@test $$(stat -c%s $@) -le $(CROMSIZE) || { echo "C ROM overflow"; exit 1; }
	truncate -s $(CROMSIZE) $@
$(CROM2): $(CROM2_PARTS) | $(ROMDIR)
	{ dd if=/dev/zero bs=16384 count=1 status=none; for f in $(CROM2_PARTS); do cat $$f; done; } > $@
	@test $$(stat -c%s $@) -le $(CROMSIZE) || { echo "C ROM overflow"; exit 1; }
	truncate -s $(CROMSIZE) $@

# the Z80 sound driver tools (M7 Task 1): sdasz80 for the assembler,
# sdld (the z80-neogeo-ihx linker, ihex output) for the link, sdobjcopy
# for the M ROM binary
Z80SDAS     = $(BIN)/z80-neogeo-ihx-sdasz80
Z80SDLD     = $(BIN)/z80-neogeo-ihx-sdld
NGZ80INC    = $(NGDEVKIT_PREFIX)/z80-neogeo-ihx/include/nullsound
NGZ80LIB    = $(NGDEVKIT_PREFIX)/z80-neogeo-ihx/lib

# M ROM: nullsound + the cart's sound commands (sound/user_commands.s).
# The .rel -> .ihx -> binary chain replaces today's stock
# nullsound_driver.ihx: the driver's command table now has the five play
# commands (4..8) registered.
$(MROM1): $(SOUND_IHX) | $(ROMDIR)
	$(Z80OBJCOPY) -I ihex -O binary $< $@ --pad-to $(MROMSIZE)

$(SOUND_IHX): $(SOUND_REL) $(NGZ80LIB)/nullsound.lib | $(BUILDDIR)
	$(Z80SDLD) -b DATA=0xf800 -i $@ $(NGZ80LIB)/nullsound.lib $(SOUND_REL)

$(SOUND_REL): sound/user_commands.s $(SAMPLES_INC) | $(BUILDDIR)
	$(Z80SDAS) -g -l -p -u -I$(NGZ80INC) -I$(BUILDDIR) -o $@ $<

# V ROM: the five effects, packed by vromtool.py into the fixed 524288-byte
# V ROM (--roms actually writes it; --asm alone only emits the defines).
# build/samples.inc carries the START/STOP defines the sound driver reads.
$(VROM1): $(SOUND_IHX) $(SAMPLES_INC) | $(ROMDIR)
	$(BIN)/vromtool.py --roms -s 524288 -n 1 $(SFX_MAP) -o $(VROM1) -m $(SAMPLES_INC)
$(SAMPLES_INC): $(SFX_WAVS) $(SFX_MAP) | $(BUILDDIR)
	$(BIN)/vromtool.py --asm -s 524288 $(SFX_MAP) -o $(VROM1) -m $@
$(SFX_WAVS): $(SFX_RAW) | $(SFX_DIR)   # prereqs only; the pattern rule does the sox
$(SFX_DIR)/%.wav: $(BUILDDIR)/sfx-raw/%.wav | $(SFX_DIR)
	sox $< -r 18500 $@
$(SFX_RAW): tools/render_sfx.py | $(BUILDDIR) $(BUILDDIR)/sfx-raw
	python3 tools/render_sfx.py $(BUILDDIR)/sfx-raw
$(SFX_DIR) $(BUILDDIR)/sfx-raw:
	mkdir -p $@

# the SOUND_TEST build: the M7 Task 1 test cart. -DSOUND_TEST main.o/flow.o
# (relinked P ROM only; it shares the M/V ROMs with the normal cart): on
# the title, at title frames 100, 160, 220, 280 and 340 it sends 4, 5, 6,
# 7 and 8, and at frame 400 it sends 6 and 8 in the same frame, recording
# each send's title frame and acknowledgement result in a RAM log the
# boot-test probe reads. The normal cart never contains the flag.
SNDTEST_ELF = $(BUILDDIR)/rom-soundtest.elf
SNDTEST_PROM = $(ROMDIR)/esrg-soundtest-p1.p1
SNDTEST_CART = $(ROMDIR)/esrg-soundtest.zip
$(BUILDDIR)/main-soundtest.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSOUND_TEST -c src/main.c -o $@
$(BUILDDIR)/flow-soundtest.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSOUND_TEST -c src/flow.c -o $@
$(SNDTEST_ELF): $(OBJS) $(BUILDDIR)/main-soundtest.o $(BUILDDIR)/flow-soundtest.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/main-soundtest.o $(BUILDDIR)/flow-soundtest.o $(LDFLAGS)
$(SNDTEST_PROM): $(SNDTEST_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(SNDTEST_CART): $(SNDTEST_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(SNDTEST_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-soundtest -l "E-SRG (sound test)" -o $@
.PHONY: soundtest-cart
soundtest-cart: $(SNDTEST_CART)

# the SOUND+RADAR_TEST build: the M7 Task 2 radar leg. -DSOUND_TEST (for
# the game sound log) + -DRADAR_TEST (the first missile of each game aims
# at the ship's start cell, so the lock-on happens with no input); the
# probe holds no input and the checker proves the pips come every 20
# frames from the lock's first frame, none before. The normal cart never
# contains either flag. radar_test_spawn lives in flow.c, so only flow.o
# needs both flags; main.c's -DSOUND_TEST bits are the same as the
# soundtest build's.
SNDRAD_ELF = $(BUILDDIR)/rom-soundradar.elf
SNDRAD_PROM = $(ROMDIR)/esrg-soundradar-p1.p1
SNDRAD_CART = $(ROMDIR)/esrg-soundradar.zip
$(BUILDDIR)/flow-soundradar.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSOUND_TEST -DRADAR_TEST -c src/flow.c -o $@
$(BUILDDIR)/main-soundradar.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSOUND_TEST -c src/main.c -o $@
$(SNDRAD_ELF): $(OBJS) $(BUILDDIR)/main-soundradar.o $(BUILDDIR)/flow-soundradar.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/main-soundradar.o $(BUILDDIR)/flow-soundradar.o $(LDFLAGS)
$(SNDRAD_PROM): $(SNDRAD_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(SNDRAD_CART): $(SNDRAD_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(SNDRAD_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-soundradar -l "E-SRG (sound/radar test)" -o $@
.PHONY: soundradar-cart
soundradar-cart: $(SNDRAD_CART)

cart: $(CART)
$(CART): $(PROM1) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(PROM1) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n $(GAMEROM) -l "$(GAMETITLE)" -o $@

# the CRACK_TEST build: the cart with -DCRACK_TEST (test-only: the normal
# cart above never contains it). It shares every ROM but the P ROM, which
# is relinked from a main.o compiled with the flag. The test cart starts
# with all 38 broken cells so the broken-tile boot-test can check every
# visible one.
CRKTEST_ELF = $(BUILDDIR)/rom-cracktest.elf
CRKTEST_PROM = $(ROMDIR)/esrg-cracks-p1.p1
CRKTEST_CART = $(ROMDIR)/esrg-cracks.zip
$(BUILDDIR)/main-cracktest.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DCRACK_TEST -c src/main.c -o $@
$(BUILDDIR)/flow-cracktest.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DCRACK_TEST -c src/flow.c -o $@
$(BUILDDIR)/cracks-cracktest.o: src/cracks.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DCRACK_TEST -c src/cracks.c -o $@
$(CRKTEST_ELF): $(OBJS) $(BUILDDIR)/main-cracktest.o $(BUILDDIR)/flow-cracktest.o $(BUILDDIR)/cracks-cracktest.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o $(BUILDDIR)/cracks.o,$(OBJS)) \
		$(BUILDDIR)/main-cracktest.o $(BUILDDIR)/flow-cracktest.o $(BUILDDIR)/cracks-cracktest.o $(LDFLAGS)
$(CRKTEST_PROM): $(CRKTEST_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(CRKTEST_CART): $(CRKTEST_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(CRKTEST_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-cracks -l "E-SRG (broken tiles test)" -o $@
.PHONY: crktest-cart
crktest-cart: $(CRKTEST_CART)

# the FRAME_MARK build: the M4 Task 4 frame-budget measurement cart. The
# normal cart never contains it; it shares every ROM but the P ROM, which
# is relinked from a main.o compiled with the flag (which records the
# end-of-work raster line in work_end_mark, read by frame_mark_probe.lua).
FRMMARK_ELF = $(BUILDDIR)/rom-framemark.elf
FRMMARK_PROM = $(ROMDIR)/esrg-framemark-p1.p1
FRMMARK_CART = $(ROMDIR)/esrg-framemark.zip
$(BUILDDIR)/main-framemark.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DFRAME_MARK -c src/main.c -o $@
$(BUILDDIR)/flow-framemark.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DFRAME_MARK -c src/flow.c -o $@
$(FRMMARK_ELF): $(OBJS) $(BUILDDIR)/main-framemark.o $(BUILDDIR)/flow-framemark.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/main-framemark.o $(BUILDDIR)/flow-framemark.o $(LDFLAGS)
$(FRMMARK_PROM): $(FRMMARK_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(FRMMARK_CART): $(FRMMARK_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(FRMMARK_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-framemark -l "E-SRG (frame mark)" -o $@
.PHONY: framemark-cart
framemark-cart: $(FRMMARK_CART)

# the M4-fixes Task 3 frame-time build: CRACK_TEST + FRAME_MARK together, so
# the measurement runs with all 38 broken tiles plus missiles — the worst
# overlay workload. The normal cart never contains either flag.
CRKFMK_ELF = $(BUILDDIR)/rom-crackframemark.elf
CRKFMK_PROM = $(ROMDIR)/esrg-crackfm-p1.p1
CRKFMK_CART = $(ROMDIR)/esrg-crackfm.zip
$(BUILDDIR)/main-crackframemark.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DCRACK_TEST -DFRAME_MARK -c src/main.c -o $@
$(BUILDDIR)/flow-crackframemark.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DCRACK_TEST -DFRAME_MARK -c src/flow.c -o $@
$(CRKFMK_ELF): $(OBJS) $(BUILDDIR)/main-crackframemark.o $(BUILDDIR)/flow-crackframemark.o $(BUILDDIR)/cracks-cracktest.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o $(BUILDDIR)/cracks.o,$(OBJS)) \
		$(BUILDDIR)/main-crackframemark.o $(BUILDDIR)/flow-crackframemark.o $(BUILDDIR)/cracks-cracktest.o $(LDFLAGS)
$(CRKFMK_PROM): $(CRKFMK_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(CRKFMK_CART): $(CRKFMK_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(CRKFMK_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-crackfm -l "E-SRG (broken tiles, frame mark)" -o $@
.PHONY: crackframemark-cart
crackframemark-cart: $(CRKFMK_CART)

# the GAMEOVER_DRAW_TEST build: the M4-fixes Task 4 boot-test's cart. The
# normal cart never contains this flag; the -DGAMEOVER_DRAW_TEST main.o
# runs the scripted one-life game the probe and checker drive (see the
# flag's comment in src/main.c and tests/check_gameover_draw.py). It
# shares every ROM but the P ROM, like the other test builds.
GET_ELF = $(BUILDDIR)/rom-gameoverdraw.elf
GET_PROM = $(ROMDIR)/esrg-godraw-p1.p1
GET_CART = $(ROMDIR)/esrg-godraw.zip
$(BUILDDIR)/main-gameoverdraw.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DGAMEOVER_DRAW_TEST -c src/main.c -o $@
$(BUILDDIR)/flow-gameoverdraw.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DGAMEOVER_DRAW_TEST -c src/flow.c -o $@
$(GET_ELF): $(OBJS) $(BUILDDIR)/main-gameoverdraw.o $(BUILDDIR)/flow-gameoverdraw.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/main-gameoverdraw.o $(BUILDDIR)/flow-gameoverdraw.o $(LDFLAGS)
$(GET_PROM): $(GET_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(GET_CART): $(GET_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(GET_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-godraw -l "E-SRG (game over draw test)" -o $@
.PHONY: godraw-cart
godraw-cart: $(GET_CART)

# the RADAR_TEST build: the -DRADAR_TEST cart (test-only: the normal cart
# never contains it). It shares every ROM but the P ROM, relinked from a
# main.o compiled with the flag, which scripts the radar boot-test: the
# first missile of each game is forced to target the ship's start cell
# (ship_reset's landing), so (with the ship parked) the lock-on happens
# with no input. See the flag's comment in src/main.c and
# tests/check_radar.py.
RADTEST_ELF = $(BUILDDIR)/rom-radartest.elf
RADTEST_PROM = $(ROMDIR)/esrg-radartest-p1.p1
RADTEST_CART = $(ROMDIR)/esrg-radartest.zip
$(BUILDDIR)/main-radartest.o: src/main.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DRADAR_TEST -c src/main.c -o $@
$(BUILDDIR)/flow-radartest.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DRADAR_TEST -c src/flow.c -o $@
$(RADTEST_ELF): $(OBJS) $(BUILDDIR)/main-radartest.o $(BUILDDIR)/flow-radartest.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/main-radartest.o $(BUILDDIR)/flow-radartest.o $(LDFLAGS)
$(RADTEST_PROM): $(RADTEST_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(RADTEST_CART): $(RADTEST_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(RADTEST_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-radartest -l "E-SRG (radar test)" -o $@
.PHONY: radartest-cart
radartest-cart: $(RADTEST_CART)

# pure-logic C built for the host: tests/host stands in for <ngdevkit/neogeo.h>
HOSTCC     = gcc
HOSTCFLAGS = -std=c99 -Wall -Wextra -Itests/host -Isrc -I$(BUILDDIR)
$(BUILDDIR)/test_ship: tests/test_ship.c src/ship.c src/ship.h $(CELLS_H) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_ship.c src/ship.c -o $@
$(BUILDDIR)/ship_sim: tests/ship_sim.c src/ship.c src/ship.h $(CELLS_H) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/ship_sim.c src/ship.c -o $@
MIS_HOST = src/ship.c src/ship.h src/missiles.c src/missiles.h src/rules.c src/rules.h $(CELLS_H) $(MIS_TABLES)
$(BUILDDIR)/test_missiles: tests/test_missiles.c $(MIS_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_missiles.c src/ship.c src/missiles.c src/rules.c -o $@
RADAR_HOST = src/radar.c src/radar.h $(RADAR_TABLES) $(MIS_TABLES)
$(BUILDDIR)/radar_sim: tests/radar_sim.c $(RADAR_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/radar_sim.c src/radar.c -o $@
$(BUILDDIR)/mis_sim: tests/mis_sim.c $(MIS_HOST) $(RADAR_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/mis_sim.c src/ship.c src/missiles.c src/rules.c src/radar.c -o $@
$(BUILDDIR)/view_sim: tests/view_sim.c src/mis_view.c src/mis_view.h $(CELLS_H) $(MIS_TABLES) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/view_sim.c src/mis_view.c -o $@
RULES_HOST = src/ship.c src/ship.h src/missiles.c src/missiles.h src/rules.c src/rules.h $(CELLS_H) $(MIS_TABLES)
$(BUILDDIR)/rules_sim: tests/rules_sim.c $(RULES_HOST) $(RADAR_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/rules_sim.c src/ship.c src/missiles.c src/rules.c src/radar.c -o $@
$(BUILDDIR)/test_rules: tests/test_rules.c $(RULES_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_rules.c src/ship.c src/missiles.c src/rules.c -o $@

CRACKS_HOST = src/cracks.c src/cracks.h src/dome.h src/mis_gfx.h src/ship_gfx.h $(CELLS_H) $(BROKEN_MAP)
# the broken test links dome.c (dome_draw_gone) + rules.c (the collapse
# getters dome.c reads), so those pure modules join the build.
$(BUILDDIR)/test_broken: tests/test_broken.c $(CRACKS_HOST) src/dome.c src/dome.h src/rules.c src/rules.h src/ship.c src/ship.h src/missiles.c src/missiles.h | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_broken.c src/cracks.c src/dome.c src/rules.c src/ship.c src/missiles.c -o $@

# the broken-tiles tile dump: the same code path the cartridge runs
# (broken_place + draw's fetch expression), printed per stone, so the host
# test can decode the real C ROM at exactly those tile numbers and compare
# each tile with the stone render_bitmap() drew (tests/test_broken_rom.py).
$(BUILDDIR)/broken_tiles_dump: tests/broken_tiles_dump.c $(CRACKS_HOST) src/dome.c src/dome.h src/rules.c src/rules.h src/ship.c src/ship.h src/missiles.c src/missiles.h | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/broken_tiles_dump.c src/cracks.c src/dome.c src/rules.c src/ship.c src/missiles.c -o $@

COLLAPSE_HOST = src/ship.c src/ship.h src/missiles.c src/missiles.h src/rules.c src/rules.h $(CELLS_H) $(MIS_TABLES)
$(BUILDDIR)/test_collapse: tests/test_collapse.c $(COLLAPSE_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_collapse.c src/ship.c src/missiles.c src/rules.c -o $@
$(BUILDDIR)/collapse_sim: tests/collapse_sim.c $(COLLAPSE_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/collapse_sim.c src/ship.c src/missiles.c src/rules.c -o $@

HUD_HOST = src/ship.c src/ship.h src/missiles.c src/missiles.h src/rules.c src/rules.h \
	src/hud.c src/hud.h $(CELLS_H) $(MIS_TABLES) $(FIX_PAL)
$(BUILDDIR)/test_hud: tests/test_hud.c $(HUD_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_hud.c src/ship.c src/missiles.c src/rules.c src/hud.c src/fix.c -o $@

STARS_HOST = src/stars.c src/stars.h $(STARS_MAP)
$(BUILDDIR)/stars_sim: tests/stars_sim.c $(STARS_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/stars_sim.c src/stars.c -o $@

# the title's nine pages of fix text (M6 Task 5): pure logic, host-built,
# held to tests/title_model.py by tests/test_title.py. The cart object is
# built too (SRCS picks src/title.c up) but unused until Task 6 draws it.
$(BUILDDIR)/title_sim: tests/title_sim.c src/title.c src/title.h | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/title_sim.c src/title.c -o $@

# the per-level high-score table (M6 Task 8): pure logic, host-built, held
# to tests/best_model.py by tests/test_best.py. The cart object is built
# too (SRCS picks src/best.c up) but unused until Task 9 keeps flow_best
# in backup RAM.
$(BUILDDIR)/best_sim: tests/best_sim.c src/best.c src/best.h src/missiles.h | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/best_sim.c src/best.c -o $@

DOME_HOST = src/dome.c src/dome.h src/cracks.c src/cracks.h src/rules.c src/rules.h src/ship.c src/ship.h src/missiles.c src/missiles.h $(CELLS_H) $(BROKEN_MAP)
$(BUILDDIR)/test_go_dome: tests/test_go_dome.c $(DOME_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_go_dome.c src/dome.c src/cracks.c src/rules.c src/ship.c src/missiles.c -o $@

test: cart $(SLOTS_LUA) $(SLOTS_JSON) $(BUILDDIR)/test_ship $(BUILDDIR)/ship_sim $(BUILDDIR)/test_missiles $(BUILDDIR)/mis_sim \
		$(BUILDDIR)/view_sim $(BUILDDIR)/rules_sim $(BUILDDIR)/test_rules $(BUILDDIR)/test_broken \
		$(BUILDDIR)/broken_tiles_dump $(BUILDDIR)/test_hud $(BUILDDIR)/test_collapse $(BUILDDIR)/collapse_sim \
		$(BUILDDIR)/test_go_dome $(BUILDDIR)/stars_sim $(BUILDDIR)/radar_sim $(BUILDDIR)/title_sim \
		$(BUILDDIR)/best_sim
	$(BUILDDIR)/test_ship
	$(BUILDDIR)/test_missiles
	$(BUILDDIR)/test_rules
	$(BUILDDIR)/test_broken
	$(BUILDDIR)/test_hud
	$(BUILDDIR)/test_collapse
	$(BUILDDIR)/test_go_dome
	$(BUILDDIR)/stars_sim all > /dev/null
	$(BUILDDIR)/best_sim < /dev/null > /dev/null	# Task 8: the sim builds and runs
	python3 -m pytest tests -q

# headless MAME: boots into cart code; the snapshot shows the dome with the
# ship on the start cell, and with the stick held up the ship reaches the peak;
# at frame 1000 (no input) missiles are on screen: the first launches come
# at fixed times from the seeded generator. `leftovers` plays bullets and
# missiles and checks that no shrunk sprite shows leftover tiles below it.
# `cracks` boots a CRACK_TEST build that starts with all 38 broken cells
# and checks the snapshot for broken-window overlays on every visible one
# and none elsewhere (tests/check_broken.py). `hud` boots the normal cart with
# scripts/hud_probe.lua, which drives a deterministic game through the BIOS
# joypad RAM and decodes FIXMAP to text; tests/check_hud.py compares the
# frames against tests/hud_model.py (M4 Task 3). `collapse` boots the
# normal cart with scripts/collapse_probe.lua, which plays a whole game to
# GAME OVER with no human input and proves, from VRAM and a snapshot, that
# the dome's columns move during the shake and are gone by the end of the
# collapse, that the rebuilt dome's VRAM matches a fresh dome's, and that
# GAME OVER appears within the frame budget the rules imply
# (tests/check_collapse.py, M4 Task 4). `framemark` boots the -DFRAME_MARK
# cart with scripts/frame_mark_probe.lua and asserts, from the end-of-work
# raster line, that no frame's work reaches the next frame's visible area
# (tests/check_frame_mark.py, M4 Task 4). `crackframemark` boots the
# -DCRACK_TEST -DFRAME_MARK cart (all 38 broken tiles plus the missile
# wave, the overlays' worst frame) and asserts the same frame budget
# (tests/check_frame_mark.py). `ship-respawn` boots the normal cart with
# scripts/ship_respawn_probe.lua, which plays the hold-Up death
# and respawn and proves the respawned ship's SCB2/3/4, SCB1 and pixels
# equal the start of the game's (tests/check_ship_respawn.py, M4-fixes
# Task 1); `ship-respawn-nodeath` repeats the check with no death — a
# direct proof that a non-sticky right column (the bug) cannot be masked
# by a fresh boot.
# `flow` and `flow-restart` boot the normal cart with scripts/flow_probe.lua
# and prove, from FIXMAP reads, the AES title -> Start -> game -> GAME OVER
# flow (M6 Task 1); `flow-mvs` and `flow-mvs-start` run the same probe under
# the MVS BIOS (`neogeo -bios euro -cart1 esrg`) with scripts/mvs_input.lua's
# coin and Start holds, and prove the MVS boot harness: the machine is MVS,
# a coin starts the BIOS compulsion timer at BCD 30 s, and the game begins
# when it runs out (flow-mvs) or on a real Start press (flow-mvs-start, M6
# Task 2). `flow-mvs-norestart` (M6 Task 4) plays the Up-held game on MVS,
# taps A at GAME OVER + 60, and proves A does not restart the game and the
# 295-frame return to the title still happens.
boot-test: cart crktest-cart crackframemark-cart framemark-cart godraw-cart radartest-cart soundtest-cart soundradar-cart $(SLOTS_LUA) $(SLOTS_JSON)
	scripts/boot_test.sh dome
	scripts/boot_test.sh dome-lift
	scripts/boot_test.sh ship
	BOOT_HOLD="P1 Up" scripts/boot_test.sh ship-top
	FRAMES=1000 scripts/boot_test.sh missile
	FRAMES=1500 scripts/boot_test.sh leftovers
	CRACK_CART="$(CRKTEST_CART)" scripts/boot_test.sh cracks
	CRACK_CART="$(CRKTEST_CART)" CRACK_ANGLE=56 scripts/boot_test.sh cracks
	scripts/boot_test.sh hud
	scripts/boot_test.sh collapse
	scripts/boot_test.sh framemark
	scripts/boot_test.sh crackframemark
	scripts/boot_test.sh ship-respawn
	scripts/boot_test.sh ship-respawn-nodeath
	GO_DRAW_CART="$(GET_CART)" scripts/boot_test.sh gameover-draw
	scripts/boot_test.sh stars
	RADAR_CART="$(RADTEST_CART)" scripts/boot_test.sh radar
	scripts/boot_test.sh flow
	scripts/boot_test.sh flow-restart
	scripts/boot_test.sh flow-pages
	scripts/boot_test.sh flow-pages-c
	scripts/boot_test.sh flow-level
	scripts/boot_test.sh flow-return
	scripts/boot_test.sh flow-return-best
	scripts/boot_test.sh flow-mvs
	scripts/boot_test.sh flow-mvs-start
	scripts/boot_test.sh flow-mvs-norestart
	# M6 Task 9: the backup-RAM high scores on MVS — three runs sharing
	# one fresh nvram directory: run 1 plays the centred game to GAME
	# OVER, run 2 proves the persisted score shows on the title before
	# any game, run 3 (a fresh nvram) proves a clean "0".
	rm -rf build/best-nvram
	BEST_NVRAM_DIR="$(abspath build/best-nvram)" scripts/boot_test.sh best-mvs
	BEST_NVRAM_DIR="$(abspath build/best-nvram)" BEST_REUSE=1 scripts/boot_test.sh best-mvs
	BEST_NVRAM_DIR="$(abspath build/best-nvram)" BEST_FRESH=1 scripts/boot_test.sh best-mvs
	# M6 Task 10: the AES memory-card high scores — three runs. Runs 1
	# and 2 share one -memcard file (run 1 starts from a fresh one, run 2
	# reuses it with a FRESH nvram/cfg, proving the card — not the
	# per-boot backup RAM — kept the score); run 3 passes no card at all,
	# proving the 0x80 no-card path and that a game still keeps its score
	# in backup RAM for the boot.
	rm -rf build/best-card
	BEST_CARD_DIR="$(abspath build/best-card)" scripts/boot_test.sh best-aes
	BEST_CARD_DIR="$(abspath build/best-card)" BEST_REUSE=1 scripts/boot_test.sh best-aes
	BEST_CARD_DIR="$(abspath build/best-card)" BEST_NOCARD=1 scripts/boot_test.sh best-aes
	# M7 Task 1: the sound pipeline — the soundtest cart (AES) plays all
	# five effects at the recorded title frames and the check reads the
	# recorded WAV; the MVS leg proves the same driver + samples play
	# under the MVS BIOS.
	scripts/boot_test.sh sound
	scripts/boot_test.sh sound-mvs
	# M7 Task 2: the game's sounds — the sound-game leg drives the
	# deterministic "sound game" and proves the logged sends equal the
	# model's predicted commands (frame for frame), sampled sends are loud
	# in the WAV, and the collapse's 5 rumbles come 9 frames apart; the
	# sound-radar leg (no input) proves the lock-on pips come every 20
	# frames from the lock's first frame, none before.
	scripts/boot_test.sh sound-game
	scripts/boot_test.sh sound-radar

mame: cart
	scripts/mame.sh

clean:
	rm -rf $(BUILDDIR)
