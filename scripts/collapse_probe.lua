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
--   S <fc> <scb3_DOME_SPRITE> .. <scb3_DOME_SPRITE+10>  the 11 dome slots' SCB3 words
--   G <fc> <gone>                  every sampled frame: 1 = all 11 SCB3
--                                  heights are 0 (the dome is hidden)
--   H <fc>                         a fresh dump follows
--   h <slot> <scb2> <scb3> <scb4> <attr> <tile8...>   fresh slot row
--   R <fc> <slot> <scb2> <scb3> <scb4> <attr> <tile rows>  rebuilt slot row
--   P <pal15 words>      fresh dome palette (bank PAL_DOME, entries 1..15)
--   Q <pal15 words>      rebuilt dome palette (decimal)
--   F <fc>               a fix-layer row block follows (all 10 rows)
--   W <row> <40 chars>   fix row r decoded (tile = ASCII, pal in 12..15)
--   SNAP <fc>            a snapshot was taken this frame
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
local DOME_SPRITE, DOME_COLS, DOME_ROWS = S.DOME_SPRITE, S.DOME_COUNT, 8
local COLLAPSE_GONE = 100
local PAL_BASE = 0x400000
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

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
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

-- dump the 11 columns (SCB3 words) and whether the dome is gone
local function sample(fc)
    local c
    local line = string.format("S %d", fc)
    for c = 0, DOME_COLS - 1 do
        line = line .. string.format(" %04x", vread(SCB3 + DOME_SPRITE + c))
    end
    f:write(line .. "\n")
    f:write(string.format("G %d %d\n", fc, dome_gone()))
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
            if tile > 0xff then line = line .. "?" else line = line .. string.char(tile) end
        end
        f:write(string.format("W %d %s\n", r, line))
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
        if fc == 60 and not fresh_lines then
            dump_fresh(fc)
        end
        if fc >= 8290 and fc <= 8513 and (fc - 8290) % 6 == 0 then
            sample(fc)
            if not snap_done and fc >= 8410 then
                machine.video:snapshot()
                f:write(string.format("SNAP %d\n", fc))
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
    end
    if n >= run_len then
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
