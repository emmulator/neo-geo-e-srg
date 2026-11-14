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
# the cart's NGH number (BCD), the header's rom_NGH_ID: the BIOS keys the MVS
# backup RAM and the AES memory card's save by it. 7278 was drawn at random
# (10-30) to leave ngdevkit's default 1337 (0x0539), which every ngdevkit
# homebrew that keeps it shares, and the low range SNK's own carts use.
NGH_ID   = 0x7278

override CFLAGS += -I$(NGDEVKIT_PREFIX)/m68k-neogeo-elf/include -Isrc -I$(BUILDDIR) \
	-std=c99 -fomit-frame-pointer -O2 -g -Wall -Wextra -DNGH_ID=$(NGH_ID)
# rom_eye_catcher_mode=2: no BIOS boot logo. The BIOS draws its "MAX 330 MEGA"
# animation from the cart's own S/C ROM tiles (SNK's art in commercial carts);
# ours hold the font there, so mode 0 showed stray letters.
LDFLAGS = -specs ngdevkit -L$(NGDEVKIT_PREFIX)/m68k-neogeo-elf/lib -lngdevkit \
	-Wl,--defsym,rom_eye_catcher_mode=2 -Wl,--defsym,rom_NGH_ID=$(NGH_ID)

PROMSIZE = 1048576
# CROMSIZE: power of two >= the back-to-back content, 16 KiB BIOS zeros +
# dome + ship + missile + explosion sheets + the broken tiles. The broken
# tiles are now PACKED (render_broken.py emits them directly in the runtime's
# fetch order: 7,909 tiles instead of the old sheet's 20,735 places, so the
# "mostly empty" padding is gone); the 8-heading hovercraft (H4) makes the
# whole C ROM content 46,354 tiles = 2,966,656 bytes + the 16 KiB BIOS zeros,
# 2,983,040 bytes (2.84 MB), so 4 MB per chip is the smallest power of two
# that fits.
CROMSIZE = 4194304
MROMSIZE = 131072

PROM1 = $(ROMDIR)/$(GAMEROM)-p1.p1
SROM1 = $(ROMDIR)/$(GAMEROM)-s1.s1
CROM1 = $(ROMDIR)/$(GAMEROM)-c1.c1
CROM2 = $(ROMDIR)/$(GAMEROM)-c2.c2
MROM1 = $(ROMDIR)/$(GAMEROM)-m1.m1
VROM1 = $(ROMDIR)/$(GAMEROM)-v1.v1
CART  = $(ROMDIR)/$(GAMEROM).zip

SRCS = $(wildcard src/*.c)
# Task P2: src/props_layout.c is the host-side definition of the props'
# layout (build/props_sim and the table generator link it); the cart reads
# build/props_table.h instead, so its object is not in the cartridge.
OBJS = $(filter-out $(BUILDDIR)/props_layout.o,$(patsubst src/%.c,$(BUILDDIR)/%.o,$(SRCS)))
ELF  = $(BUILDDIR)/rom.elf

ASSETS = $(BUILDDIR)/assets
DOME_GIF = $(ASSETS)/dome.gif
DOME_C1  = $(ASSETS)/dome.c1
DOME_C2  = $(ASSETS)/dome.c2
DOME_PAL = $(ASSETS)/dome.pal
DOME_MAP = $(BUILDDIR)/dome_map.h
CELLS_H  = $(BUILDDIR)/cells.h
FIX_PAL  = $(BUILDDIR)/fix_pal.h
# high-score boards Task B4: the thick-outline title font's tile numbers
# (tools/generate_srom.py --title2-header; src/flow.c includes it).
TITLE_FONT_H = $(BUILDDIR)/title_font.h
# Attract Task A3: the demo script — the recorded input runs (src/demo.c
# includes the header) and the JSON events the demo boot-test states.
DEMO_MAP = $(BUILDDIR)/demo_map.h
DEMO_JSON = $(BUILDDIR)/demo.json
# high-score boards Task B5: the initials ring's generated header and sheet
# (tools/render_ring.py is the orchestrator's). src/entry.c includes
# ring_map.h for ring_code and the phase constants; the sheet joins the C
# ROM in Task B6.
RING_GIF = $(ASSETS)/ring.gif
RING_MAP = $(BUILDDIR)/ring_map.h
# high-score boards Task B6: the ring's 38 16x16 tiles, LAST in the C ROM
# (after the collapse; src/ring_gfx.c's RING_TILE_BASE is
# COLLAPSE_TILE_BASE + COLLAPSE_TILES).
RING_C1 = $(ASSETS)/ring.c1
RING_C2 = $(ASSETS)/ring.c2
# the one sprite slot map (M5 Task 1): build/slots.lua (the MAME probes
# dofile it) and build/slots.json (the Python checkers load it) are
# generated from src/slots.h, the only place slot numbers are defined.
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
# M5 Task 3: the radar's per-ring and per-step tables (tools/gen_radar.py,
# reading the constants from src/radar.h), used by src/radar.c's per-frame
# 16-bit maths.
RADAR_TABLES = $(BUILDDIR)/radar_tables.h
# M5 Task 4: the radar's pictures and tables — the static frame picture (a
# 1-px ellipse + the Vectrex's roof), the per-height stick pictures and the
# per-(dx,dy) heading tiles, solved against the Neo Geo's zoom tables, all
# by tools/render_radar.py (from src/radar.h's constants and the "000-lo.lo"
# zoom table in aes.zip). The map header (tile bases + the palette) and the
# c1/c2 payloads join the C ROM right after the broken sheet (dome-scenery
# Task 4 retired the star tile), the radar's part of CROMSIZE (2 MB) budget.
RADAR_MAP    = $(BUILDDIR)/radar_map.h
RADAR_C1     = $(ASSETS)/radar-frame.c1 $(ASSETS)/radar-stick.c1 $(ASSETS)/radar-head.c1
RADAR_C2     = $(ASSETS)/radar-frame.c2 $(ASSETS)/radar-stick.c2 $(ASSETS)/radar-head.c2
# dome-scenery Task 5: the ground — one static block of 20 x 8 tiles from
# tools/render_scenery.py (the orchestrator's art; this Makefile only gives
# it paths), its map header (the block's place/size and the two palettes)
# and the c1/c2 payloads. The parts join the C ROM AFTER the radar's (see
# the rule below): src/ground.c adds RADAR_HEAD_TILE_BASE +
# RADAR_HEAD_TILES to the header's relative tile numbers, so the tile at
# each number is exactly the picture's tile.
GROUND_MAP   = $(BUILDDIR)/ground_map.h
GROUND_C1    = $(ASSETS)/ground.c1
GROUND_C2    = $(ASSETS)/ground.c2
# dome-scenery Task 6: the mountains — a 640 px panorama of 40 x 3 tiles
# from tools/render_mountains.py (the orchestrator's art; this Makefile only
# gives it paths), its map header (size, place and palette) and the c1/c2
# payloads. The part joins the C ROM AFTER the ground's (see the rule
# below): src/mountains.c adds RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES +
# GROUND_TILES, so the tile at each relative number is the picture's tile.
MTN_MAP      = $(BUILDDIR)/mountain_map.h
MTN_C1       = $(ASSETS)/mountain.c1
MTN_C2       = $(ASSETS)/mountain.c2
# dome-scenery Task 7: the console — a dark control panel across the bottom,
# angled up beside the dome, from tools/render_console.py (the orchestrator's
# art; this Makefile only gives it paths), its map header (per column the top
# y, the tile rows, the first tile in the part, and the palette) and the
# c1/c2 payloads. The part joins the C ROM AFTER the mountains' (see the rule
# below): src/console.c adds RADAR_HEAD_TILE_BASE + RADAR_HEAD_TILES +
# GROUND_TILES + MTN_TILES, so the tile at each relative number is the
# picture's tile.
CON_MAP      = $(BUILDDIR)/console_map.h
CON_C1       = $(ASSETS)/console.c1
CON_C2       = $(ASSETS)/console.c2
# dome-scenery Task 11: the props (the 19 trees and rocks) — the map header
# src/props_layout.c reads (per prop, per angle: x, y, se; the pictures and
# their anchors; the palettes; the shadow table) and the c1/c2 payloads.
# Dome-scenery Task 12 puts the part in the cart (after the console's in
# CROM1_PARTS/CROM2_PARTS) and links src/props_layout.c: src/props.c draws
# the props from it and src/props.h's PROP_TILE_BASE adds the part base.
PROPS_MAP    = $(BUILDDIR)/props_map.h
PROPS_C1     = $(ASSETS)/props.c1
PROPS_C2     = $(ASSETS)/props.c2
# Task P2: the per-angle layout, generated on the host from
# src/props_layout.c (tests/props_table_gen.c) and read by src/props.c.
PROPS_TABLE_H = $(BUILDDIR)/props_table.h
# dome-scenery Task 17: the band of towns and forests — a 768 px panorama of
# 48 x 2 tiles from tools/render_band.py (the orchestrator's art; this
# Makefile only gives it paths), its map header (size, place and palette) and
# the c1/c2 payloads. The part joins the C ROM LAST (after the props' in
# CROM1_PARTS/CROM2_PARTS) so no existing tile base moves: src/band.c adds
# PROP_TILE_BASE + PROP_TILES, so the tile at each relative number is the
# picture's tile.
BAND_MAP      = $(BUILDDIR)/band_map.h
BAND_C1       = $(ASSETS)/band.c1
BAND_C2       = $(ASSETS)/band.c2
# the collapse's ruin (the collapse redo's Task C1): one 8 x 6-tile picture
# for every dome angle, from tools/render_collapse.py (the orchestrator's
# art; this Makefile only gives it paths). The part joins the C ROM LAST,
# after the band (the order CROM1_PARTS / CROM2_PARTS list), so no existing
# tile base moves. C1 uses only the ruin's numbers; the rest of the header
# is for Tasks C2-C4. src/dome.h adds BAND_TILE_BASE + BAND_TILES.
COLLAPSE_MAP  = $(BUILDDIR)/collapse_map.h
COLLAPSE_C1   = $(ASSETS)/collapse.c1
COLLAPSE_C2   = $(ASSETS)/collapse.c2
# R1/K1: the sound pipeline. tools/synth_sfx.py renders the game's
# move/jump/fire/hit/crack and the initials picker's tick/type/bell/
# backspace as mono 16-bit WAVs at 18500 Hz (the ADPCM-A encoder's rate);
# the lock-on pip stays tools/render_sfx.py's (187500 Hz, resampled by
# sox). vromtool.py packs them into the 524288-byte V ROM and emits
# build/samples.inc, the START/STOP ASM defines sound/user_commands.s
# includes. The M ROM is nullsound + user_commands.s (the command table: 3
# reset, 4..9 the game's samples, 10..13 the picker's), assembled/linked/
# objcopied instead of the stock nullsound_driver.ihx.
SFX_SYNTH_RAW = $(addprefix $(BUILDDIR)/sfx-synth/,move.wav jump.wav fire.wav hit.wav crack.wav tick.wav bell.wav backspace.wav)
# the picked letter's typewriter strike is a CC0 recording (CREDITS.md)
SFX_ASSET_RAW = assets/sfx/type.wav
SFX_VEC_RAW   = $(BUILDDIR)/sfx-vectrex/pip.wav
SFX_RAW       = $(SFX_SYNTH_RAW) $(SFX_VEC_RAW) $(SFX_ASSET_RAW)
SFX_DIR       = $(BUILDDIR)/sfx
SFX_WAVS      = $(addprefix $(SFX_DIR)/,move.wav jump.wav fire.wav hit.wav crack.wav pip.wav tick.wav type.wav bell.wav backspace.wav)
SFX_MAP       = sound/samples-map.yaml
SAMPLES_INC  = $(BUILDDIR)/samples.inc
SOUND_REL    = $(BUILDDIR)/user_commands.rel
SOUND_IHX    = $(BUILDDIR)/sound_driver.ihx

# generated headers every object may include (later tasks add to this)
GEN_HEADERS = $(FIX_PAL) $(TITLE_FONT_H) $(DOME_MAP) $(DOME_PAL) $(CELLS_H) $(DEMO_MAP) $(RING_MAP) $(RING_C1) $(RING_C2) $(SHIP_MAP) $(SHIP_PAL) $(MIS_TABLES) $(MIS_MAP) $(BROKEN_MAP) $(RADAR_TABLES) $(RADAR_MAP) $(RADAR_C1) $(RADAR_C2) $(GROUND_MAP) $(GROUND_C1) $(GROUND_C2) $(MTN_MAP) $(MTN_C1) $(MTN_C2) $(CON_MAP) $(CON_C1) $(CON_C2) $(PROPS_MAP) $(PROPS_C1) $(PROPS_C2) $(BAND_MAP) $(BAND_C1) $(BAND_C2) $(COLLAPSE_MAP) $(COLLAPSE_C1) $(COLLAPSE_C2)
CROM1_PARTS = $(DOME_C1) $(SHIP_C1) $(MIS_SHEETS:.gif=.c1) $(BROKEN_PART) $(RADAR_C1) $(GROUND_C1) $(MTN_C1) $(CON_C1) $(PROPS_C1) $(BAND_C1) $(COLLAPSE_C1) $(RING_C1)
CROM2_PARTS = $(DOME_C2) $(SHIP_C2) $(MIS_SHEETS:.gif=.c2) $(BROKEN_C2) $(RADAR_C2) $(GROUND_C2) $(MTN_C2) $(CON_C2) $(PROPS_C2) $(BAND_C2) $(COLLAPSE_C2) $(RING_C2)

.PHONY: all cart test clean boot-test mame
all: cart
$(ASSETS):
	mkdir -p $@

# slots.lua/json are generated from src/slots.h (the one slot map).
$(SLOTS_LUA) $(SLOTS_JSON) &: src/slots.h $(DOME_MAP) tools/gen_slots.py | $(BUILDDIR)
	python3 tools/gen_slots.py $(BUILDDIR)

# Attract Task A3: the demo script (tools/gen_demo.py is the orchestrator's;
# this rule only gives it the paths). The generator replays the host models
# and writes the cart's input runs (build/demo_map.h, included by
# src/demo.c) and the events the demo boot-test states (build/demo.json).
$(DEMO_MAP) $(DEMO_JSON) &: tools/gen_demo.py tests/hud_model.py \
		tests/mis_model.py tests/radar_model.py tests/rules_model.py \
		tests/ship_model.py tests/fixtures/vectrex_cells.json $(MIS_TABLES) | $(BUILDDIR)
	python3 tools/gen_demo.py $(DEMO_MAP) --json $(DEMO_JSON) > /dev/null

# high-score boards Task B5: the ring's header (entry.c reads RING_N,
# RING_SUB, RING_PHASES, RING_ERASE, RING_END and ring_code from it) and
# the sheet Task B6 joins to the C ROM. The generator is the orchestrator's;
# this rule only gives it the paths.
$(RING_GIF) $(RING_MAP) &: tools/render_ring.py tools/generate_srom.py | $(ASSETS) $(BUILDDIR)
	python3 tools/render_ring.py $(RING_GIF) $(RING_MAP)

$(RING_C1) $(RING_C2) &: $(RING_GIF)
	$(BIN)/tiletool.py -c --sprite $< -o $(RING_C1) $(RING_C2)

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

# the ship: the 1950s hovercraft, 48 latitude views x 13 pictures (REST,
# WALK, JUMP, HEAVE) and its 64 bolt tiles, right after the dome's
# (tools/render_hovercraft.py is the orchestrator's; this rule only gives it
# the paths)
$(SHIP_GIF) $(SHIP_MAP) &: tools/render_hovercraft.py tools/gen_missiles.py \
		tools/vectrex_missiles.json tools/render_dome.py tools/geometry.py | $(ASSETS)
	python3 tools/render_hovercraft.py $(SHIP_GIF) $(SHIP_MAP) > /dev/null

$(SHIP_C1) $(SHIP_C2) &: $(SHIP_GIF)
	$(BIN)/tiletool.py -c --sprite $< -o $(SHIP_C1) $(SHIP_C2)

$(SHIP_PAL): $(SHIP_GIF)
	$(BIN)/paltool.py $< -o $@.tmp
	sed 's/},[[:space:]]*$$/}/' $@.tmp > $@ && rm $@.tmp

# missiles and bullets: tables (rings, flights, projection) and pictures
$(MIS_TABLES): tools/gen_missiles.py tools/geometry.py tools/vectrex_missiles.json | $(BUILDDIR)
	python3 tools/gen_missiles.py $@ > /dev/null

$(MIS_SHEETS) $(MIS_MAP) &: tools/render_rockets.py tools/render_missiles.py tools/gen_missiles.py \
		tools/render_hovercraft.py tools/render_dome.py tools/geometry.py tools/vectrex_missiles.json \
		| $(ASSETS)
	python3 tools/render_rockets.py $(ASSETS) $(MIS_MAP) > /dev/null

# broken-window overlays: the art + the per-cell tables (M4-fixes Task 3).
# render_broken.py writes broken.c1/c2 itself — the tiles are packed in the
# runtime's fetch order (BROKEN_TILE_BASE + tile0[cell] + view_t0[cell][view]
# + r*w + c), which no tiletool sheet (row-major over a rectangle) can
# express, and that packing is what keeps the C ROM as small as the content
# allows (the old sheet's 20,735 padded places are gone; the whole C ROM is
# 1.22 MB, so CROMSIZE = 2 MB — the smallest power of two that fits).
$(BROKEN_PART) $(BROKEN_C2) $(BROKEN_MAP) &: tools/render_broken.py tools/render_rockets.py \
		tools/render_missiles.py tools/render_hovercraft.py tools/render_dome.py \
		tools/gen_missiles.py tools/geometry.py $(SLOTS_JSON) | $(ASSETS)
	python3 tools/render_broken.py $(ASSETS) $(BROKEN_MAP) > /dev/null

$(ASSETS)/%.c1 $(ASSETS)/%.c2: $(ASSETS)/%.gif
	$(BIN)/tiletool.py -c --sprite $< -o $(ASSETS)/$*.c1 $(ASSETS)/$*.c2

# the radar's pictures (M5 Task 4): one grouped rule emits the map header
# and the three c1/c2 part pairs (frame, sticks, headings) in the C ROM
# order, after the broken sheet (the star tile is gone, Task 4). The
# generator reads the constants from
# src/radar.h and the Neo Geo's zoom table from aes.zip (the headings are
# solved against it) and verifies its own output as it goes.
$(RADAR_MAP) $(RADAR_C1) $(RADAR_C2) &: tools/render_radar.py tools/render_broken.py \
		tools/render_hovercraft.py $(BROKEN_MAP) $(BROKEN_PART) src/radar.h $(SLOTS_JSON) \
		| $(BUILDDIR) $(ASSETS)
	python3 tools/render_radar.py $(RADAR_MAP) $(ASSETS)/radar-frame.c1 $(ASSETS)/radar-frame.c2 \
		$(ASSETS)/radar-stick.c1 $(ASSETS)/radar-stick.c2 \
		$(ASSETS)/radar-head.c1 $(ASSETS)/radar-head.c2 > /dev/null

# the radar's tables: per ring the spot's x factor, y factor and stick
# height (all / (R/6), from src/radar.h's constants and the rings' polar
# angles), per screen azimuth j sin and cos — the 16-bit tables
# src/radar.c's per-frame maths read
$(RADAR_TABLES): tools/gen_radar.py tools/geometry.py tools/gen_missiles.py src/radar.h $(MIS_TABLES) | $(BUILDDIR)
	python3 tools/gen_radar.py $@ > /dev/null

# the ground's picture (dome-scenery Tasks 5 and 19): one rule emits the map
# header and the c1/c2 payloads, after the radar's parts in the C ROM (the
# order CROM1_PARTS / CROM2_PARTS list). Task 19's generator is
# tools/render_ripple.py: the same block and tiles, re-indexed for the
# palette rotation, plus the ripple banks/palettes/rotations. The generator
# is the orchestrator's and is never edited for the picture or palette; this
# rule only gives it the paths. It writes the header's tile numbers RELATIVE
# to the ground part's first tile (0..GROUND_TILES-1); src/ground.c adds the
# part base.
$(GROUND_MAP) $(GROUND_C1) $(GROUND_C2) &: tools/render_ripple.py tools/render_scenery.py tools/render_dome.py tools/render_console.py tools/render_props.py tools/geometry.py tests/layout.py src/dome.h | $(BUILDDIR) $(ASSETS)
	python3 tools/render_ripple.py $(GROUND_MAP) $(GROUND_C1) $(GROUND_C2)

# the mountains' picture (dome-scenery Task 6): one rule emits the map
# header and the c1/c2 payloads, after the ground's part in the C ROM (the
# order CROM1_PARTS / CROM2_PARTS list). The generator is the
# orchestrator's and is never edited for the picture or palette; this rule
# only gives it the paths. It writes the header's tile numbers RELATIVE to
# the mountain part's first tile (0..MTN_TILES-1); src/mountains.c adds the
# part base.
$(MTN_MAP) $(MTN_C1) $(MTN_C2) &: tools/render_mountains.py tools/render_scenery.py tools/render_dome.py tools/geometry.py | $(BUILDDIR) $(ASSETS)
	python3 tools/render_mountains.py $(MTN_MAP) $(MTN_C1) $(MTN_C2)

# the console's picture (dome-scenery Task 7): one rule emits the map header
# and the c1/c2 payloads, after the mountains' part in the C ROM (the order
# CROM1_PARTS / CROM2_PARTS list). The generator is the orchestrator's and is
# never edited for the picture or palette; this rule only gives it the paths.
# It writes the header's con_first[c] tile numbers RELATIVE to the console
# part's first tile; src/console.c adds the part base.
$(CON_MAP) $(CON_C1) $(CON_C2) &: tools/render_console.py tools/render_scenery.py tools/render_dome.py tools/geometry.py | $(BUILDDIR) $(ASSETS)
	python3 tools/render_console.py $(CON_MAP) $(CON_C1) $(CON_C2)

# the props' map and picture (dome-scenery Task 11): one rule emits the map
# header and the c1/c2 payloads, from the orchestrator's generator (never
# edited for the picture, palette or places; this rule only gives it the
# paths). The header's tile numbers are RELATIVE to the props part's first
# tile (0..PROP_TILES-1); Task 12's src/props.h adds PROP_TILE_BASE.
$(PROPS_MAP) $(PROPS_C1) $(PROPS_C2) &: tools/render_props.py tools/render_scenery.py tools/render_dome.py tools/render_console.py tools/geometry.py tests/layout.py src/dome.h | $(BUILDDIR) $(ASSETS)
	python3 tools/render_props.py $(PROPS_MAP) $(PROPS_C1) $(PROPS_C2)

# the towns-and-forests band (dome-scenery Task 17): one rule emits the map
# header and the c1/c2 payloads, LAST in the C ROM (the order CROM1_PARTS /
# CROM2_PARTS list). The generator is the orchestrator's and is never edited
# for the picture or palette; this rule only gives it the paths. It writes
# the header's tile numbers RELATIVE to the band part's first tile
# (0..BAND_TILES-1); src/band.c adds PROP_TILE_BASE + PROP_TILES.
$(BAND_MAP) $(BAND_C1) $(BAND_C2) &: tools/render_band.py tools/render_scenery.py tools/render_dome.py tools/geometry.py | $(BUILDDIR) $(ASSETS)
	python3 tools/render_band.py $(BAND_MAP) $(BAND_C1) $(BAND_C2)

# the collapse's ruin (the collapse redo's Task C1): one rule emits the map
# header and the c1/c2 payloads, LAST in the C ROM (the order CROM1_PARTS /
# CROM2_PARTS list). The generator is the orchestrator's and is never edited
# for the picture, palette or tables; this rule only gives it the paths.
# The header's tile numbers are RELATIVE to the collapse part's first tile
# (0..COLLAPSE_TILES-1); src/dome.c adds COLLAPSE_TILE_BASE
# (BAND_TILE_BASE + BAND_TILES, src/dome.h).
$(COLLAPSE_MAP) $(COLLAPSE_C1) $(COLLAPSE_C2) &: tools/render_collapse.py tools/render_dome.py tools/render_broken.py tools/render_radar.py tools/render_scenery.py tools/geometry.py tests/layout.py src/dome.h $(SLOTS_JSON) | $(BUILDDIR) $(ASSETS)
	python3 tools/render_collapse.py $(COLLAPSE_MAP) $(COLLAPSE_C1) $(COLLAPSE_C2)

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

# S ROM: ASCII fix tiles (tile = character code) plus, from tile 512, the
# thick-outline title font (high-score boards Task B4). The old blocks stay
# byte-identical; the S ROM grows to 128 KB (4096 tiles).
$(SROM1) $(FIX_PAL) $(TITLE_FONT_H) &: tools/generate_srom.py src/title.h | $(ROMDIR) $(BUILDDIR)
	python3 tools/generate_srom.py --ascii --output $(SROM1) --pal-header $(FIX_PAL) --title2-header $(TITLE_FONT_H)
	@test $$(stat -c%s $(SROM1)) -eq 131072 || { echo "S ROM must be 131072 bytes"; exit 1; }

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

# V ROM: the game's six effects plus the picker's four, packed by
# vromtool.py into the fixed 524288-byte V ROM (--roms actually writes it;
# --asm alone only emits the defines). build/samples.inc carries the
# START/STOP defines the sound driver reads.
$(VROM1): $(SOUND_IHX) $(SAMPLES_INC) | $(ROMDIR)
	$(BIN)/vromtool.py --roms -s 524288 -n 1 $(SFX_MAP) -o $(VROM1) -m $(SAMPLES_INC)
$(SAMPLES_INC): $(SFX_WAVS) $(SFX_MAP) | $(BUILDDIR)
	$(BIN)/vromtool.py --asm -s 524288 $(SFX_MAP) -o $(VROM1) -m $@
$(SFX_WAVS): $(SFX_RAW) | $(SFX_DIR)   # prereqs only; the rules below do the sox
$(SFX_DIR)/%.wav: $(BUILDDIR)/sfx-synth/%.wav | $(SFX_DIR)
	sox $< -r 18500 $@
$(SFX_DIR)/pip.wav: $(BUILDDIR)/sfx-vectrex/pip.wav | $(SFX_DIR)
	sox $< -r 18500 $@
$(SFX_DIR)/type.wav: $(SFX_ASSET_RAW) | $(SFX_DIR)
	sox $< -r 18500 $@
$(SFX_SYNTH_RAW) &: tools/synth_sfx.py | $(BUILDDIR) $(BUILDDIR)/sfx-synth
	python3 tools/synth_sfx.py $(BUILDDIR)/sfx-synth
$(SFX_VEC_RAW): tools/render_sfx.py | $(BUILDDIR) $(BUILDDIR)/sfx-vectrex
	python3 tools/render_sfx.py $(BUILDDIR)/sfx-vectrex
$(SFX_DIR) $(BUILDDIR)/sfx-synth $(BUILDDIR)/sfx-vectrex:
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
# the -DSOUND_TEST carts need a collapse stub with no BSS: their sound-test
# RAM log lives in flow.o, and collapse.o's RAM would shift it (the MVS
# BIOS's garbage at the shifted address passes the sound probe's gates).
$(BUILDDIR)/collapse-soundtest.o: src/collapse.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSOUND_TEST -c src/collapse.c -o $@
$(SNDTEST_ELF): $(OBJS) $(BUILDDIR)/collapse-soundtest.o $(BUILDDIR)/main-soundtest.o $(BUILDDIR)/flow-soundtest.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o $(BUILDDIR)/collapse.o,$(OBJS)) \
		$(BUILDDIR)/collapse-soundtest.o $(BUILDDIR)/main-soundtest.o $(BUILDDIR)/flow-soundtest.o $(LDFLAGS)
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
$(SNDRAD_ELF): $(OBJS) $(BUILDDIR)/collapse-soundtest.o $(BUILDDIR)/main-soundradar.o $(BUILDDIR)/flow-soundradar.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o $(BUILDDIR)/collapse.o,$(OBJS)) \
		$(BUILDDIR)/collapse-soundtest.o $(BUILDDIR)/main-soundradar.o $(BUILDDIR)/flow-soundradar.o $(LDFLAGS)
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

# Attract Task A3: the pre-A3 title-scene and gameplay boot tests were
# calibrated on a static fresh title. Build the same cart with the demo
# compiled out (STATIC_TITLE) for those legs; the demo legs and the
# flow/Start legs keep the normal cart (and the normal FRAME_MARK cart).
STATIC_ELF = $(BUILDDIR)/rom-static.elf
STATIC_PROM = $(ROMDIR)/esrg-static-p1.p1
STATIC_CART = $(ROMDIR)/esrg-static.zip
$(BUILDDIR)/flow-static.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSTATIC_TITLE -c src/flow.c -o $@
$(STATIC_ELF): $(OBJS) $(BUILDDIR)/flow-static.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/flow-static.o $(LDFLAGS)
$(STATIC_PROM): $(STATIC_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(STATIC_CART): $(STATIC_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(STATIC_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-static -l "E-SRG (static title)" -o $@
.PHONY: static-cart
static-cart: $(STATIC_CART)

STATIC_FM_ELF = $(BUILDDIR)/rom-staticfm.elf
STATIC_FM_PROM = $(ROMDIR)/esrg-staticfm-p1.p1
STATIC_FM_CART = $(ROMDIR)/esrg-staticfm.zip
$(BUILDDIR)/flow-staticfm.o: src/flow.c $(wildcard src/*.h) $(GEN_HEADERS) | $(BUILDDIR)
	$(CC68K) $(CFLAGS) -DSTATIC_TITLE -DFRAME_MARK -c src/flow.c -o $@
$(STATIC_FM_ELF): $(OBJS) $(BUILDDIR)/main-framemark.o $(BUILDDIR)/flow-staticfm.o
	$(CC68K) -o $@ $(filter-out $(BUILDDIR)/main.o $(BUILDDIR)/flow.o,$(OBJS)) \
		$(BUILDDIR)/main-framemark.o $(BUILDDIR)/flow-staticfm.o $(LDFLAGS)
$(STATIC_FM_PROM): $(STATIC_FM_ELF) | $(ROMDIR)
	$(OBJCOPY68) -O binary -S -R .text2 --gap-fill 0xff --pad-to $(PROMSIZE) $< $@
	dd if=$@ of=$@ conv=notrunc,swab status=none
$(STATIC_FM_CART): $(STATIC_FM_PROM) $(SROM1) $(CROM1) $(CROM2) $(MROM1) $(VROM1)
	$(BIN)/romtool.py -b cartridge -f zip -p $(STATIC_FM_PROM) -s $(SROM1) \
		-c $(CROM1) $(CROM2) -m $(MROM1) -v $(VROM1) \
		-n esrg-staticfm -l "E-SRG (static title, frame mark)" -o $@
.PHONY: staticfm-cart
staticfm-cart: $(STATIC_FM_CART)

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
# Task S2: the frame choice, host-built against the real ship.c / missiles.c /
# rules.c. tests/check_spider.py --host holds it to tests/ship_anim_model.py.
$(BUILDDIR)/spider_sim: tests/spider_sim.c src/ship.c src/ship.h src/missiles.c \
		src/missiles.h src/rules.c src/rules.h src/ship_gfx.c src/ship_gfx.h \
		$(CELLS_H) $(MIS_TABLES) $(SHIP_MAP) $(SHIP_PAL) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/spider_sim.c src/ship.c src/missiles.c \
		src/rules.c src/ship_gfx.c -o $@

# dome-scenery Task 11: the props' layout, pure logic, held to
# tests/props_model.py by tests/test_props.py.
$(BUILDDIR)/props_sim: tests/props_sim.c src/props_layout.c src/props_layout.h $(PROPS_MAP) $(PROPS_C1) $(PROPS_C2) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/props_sim.c src/props_layout.c -o $@
# Task P2: the generator writes build/props_table.h from props_layout();
# the same source built with -DPROPS_TABLE_CHECK is the host test that
# every field of both tables equals props_layout() at every angle.
$(BUILDDIR)/props_table_gen: tests/props_table_gen.c src/props_layout.c src/props_layout.h $(PROPS_MAP) $(PROPS_C1) $(PROPS_C2) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/props_table_gen.c src/props_layout.c -o $@
$(PROPS_TABLE_H): $(BUILDDIR)/props_table_gen | $(BUILDDIR)
	$(BUILDDIR)/props_table_gen > $@.tmp && mv $@.tmp $@
$(BUILDDIR)/test_props_table: tests/props_table_gen.c $(PROPS_TABLE_H) src/props_layout.c src/props_layout.h $(PROPS_MAP) $(PROPS_C1) $(PROPS_C2) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) -DPROPS_TABLE_CHECK tests/props_table_gen.c src/props_layout.c -o $@
# the attract demo's skipped props commits (P1): src/props.c's real
# prepare/commit against a VRAM model (tests/host_vram), every commit held
# to the layout of the last prepared angle.
$(BUILDDIR)/test_props_commit: tests/test_props_commit.c src/props.c src/props.h src/props_layout.c src/props_layout.h tests/host_vram/ngdevkit/neogeo.h $(GEN_HEADERS) $(PROPS_TABLE_H) | $(BUILDDIR)
	$(HOSTCC) -std=c99 -Wall -Wextra -Itests/host_vram -Isrc -I$(BUILDDIR) tests/test_props_commit.c src/props.c src/props_layout.c -o $@
# Task P2: src/props.c includes the generated table.
$(BUILDDIR)/props.o: $(PROPS_TABLE_H)
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

# R1: the frame's sound command list, host-built from the real ship.c /
# missiles.c / rules.c / radar.c and src/sound.h's sound_frame_cmds (the
# same function flow.c's game_sound calls), held to tests/sound_model.py by
# tests/test_sound_host.py.
$(BUILDDIR)/sound_sim: tests/sound_sim.c src/sound.h src/ship.h src/missiles.h \
		src/rules.h src/radar.h src/ship.c src/missiles.c src/rules.c src/radar.c \
		$(CELLS_H) $(MIS_TABLES) $(RADAR_TABLES) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/sound_sim.c src/ship.c src/missiles.c src/rules.c src/radar.c -o $@

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
	src/hud.c src/hud.h src/fix.c src/fix.h $(CELLS_H) $(MIS_TABLES) $(FIX_PAL) $(TITLE_FONT_H)
$(BUILDDIR)/test_hud: tests/test_hud.c $(HUD_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_hud.c src/ship.c src/missiles.c src/rules.c src/hud.c src/fix.c -o $@

# the title's nine pages of fix text (M6 Task 5): pure logic, host-built,
# held to tests/title_model.py by tests/test_title.py. The cart object is
# built too (SRCS picks src/title.c up) but unused until Task 6 draws it.
$(BUILDDIR)/title_sim: tests/title_sim.c src/title.c src/title.h | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/title_sim.c src/title.c -o $@

# high-score boards Task B1: the five-entry per-level board, pure logic,
# host-built, held to tests/board_model.py by tests/test_board.py. Task B2
# keeps it in flow_board in backup RAM / on the AES memory card and the
# title shows each level's top entry.
$(BUILDDIR)/board_sim: tests/board_sim.c src/board.c src/board.h src/missiles.h | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/board_sim.c src/board.c -o $@

# high-score boards Task B5: the initials ring's state machine, pure logic,
# host-built, held to tests/entry_model.py by tests/test_entry.py.
$(BUILDDIR)/entry_sim: tests/entry_sim.c src/entry.c src/entry.h $(RING_MAP) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/entry_sim.c src/entry.c -o $@

DOME_HOST = src/dome.c src/dome.h src/cracks.c src/cracks.h src/rules.c src/rules.h src/ship.c src/ship.h src/missiles.c src/missiles.h $(CELLS_H) $(BROKEN_MAP)
$(BUILDDIR)/test_go_dome: tests/test_go_dome.c $(DOME_HOST) | $(BUILDDIR)
	$(HOSTCC) $(HOSTCFLAGS) tests/test_go_dome.c src/dome.c src/cracks.c src/rules.c src/ship.c src/missiles.c -o $@

test: cart $(SLOTS_LUA) $(SLOTS_JSON) $(BUILDDIR)/test_ship $(BUILDDIR)/ship_sim $(BUILDDIR)/spider_sim $(BUILDDIR)/test_missiles $(BUILDDIR)/mis_sim \
		$(BUILDDIR)/view_sim $(BUILDDIR)/rules_sim $(BUILDDIR)/test_rules $(BUILDDIR)/test_broken \
		$(BUILDDIR)/broken_tiles_dump $(BUILDDIR)/test_hud $(BUILDDIR)/test_collapse $(BUILDDIR)/collapse_sim \
		$(BUILDDIR)/test_go_dome $(BUILDDIR)/radar_sim $(BUILDDIR)/title_sim \
		$(BUILDDIR)/board_sim $(BUILDDIR)/entry_sim $(BUILDDIR)/props_sim $(BUILDDIR)/sound_sim $(BUILDDIR)/test_props_commit \
		$(BUILDDIR)/test_props_table
	$(BUILDDIR)/test_ship
	$(BUILDDIR)/test_missiles
	$(BUILDDIR)/test_rules
	$(BUILDDIR)/test_broken
	$(BUILDDIR)/test_hud
	$(BUILDDIR)/test_collapse
	$(BUILDDIR)/test_go_dome
	$(BUILDDIR)/test_props_commit
	$(BUILDDIR)/test_props_table
	$(BUILDDIR)/board_sim < /dev/null > /dev/null	# B1/B2: the sim builds and runs
	$(BUILDDIR)/entry_sim < /dev/null > /dev/null	# B5: the sim builds and runs
	python3 -m pytest tests -q
	python3 tests/check_spider.py --host

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
boot-test: cart crktest-cart crackframemark-cart framemark-cart static-cart staticfm-cart godraw-cart radartest-cart soundtest-cart soundradar-cart $(SLOTS_LUA) $(SLOTS_JSON)
	# every leg (headless MAME + its checker) runs from scripts/boot_test_all.sh,
	# the leg list's one home: in parallel (BOOT_JOBS at a time, default half
	# the cores), each leg in its own build/boot-legs/ directory, the outputs
	# printed in order. BOOT_JOBS=1 runs them one at a time.
	CRKTEST_CART="$(CRKTEST_CART)" GET_CART="$(GET_CART)" RADTEST_CART="$(RADTEST_CART)" \
	    scripts/boot_test_all.sh

mame: cart
	scripts/mame.sh

clean:
	rm -rf $(BUILDDIR)
