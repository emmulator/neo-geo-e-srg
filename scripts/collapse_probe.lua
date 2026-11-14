-- collapse_probe.lua: the M4 Task 4 collapse boot-test.
--
-- Drives the normal cart through a deterministic full game (centred stick,
-- A tapped every 11 frames — the fire keeps kills below 6, and under the
-- Vectrex 1.1.0 rule the 6th dome hit that breaks a cell opens every ring,
-- so three clean dome deaths follow; the ship never moves, so it never dies
-- on a broken cell) and proves, from VRAM and snapshots:
--   1. the dome's columns move during the shake: mid-collapse SCB3/SCB4
--      of the dome slots differ from the fixed positions, and the columns
--      are NOT chained (their SCB4 Xs differ from the fixed
--      DOME_X + c*16 while the shake runs);
--   2. the columns are gone by the end of the collapse: past
--      COLLAPSE_GONE, every dome slot's SCB3 height is 0;
--   3. the rebuilt dome's VRAM matches a fresh dome's: the dump taken
--      after the first rebuild (fc 8492, 118 after the death; the dump at
--      fc 8513 gives the rebuild a few frames to settle) has the same
--      SCB2/3/4 chain and
--      palette as the "fresh" dump taken on cart frame 60 (the SCB1 tile
--      lists legitimately differ — the dome turns behind the ship, and the
--      two frames are at different views);
--   4. the fix layer reaches GAME OVER within a frame budget derived from
--      the rules: the centred policy's model says GAME OVER at cart frame
--      27142 under Task 1's seed (tests/check_collapse.py replays the model from the recorded
--      inputs and checks GAME OVER appears on row 7 by the model's own
--      frame — the "budget" is the model's derivation, not a guess).
--
-- Task 1 seeds the missiles from the title's time (the default Start at
-- MAME 600 -> seed 0xaede), so the timelines moved: the first dome death
-- is at cart frame 8359 (the model derivation), the rebuild at 8492.
-- The probe's samples span cart frames 8290..8492, so they bracket the
-- whole first
-- collapse.
--
-- The probe outputs:
--   I <rec> <fc> <cur> <chg>      every record (the input read-back truth)
--   S <fc> <scb3_DOME_SPRITE> .. <scb3_DOME_SPRITE+7>  the 8 dome slots' SCB3 words
--   G <fc> <gone>                  every sampled frame: 1 = all 8 SCB3
--                                  heights are 0 (the old hide, kept for the
--                                  shake/historic check)
--   U <fc> <scb4> <tile0> <attr0> ...  the box chain's 8 SCB4 words and every
--                                  column's SCB1 rows 0..RUIN_ROWS-1 (Task C1)
--   H <fc>                         a fresh dump follows
--   h <slot> <scb2> <scb3> <scb4> <attr> <tile8...>   fresh slot row
--   R <fc> <slot> <scb2> <scb3> <scb4> <attr> <tile rows>  rebuilt slot row
--   P <pal15 words>      fresh dome palette (bank PAL_DOME, entries 1..15)
--   Q <pal15 words>      rebuilt dome palette (decimal)
--   F <fc>               a fix-layer row block follows (all 10 rows)
--   FR <row> <40 chars>  fix row r decoded (Task C5 renamed it from W so
--                        the raw worst dump can use W/w)
--   W <fc> <count> <line>  Task C5: the collapse census's overall worst
--   w <slot> <scb3> ...    all 381 slots' raw SCB3 on that frame
--   SNAP <fc>            a snapshot was taken this frame
--   X <fc> <slot> <scb3> <scb4>   every slot's box at the snapshot
--   L <fc> <slot> <reg> <vpos>    every write to a dome slot (Task C1)
--   RUIN <fc>            Task C2: the dome slot 0's SCB1 attribute turned
--                        PAL_RUIN << 8 (the burst marker)
--   V <fc> <col> <scb2> <scb3> <scb4> <tile0> <attr0> ...  the fire slot's
--                        words and SCB1 rows 0..31, every frame from the
--                        ruin switch through g 60 (Task C2)
--   T <fc> <slot> <scb3> <scb4> <scb2>  every fire slot's span each frame
--                        (Task C2's tear proof)
--   KW <fc> <slot> <reg> <vpos>   every write to a fire slot (Task C2;
--                                 tagged KW so Task C5's K lines are free)
--   K <fc> <g> <count> <line>     Task C5: the sprites-per-scanline census
--                                 on every frame of every dome death's
--                                 collapse (g = the collapse's own g)
--   Z <fc> <n> <scb2> <scb3> <scb4> <t0> <a0> <t1> <a1>
--                                 the fragment slot's words and SCB1 rows
--                                 0..FRAG_MAX_ROWS-1, every frame from the
--                                 ruin switch through g FRAG_T + 1 (Task C3)
--   B <fc> <n> <t2> <a2> ... <t31> <a31>
--                                 the fragment slot's blank rows, once (Task
--                                 C3: the blanking on the collapse's first
--                                 frame)
--   N <fc> <slot> <scb3> <scb4> <scb2>  every fragment slot's span each
--                                 frame (Task C3's tear proof)
--   Y <fc> <slot> <reg> <vpos>    every write to a fragment slot (Task C3)
--   SNAP <fc>                    a snapshot was taken this frame (the ruin
--                                 switch, then the fire/fragments at g 2,
--                                 10, 12, 30 and 40)
-- Env: OUT, FRAMES, HUD_FRAMECNT_ADDR (0 disables the exact alignment).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "25700")
local framecnt_addr = tonumber(os.getenv("COLLAPSE_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local DOME_SPRITE, DOME_COLS, DOME_ROWS = S.DOME_SPRITE, S.DOME_COUNT, 6
local RUIN_ROWS = 5                       -- build/collapse_map.h RUIN_ROWS (V2)
local COLLAPSE_GONE = 100
local PAL_RUIN = 55                       -- src/dome.h
local PAL_FIRE = 56                       -- src/collapse.h
local PAL_BASE = 0x400000
-- Task C2: the fireball's slots and its SCB1 rows (the hardware can sample
-- up to row 31; the probe dumps all of them).
local FIRE_SPRITE, FIRE_COLS = S.COLLAPSE_FIRE_SPRITE, S.COLLAPSE_FIRE_COUNT
local FIRE_SCB1_ROWS = 32
local FIRE_T = 45                         -- build/collapse_map.h FIRE_T
-- Task C3: the fragments, one full-size column each, in the dome's pal.
local FRAG_SPRITE, FRAG_COUNT = S.COLLAPSE_FRAG_SPRITE, S.COLLAPSE_FRAG_COUNT
local FRAG_T = 77                         -- build/collapse_map.h FRAG_T
local FRAG_MAX_ROWS = 2                   -- build/collapse_map.h FRAG_MAX_ROWS
local FRAG_SCB1_ROWS = 32
local PAL_DOME = 1                        -- src/dome.h
local COLLAPSE_SHAKE = 41                 -- src/rules.h
local DEAD_FRAMES = 118                   -- src/rules.h
-- Task C4/V1: the puffs (six slots, three pairs) and the smoke (twelve
-- columns: six BACK slots right below DOME_SPRITE, six FRONT slots in the
-- overlay range).
local PUFF_SPRITE, PUFF_COUNT = S.COLLAPSE_PUFF_SPRITE, S.COLLAPSE_PUFF_COUNT
local PUFF_ROWS = 2                       -- build/collapse_map.h PUFF_ROWS
local PUFF_SCB1_ROWS = 32
local SMOKE_BACK_SPRITE, SMOKE_BACK_COUNT = S.SMOKE_BACK_SPRITE,
    S.SMOKE_BACK_COUNT
local SMOKE_SPRITE, SMOKE_COUNT = S.COLLAPSE_SMOKE_SPRITE, S.COLLAPSE_SMOKE_COUNT
local SMOKE_TOTAL = SMOKE_BACK_COUNT + SMOKE_COUNT
local SMOKE_ROWS = 7                      -- build/collapse_map.h SMOKE_ROWS
local SMOKE_SCB1_ROWS = 32
local PAL_SMOKE = 57                      -- src/collapse.h
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1), and exposes game_started(fc) to keep our drive() off the title
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")
local MS = dofile((os.getenv("REPO") or ".") .. "/scripts/mis_seed.lua")

-- VRAM is read (and, by the leftover probe, written) through MAME's own copy
-- of it, never through the LSPC registers at 0x3c0000/2: writing the address
-- register from a frame callback changes the cart's VRAM pointer under it, and
-- the cart's next writes land at the probe's address (it zeroed title rows).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end

local function hold(name, on)
    joy.fields[name]:set_value(on and 1 or 0)
end

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0

-- Task C1: tap the LSPC registers (as scripts/tear_probe.lua does) to
-- record the raster line of every write to a dome slot. The ruin's switch
-- writes (the re-chain and the 8 columns' SCB1 lists) must land before the
-- dome box's first visible line: vpos < DOME_Y + 16 (screen line DOME_Y =
-- vpos DOME_Y + 16). fc_now is set at the end of each tick to the NEXT
-- frame's cart frame: hud_frame increments hud_framecnt before
-- dome_collapse runs, so the writes of that frame carry that frame's fc.
local cur, mod = 0, 1
local fc_now = 0
local function vpos()
    -- src/flow.c lspc_vpos: ((LSPCMODE >> 7) & 0x1ff) - 0x100
    return ((sp:read_u16(0x3c0006) >> 7) & 0x1ff) - 0x100
end
local function on_write(offset, data, mask)
    local reg = offset & 0x6
    if reg == 0 then
        cur = data
    elseif reg == 4 then
        mod = data
    elseif reg == 2 then
        local a = cur
        local kind, slot = 0, -1
        if a < 0x7000 then kind, slot = 1, a // 64
        elseif a >= 0x8000 and a < 0x8200 then kind, slot = 2, a - 0x8000
        elseif a >= 0x8200 and a < 0x8400 then kind, slot = 3, a - 0x8200
        elseif a >= 0x8400 and a < 0x8600 then kind, slot = 4, a - 0x8400 end
        if kind > 0 and fc_now > 0
            and fc_now >= 8290 and fc_now <= 8513 then
            if slot >= DOME_SPRITE and slot < DOME_SPRITE + DOME_COLS then
                f:write(string.format("L %d %d %d %d\n", fc_now, slot, kind,
                                      vpos()))
            elseif slot >= FIRE_SPRITE and slot < FIRE_SPRITE + FIRE_COLS then
                -- Task C2: the fireball's own writes, for the tear proof
                -- (tag KW: Task C5's K lines are the scanline census)
                f:write(string.format("KW %d %d %d %d\n", fc_now, slot, kind,
                                      vpos()))
            elseif slot >= FRAG_SPRITE and slot < FRAG_SPRITE + FRAG_COUNT then
                -- Task C3: the fragments' own writes, for the tear proof
                f:write(string.format("Y %d %d %d %d\n", fc_now, slot, kind,
                                      vpos()))
            elseif slot >= PUFF_SPRITE and slot < PUFF_SPRITE + PUFF_COUNT then
                -- Task C4: the puffs' own writes (with the data: a SCB3 0
                -- write is a hide, which cannot tear), for the tear proof
                f:write(string.format("PWR %d %d %d %d %d\n", fc_now, slot,
                                      kind, data, vpos()))
            elseif (slot >= SMOKE_BACK_SPRITE
                    and slot < SMOKE_BACK_SPRITE + SMOKE_BACK_COUNT)
                or (slot >= SMOKE_SPRITE
                    and slot < SMOKE_SPRITE + SMOKE_COUNT) then
                -- Task C4/V1: the smoke's own writes, as above
                f:write(string.format("SWR %d %d %d %d %d\n", fc_now, slot,
                                      kind, data, vpos()))
            end
        end
        -- the LSPC's auto-increment, within the zone (as the hardware)
        if a >= 0x8000 then
            cur = 0x8000 + ((a - 0x8000 + mod) & 0x7ff)
        else
            cur = (a + mod) & 0x7fff
        end
    end
    return data
end
_G.__collapse_tap = sp:install_write_tap(0x3c0000, 0x3c0005, "lspc", on_write)

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

-- Task C5: the sprites-per-scanline counter, exactly as
-- scripts/ground_probe.lua's scan(): walk slots 0..380 in order, a sticky
-- slot inherits the previous slot's top and height, and a slot with height
-- h covers lines top .. top + 16h - 1 (vertical shrink does NOT shorten a
-- sprite: the height is what counts), whatever its X. Returns the worst
-- count, its line and every slot's raw SCB3 word.
local function scan()
    local rows = {}
    local raw = {}
    local prev_top, prev_h = 0, 0
    for s = 0, 380 do
        local scb3 = vread(SCB3 + s)
        local h = scb3 & 0x3f
        local top
        if (scb3 & 0x40) ~= 0 then         -- sticky: inherit
            top, h = prev_top, prev_h
        else
            top = 496 - (scb3 >> 7)
        end
        prev_top, prev_h = top, h
        if h > 0 then
            local y0 = math.max(0, top)
            local y1 = math.min(223, top + h * 16 - 1)
            for y = y0, y1 do
                rows[y] = (rows[y] or 0) + 1
            end
        end
        raw[s] = scb3
    end
    local best, bestline = 0, -1
    for y = 0, 223 do
        local c = rows[y] or 0
        if c > best then best, bestline = c, y end
    end
    return best, bestline, raw
end

local function slot_line(tag, slot)
    local line = string.format("%s %d %04x %04x %04x %04x",
                               tag, slot, vread(SCB2 + slot), vread(SCB3 + slot),
                               vread(SCB4 + slot), vread(SCB1 + slot * 64 + 1))
    for r = 0, DOME_ROWS - 1 do
        line = line .. string.format(" %04x", vread(SCB1 + slot * 64 + r * 2))
    end
    return line
end

-- the whole dome's SCB3 heights: is every column hidden?
local function dome_gone()
    local c
    for c = 0, DOME_COLS - 1 do
        if (vread(SCB3 + DOME_SPRITE + c) & 0x3f) ~= 0 then
            return 0
        end
    end
    return 1
end

-- dump the dome's 8 columns' SCB3 words, whether every column is hidden,
-- and (Task C1) the box chain's SCB4 words plus every column's SCB1 rows
-- 0..RUIN_ROWS-1, both words (tile and attribute).
local function sample(fc)
    local c, r
    local line = string.format("S %d", fc)
    for c = 0, DOME_COLS - 1 do
        line = line .. string.format(" %04x", vread(SCB3 + DOME_SPRITE + c))
    end
    f:write(line .. "\n")
    f:write(string.format("G %d %d\n", fc, dome_gone()))
    line = string.format("U %d", fc)
    for c = 0, DOME_COLS - 1 do
        line = line .. string.format(" %04x", vread(SCB4 + DOME_SPRITE + c))
        for r = 0, RUIN_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + (DOME_SPRITE + c) * 64 + r * 2),
                vread(SCB1 + (DOME_SPRITE + c) * 64 + r * 2 + 1))
        end
    end
    f:write(line .. "\n")
end

-- the snapshot's slot boxes: every slot's SCB3 (Y/height/sticky) and SCB4
-- (X), so the checker can tell which higher slots cover the ruin's or the
-- fireball's pixels.
local function dump_slots(fc)
    local s
    for s = 0, 380 do
        f:write(string.format("X %d %d %04x %04x\n", fc, s,
                              vread(SCB3 + s), vread(SCB4 + s)))
    end
end

-- Task C2: dump the fireball's 12 slots for a frame: SCB2, SCB3, SCB4 and
-- every SCB1 row 0..31 (tile and attribute). The checker compares rows
-- 0..FIRE_ROWS-1 with fire_tile of the previous frame's g and rows
-- FIRE_ROWS..31 with the blank tile (written once on the collapse's first
-- frame).
local function dump_fire(fc)
    local c, r
    for c = 0, FIRE_COLS - 1 do
        local slot = FIRE_SPRITE + c
        local line = string.format("V %d %d %04x %04x %04x", fc, c,
            vread(SCB2 + slot), vread(SCB3 + slot), vread(SCB4 + slot))
        for r = 0, FIRE_SCB1_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C3: dump the fragments' 49 slots for a frame: SCB2, SCB3, SCB4 and
-- SCB1 rows 0..FRAG_MAX_ROWS-1 (tile and attribute). The checker compares
-- them with frag_* at the previous frame's g (hidden = SCB3 0) and the
-- flip rule (a V flip reverses a 2-tile fragment's rows).
local function dump_frags(fc)
    local n, r
    for n = 0, FRAG_COUNT - 1 do
        local slot = FRAG_SPRITE + n
        local line = string.format("Z %d %d %04x %04x %04x", fc, n,
            vread(SCB2 + slot), vread(SCB3 + slot), vread(SCB4 + slot))
        for r = 0, FRAG_MAX_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C3: once, after the first-frame blanking has been committed: the
-- fragment slots' SCB1 rows FRAG_MAX_ROWS..31, which must be the part's
-- blank tile (the hardware can sample rows up to 31 under a shrunk column,
-- though full-size fragments draw only their own rows).
local function dump_frag_blank(fc)
    local n, r
    for n = 0, FRAG_COUNT - 1 do
        local slot = FRAG_SPRITE + n
        local line = string.format("B %d %d", fc, n)
        for r = FRAG_MAX_ROWS, FRAG_SCB1_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C3: the fragment slots' spans each frame, for the tear proof.
local function dump_frag_spans(fc)
    local n
    for n = 0, FRAG_COUNT - 1 do
        local slot = FRAG_SPRITE + n
        f:write(string.format("N %d %d %04x %04x %04x\n", fc, slot,
            vread(SCB3 + slot), vread(SCB4 + slot),
            vread(SCB2 + slot)))
    end
end


-- Task C4: dump the six puff slots' words (SCB2/3/4 and SCB1 rows
-- 0..PUFF_ROWS-1) every frame of the shake and a little past the burst.
local function dump_puffs(fc)
    local slot, r
    for slot = PUFF_SPRITE, PUFF_SPRITE + PUFF_COUNT - 1 do
        local line = string.format("PU %d %d %04x %04x %04x", fc, slot,
            vread(SCB2 + slot), vread(SCB3 + slot), vread(SCB4 + slot))
        for r = 0, PUFF_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C4: once, the puff slots' SCB1 rows PUFF_ROWS..31, which must be the
-- part's blank tile (the hardware can sample them under a shrunk sprite).
local function dump_puff_blank(fc)
    local slot, r
    for slot = PUFF_SPRITE, PUFF_SPRITE + PUFF_COUNT - 1 do
        local line = string.format("PB %d %d", fc, slot)
        for r = PUFF_ROWS, PUFF_SCB1_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C4/V1: the twelve smoke columns' words (SCB2/3/4 and SCB1 rows
-- 0..6), every frame from the burst to the rebuild and a few frames after.
local function dump_smoke(fc)
    local slot, r
    for slot = 0, SMOKE_TOTAL - 1 do
        local s = slot
        if slot >= SMOKE_BACK_COUNT then
            s = SMOKE_SPRITE + slot - SMOKE_BACK_COUNT
        else
            s = SMOKE_BACK_SPRITE + slot
        end
        local line = string.format("SM %d %d %04x %04x %04x", fc, s,
            vread(SCB2 + s), vread(SCB3 + s), vread(SCB4 + s))
        for r = 0, SMOKE_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + s * 64 + r * 2),
                vread(SCB1 + s * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C4/V1: once, the twelve smoke columns' SCB1 rows SMOKE_ROWS..31
-- (the blank tile).
local function dump_smoke_blank(fc)
    local slot, r
    for i = 0, SMOKE_TOTAL - 1 do
        if i >= SMOKE_BACK_COUNT then
            slot = SMOKE_SPRITE + i - SMOKE_BACK_COUNT
        else
            slot = SMOKE_BACK_SPRITE + i
        end
        local line = string.format("SB %d %d", fc, slot)
        for r = SMOKE_ROWS, SMOKE_SCB1_ROWS - 1 do
            line = line .. string.format(" %04x %04x",
                vread(SCB1 + slot * 64 + r * 2),
                vread(SCB1 + slot * 64 + r * 2 + 1))
        end
        f:write(line .. "\n")
    end
end

-- Task C4: the puff and smoke slots' spans each frame, for the tear proof.
local function dump_puff_spans(fc)
    local slot
    for slot = PUFF_SPRITE, PUFF_SPRITE + PUFF_COUNT - 1 do
        f:write(string.format("PS %d %d %04x %04x %04x\n", fc, slot,
            vread(SCB3 + slot), vread(SCB4 + slot), vread(SCB2 + slot)))
    end
end

local function dump_smoke_spans(fc)
    local slot
    for i = 0, SMOKE_TOTAL - 1 do
        if i >= SMOKE_BACK_COUNT then
            slot = SMOKE_SPRITE + i - SMOKE_BACK_COUNT
        else
            slot = SMOKE_BACK_SPRITE + i
        end
        f:write(string.format("SS %d %d %04x %04x %04x\n", fc, slot,
            vread(SCB3 + slot), vread(SCB4 + slot), vread(SCB2 + slot)))
    end
end

-- the dome's 15 used palette entries (bank PAL_DOME, entries 1..15; entry 0
-- is the transparent black). Palette RAM is one u16 per entry. Written as a
-- P/Q record (hex words, all on one line) after a slot dump so the checker
-- can prove the collapse's fade restored the full palette.
local function dump_pal(tag)
    local i
    local line = tag
    for i = 1, 15 do
        line = line .. string.format(" %04x", sp:read_u16(PAL_BASE + (1 * 16 + i) * 2))
    end
    f:write(line .. "\n")
end

-- decode the fix layer's 10 HUD rows (like hud_probe.lua) so the checker
-- can prove GAME OVER (row 7, centred) appears by the model's frame.
local function dump_fix(fc)
    local r, c
    f:write(string.format("F %d\n", fc))
    for r = 0, 9 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            -- every tile >= 0x80 is a <NN> escape so the row stream stays
            -- ASCII: the HUD icons and Task G1's thick-font GAME OVER tiles
            -- (>= TITLE2_ROW_BASE 512; the checker recovers the character
            -- from build/title_font.h's index block).
            if tile >= 0x80 then
                line = line .. string.format("<%d>", tile)
            else
                line = line .. string.char(tile)
            end
        end
        f:write(string.format("FR %d %s\n", r, line))
    end
end

local fresh_lines = nil

local function dump_fresh(fc)
    local c
    fresh_lines = {}
    f:write(string.format("H %d\n", fc))
    for c = 0, DOME_COLS - 1 do
        local line = slot_line("h", DOME_SPRITE + c)
        fresh_lines[#fresh_lines + 1] = line
        f:write(line .. "\n")
    end
    dump_pal("P")
end

-- the centred policy: the stick centred always (the ship rests on the
-- start cell, 27), A (fire) tapped every 11 frames. Fire keeps kills below
-- 6; under the Vectrex 1.1.0 rule the 6th missile hit that breaks a cell
-- opens every ring, so the dome breaks three times (cart frames 8359,
-- 16715, 27105) and the game ends. The taps after the last launch stop
-- once the game is effectively over (fc 27105 + 118): the recorded inputs
-- stay the ground truth the checker replays.
local function drive(fc)
    if not SG.game_started(fc) then     -- the title: no input of our own
        return
    end
    hold("P1 Left", false)
    hold("P1 Up", false)
    hold("P1 Right", false)
    hold("P1 Down", false)
    hold("P1 A", fc <= 27105 and (fc % 11) == 0)
end

-- after the rebuild the dome must be a fresh dome: the same sticky chain
-- and full-size SCB2, and the SCB1 tile list of the view the ship is at
-- (the rules' replay tells the checker that view; the cart's own
-- dome_tile table, read from build/dome_map.h, is the reference — a fresh
-- dome at that view draws exactly those tiles). This dumps the rebuilt
-- slots; the checker does the comparison.
local rebuilt = nil

local function check_rebuilt(fc)
    local c
    f:write(string.format("REBUILD %d\n", fc))
    for c = 0, DOME_COLS - 1 do
        f:write(slot_line("R", DOME_SPRITE + c) .. "\n")
    end
    dump_pal("Q")
    rebuilt = true
end

-- the fix rows are sampled around the model's GAME OVER (~fc 27142, the
-- centred policy's derivation in tests/check_collapse.py): every 10 frames
-- from 26985 (after the last death starts, while the text is still
-- absent) through 27245, so the checker brackets the derived frame and
-- proves GAME OVER shows on row 7 within that window.
local fix_next = 26985
local snap_done = false

-- Task C2: the ruin switch (dome slot 0's SCB1 attribute turns PAL_RUIN) is
-- the burst marker; the fireball is displayed one frame later (its words are
-- committed in the next vblank), so displayed g at the end of frame fc is
-- fc - ruin_fc - 1. The fire snapshots are at g 2, 12, 30 and (Task C3) 40,
-- i.e. ruin_fc + 3, + 13, + 31 and + 41. Task C3 also snapshots the ruin
-- switch frame itself (g -1, before the fragments and the fireball), so the
-- C1 ruin pixel proof keeps the snapshot with the most uncovered ruin
-- pixels now that the fragments cover the box.
--
-- Task C4 adds a smoke snapshot at displayed g 50 (ruin_fc + 51): at g 40
-- the C2 fireball and C3's fragments cover most of the smoke (460 pixels
-- left), while at g 50 the fireball is gone and the plumes are large enough
-- for the >1000-pixel smoke proof. (Plan-deviation: the plan named the g 40
-- snapshot; see the commit message.)
local ruin_fc = nil
local fire_snaps = {}
local ruin_snaps = {}
local snap_taken = {}
-- Task C4: the collapse's first frame is the first frame whose dome SCB3
-- words differ from the previous frame's (the whole dome's chain never
-- changes; the shake splits it). The puff snapshot at displayed f 35 is
-- then 36 frames later.
local collapse_fc = nil
local puff_snap_fc = nil
local prev_dome_scb3 = nil

-- Task C5: every dome death's collapse is scanned every frame. fixed_key is
-- the whole dome's SCB3 chain, captured on cart frame 60; the split is the
-- first frame whose key differs from it after the chain was fixed (the
-- whole dome's chain never changes while it is whole). The census covers
-- DEAD_FRAMES frames from that first frame: the rebuild for the first two
-- deaths, and (the collapse's smoke keeps looping) into the dome death's
-- GAME OVER for the third.
local fixed_key = nil
local census_start = nil
local census_index = 0
local census_worst, census_line = 0, -1
local census_fc, census_g, census_death, census_raw = 0, 0, 0, nil

local function dome_scb3_key()
    local c
    local line = ""
    for c = 0, DOME_COLS - 1 do
        line = line .. string.format("%04x", vread(SCB3 + DOME_SPRITE + c))
    end
    return line
end

local function tick()
    n = n + 1
    if in_cart == 0 and cpu.state["PC"].value >= 0x100000 then
        in_cart = 1
    end
    SG.sg_apply(n)
    if in_cart then
        rec = rec + 1
        local fc = framecnt()
        f:write(string.format("I %d %d %d %d\n", rec, fc, sp:read_u8(BI), sp:read_u8(CHG)))
        MS.poll(f, n, fc)
        drive(fc)
        -- the ruin's switch is written in game_frame (Task C1), so it is in
        -- MAME's VRAM by the end of the frame it happens on.
        if fc >= 8290 and fc <= 8513 and ruin_fc == nil then
            if vread(SCB1 + (DOME_SPRITE + 0) * 64 + 1) == (PAL_RUIN << 8) then
                ruin_fc = fc
                f:write(string.format("RUIN %d\n", fc))
                ruin_snaps[fc] = 1
                fire_snaps[fc + 1 + 2] = 2
                fire_snaps[fc + 1 + 12] = 12
                fire_snaps[fc + 1 + 30] = 30
                fire_snaps[fc + 1 + 40] = 40
                fire_snaps[fc + 1 + 50] = 50       -- Task C4's smoke proof
            end
        end
        -- Task C4/C5: capture the whole dome's SCB3 chain once, then find
        -- every collapse's first frame (the shake's split). The first split
        -- also gives the puff snapshot at displayed f 35 (36 frames later).
        local key = dome_scb3_key()
        if fixed_key == nil and fc == 60 then
            fixed_key = key
        end
        if fixed_key ~= nil and census_start == nil and census_index < 3
           and prev_dome_scb3 == fixed_key and key ~= fixed_key then
            census_start = fc
            census_index = census_index + 1
            if census_index == 1 then
                collapse_fc = fc
                puff_snap_fc = fc + 36
            end
        end
        prev_dome_scb3 = key
        -- Task C5: count the sprites on every scanline on every frame of
        -- the collapse. g is the collapse's own g (the checker's displayed
        -- g): the ruin switch is COLLAPSE_SHAKE frames after the split, so
        -- g = fc - split - COLLAPSE_SHAKE - 1.
        if census_start ~= nil and fc >= census_start
           and fc < census_start + DEAD_FRAMES then
            local best, line, raw = scan()
            local g = fc - (census_start + COLLAPSE_SHAKE) - 1
            f:write(string.format("K %d %d %d %d\n", fc, g, best, line))
            if best > census_worst then
                census_worst, census_line = best, line
                census_fc, census_g = fc, g
                census_death, census_raw = census_index, raw
            end
            if fc == census_start + DEAD_FRAMES - 1 then
                census_start = nil
            end
        end
        if collapse_fc and fc >= collapse_fc + 1
           and fc <= collapse_fc + 1 + 70 then
            dump_puffs(fc)
        end
        -- the fire words, every frame from the ruin switch through g 60
        if ruin_fc and fc >= ruin_fc and fc <= ruin_fc + 60 then
            dump_fire(fc)
        end
        -- Task C4: the smoke words from the burst to the rebuild and a few
        -- frames after (the hide), plus the one-time blank rows.
        if ruin_fc and fc >= ruin_fc and fc <= ruin_fc + 80 then
            dump_smoke(fc)
        end
        if ruin_fc and fc == ruin_fc then
            dump_puff_blank(fc)
            dump_smoke_blank(fc)
        end
        -- Task C3: the fragments' words, every frame from the ruin switch
        -- through g FRAG_T + 1 (displayed g = fc - ruin_fc - 1); and once
        -- the blank rows below the pieces.
        if ruin_fc and fc >= ruin_fc and fc <= ruin_fc + FRAG_T + 2 then
            dump_frags(fc)
        end
        if ruin_fc and fc == ruin_fc then
            dump_frag_blank(fc)
        end
        -- the fire and fragment slots' spans, for the tear proofs (every
        -- frame whose old span can matter: the collapse's first frame is
        -- the ruin switch minus COLLAPSE_SHAKE)
        if fc >= 8290 and fc <= 8513 then
            for c = 0, FIRE_COLS - 1 do
                local slot = FIRE_SPRITE + c
                f:write(string.format("T %d %d %04x %04x %04x\n", fc, slot,
                    vread(SCB3 + slot), vread(SCB4 + slot),
                    vread(SCB2 + slot)))
            end
            dump_frag_spans(fc)
            dump_puff_spans(fc)
            dump_smoke_spans(fc)
        end
        -- Task C4: the puff snapshot at displayed f 35 (before the ruin
        -- switch, while the shake's puffs are on screen).
        if puff_snap_fc and fc == puff_snap_fc and not snap_taken[fc] then
            snap_taken[fc] = true
            machine.video:snapshot()
            f:write(string.format("SNAP %d\n", fc))
            dump_slots(fc)
        end
        -- the ruin switch snapshot (Task C3) and the four fire snapshots
        if ruin_fc and (fire_snaps[fc] or ruin_snaps[fc]) and not snap_taken[fc] then
            snap_taken[fc] = true
            machine.video:snapshot()
            f:write(string.format("SNAP %d\n", fc))
            dump_slots(fc)
        end
        if fc == 60 and not fresh_lines then
            dump_fresh(fc)
        end
        if fc >= 8290 and fc <= 8513 and (fc - 8290) % 6 == 0 then
            sample(fc)
            if not snap_done and fc >= 8410 and not snap_taken[fc] then
                snap_taken[fc] = true
                machine.video:snapshot()
                f:write(string.format("SNAP %d\n", fc))
                dump_slots(fc)
                snap_done = true
            end
        end
        if fc == 8513 and not rebuilt then
            check_rebuilt(fc)
        end
        if fix_next and fc >= fix_next then
            dump_fix(fc)
            if fc >= 27245 then
                fix_next = nil
            else
                fix_next = fix_next + 10
            end
        end
        fc_now = fc + 1                 -- the next frame's cart counter
    end
    if n >= run_len then
        if census_raw then
            f:write(string.format("W %d %d %d\n", census_fc, census_worst, census_line))
            for s = 0, 380 do
                f:write(string.format("w %d %04x\n", s, census_raw[s]))
            end
        end
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d sampled=%d rebuilt=%d\n",
                              in_cart, n, rec, (rebuilt ~= nil) and 1 or 0,
                              (rebuilt == true) and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__collapse = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
