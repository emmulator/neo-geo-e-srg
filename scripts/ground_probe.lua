-- ground_probe.lua: the dome-scenery Task 5 grass boot-test.
--
-- Boots the normal cart and plays the same deterministic centred game as the
-- collapse leg (the stick centred so the ship rests on the start cell, A
-- every 11 cart frames; fire keeps kills below 6, so under the Vectrex
-- 1.1.0 rule the dome breaks three times and the game ends). It takes three
-- snapshots, in this order:
--
--   TITLE  a title frame (fc 0): the grass is drawn under the title at the
--          fresh game's state, so (10,150) is the generated grass colour;
--   WHOLE  an early play frame (fc 30, before the first missile launches at
--          fc 59): the dome is whole, the ground's clean band y 104..119 /
--          x 0..79 matches the art, and the shadow pixels right of the dome
--          show the twin (shadowed) colour;
--   GONE   the FIRST play frame whose dome slot 0 SCB1 attribute is
--          PAL_RUIN << 8 (the collapse's ruin, after a whole dome was seen):
--          the same shadow pixels must show the plain shade, because the
--          bank has switched to ground_pal_noshadow (dome_is_whole is 0
--          from the collapse's first split on). Task C1: the dome no longer
--          vanishes; the ruin stands in its own 8 columns.
--
-- Every CENSUS_EVERY cart frames it counts the sprites on each scanline
-- from every slot's SCB3 (resolving the sticky chains: a sticky slot
-- inherits the previous slot's Y and height) and writes
--     C <fc> <worst count> <worst line>
-- for the whole game. When a new worst is found it keeps that frame's raw
-- SCB3 dump and writes it at the end:
--     W <fc> <count> <line>
--     w <slot> <scb3> ...              all 381 slots, 0..380
-- At the snapshots it also writes
--     SNAP <TAG> <n> <fc>
--     PAL <TAG> <16 hex words>         the ground bank (PAL_GROUND 8)
--     X <TAG> <slot> <scb3> <scb4>     every slot, so the checker can prove
--                                      a chosen pixel is not covered by a
--                                      sprite, and the worst-line count
--     F <TAG> <row> <40 chars>         fix rows 15/16 (the clean band)
--
-- Env: OUT, FRAMES (28100: the centred game reaches GAME OVER at fc
-- ~27142 under the default Start's seed), GROUND_FRAMECNT_ADDR /
-- HUD_FRAMECNT_ADDR, CENSUS_EVERY (10), SG_BEGIN/SG_END (600..604).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "28100")
local framecnt_addr = tonumber(os.getenv("GROUND_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local every = tonumber(os.getenv("CENSUS_EVERY") or "10")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local PAL_GROUND = 8                      -- src/ground.h
local PAL_RUIN = 55                       -- src/dome.h (Task C1)
local PAL_BASE = 0x400000

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")

-- VRAM is read through MAME's own copy of it, never through the LSPC
-- registers at 0x3c0000/2: writing the address register from a frame
-- callback changes the cart's VRAM pointer under it.
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end

local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local title_snap, whole_snap, gone_snap = false, false, false
local seen_whole = false
local worst_count, worst_line, worst_fc, worst_raw = 0, -1, 0, nil

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

-- the effective box of every slot: (tag, scb3, scb4) with the sticky chain
-- resolved (a sticky slot inherits the previous slot's Y and height). `raw`
-- is true for a plain SCB3 scan; the X chain is resolved separately by the
-- checker from the raw scb4 words.
local function scan()
    local rows = {}
    local raw = {}
    local prev_top, prev_h = 0, 0
    local line = ""
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
            local bot = top + h * 16 - 1
            local y0 = math.max(0, top)
            local y1 = math.min(223, bot)
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

local function pal16()
    local i, line = "", ""
    for i = 0, 15 do
        line = line .. string.format(" %04x", sp:read_u16(PAL_BASE + (PAL_GROUND * 16 + i) * 2))
    end
    return line
end

local function dump_slots(tag)
    for s = 0, 380 do
        f:write(string.format("X %s %d %04x %04x\n", tag, s,
                              vread(SCB3 + s), vread(SCB4 + s)))
    end
end

local function dump_fix(tag)
    local r, c
    for r = 15, 27 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            if tile > 0xff then line = line .. "?" else line = line .. string.char(tile) end
        end
        f:write(string.format("F %s %d %s\n", tag, r, line))
    end
end

local function snapshot(tag, fc)
    machine.video:snapshot()
    f:write(string.format("SNAP %s %d %d\n", tag, n, fc))
    f:write("PAL " .. tag .. pal16() .. "\n")
    dump_slots(tag)
    if tag ~= "TITLE" then
        dump_fix(tag)
    end
end

local function dome_all_hidden()
    local c
    for c = 0, S.DOME_COUNT - 1 do
        if (vread(SCB3 + S.DOME_SPRITE + c) & 0x3f) ~= 0 then
            return false
        end
    end
    return true
end

-- Task C1: the ruin is the dome's own 8 columns' SCB1 lists in PAL_RUIN;
-- the first column's attribute word is the switch's marker.
local function dome_ruin()
    return vread(SCB1 + S.DOME_SPRITE * 64 + 1) == (PAL_RUIN << 8)
end

-- the centred policy, exactly as the collapse leg's drive()
local function drive(fc)
    if not SG.game_started(fc) then
        return
    end
    joy.fields["P1 Left"]:set_value(0)
    joy.fields["P1 Up"]:set_value(0)
    joy.fields["P1 Right"]:set_value(0)
    joy.fields["P1 Down"]:set_value(0)
    joy.fields["P1 A"]:set_value(fc <= 27105 and (fc % 11) == 0 and 1 or 0)
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
        drive(fc)

        -- the title frame: snapshotted once, before any game
        if not title_snap and n >= 200 and fc == 0 then
            snapshot("TITLE", fc)
            title_snap = true
        end

        if SG.game_started(fc) then
            -- the early whole-dome play frame: no missile exists yet
            if title_snap and not whole_snap and fc >= 30 then
                snapshot("WHOLE", fc)
                whole_snap = true
            end
            -- latch a whole dome, then the first ruin frame after it
            if whole_snap then
                if not seen_whole and not dome_all_hidden() then
                    seen_whole = true
                end
                if seen_whole and not gone_snap and dome_ruin() then
                    snapshot("GONE", fc)
                    gone_snap = true
                end
            end
            if fc % every == 0 then
                local c, line, raw = scan()
                f:write(string.format("C %d %d %d\n", fc, c, line))
                if c > worst_count then
                    worst_count, worst_line, worst_fc, worst_raw = c, line, fc, raw
                end
            end
        end
    end
    if n >= run_len then
        if worst_raw then
            f:write(string.format("W %d %d %d\n", worst_fc, worst_count, worst_line))
            for s = 0, 380 do
                f:write(string.format("w %d %04x\n", s, worst_raw[s]))
            end
        end
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d title=%d whole=%d gone=%d\n",
                              in_cart, n, rec, title_snap and 1 or 0,
                              whole_snap and 1 or 0, gone_snap and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__ground = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
