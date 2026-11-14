-- console_probe.lua: the dome-scenery Task 7 console boot-test.
--
-- Boots the normal cart and plays the same deterministic centred game as the
-- ground/mountains legs (stick centred, A every 11 cart frames), so a whole
-- panel, the dome, the ship and the missiles are all on screen. At two frames
-- it snapshots and dumps, from MAME's own VRAM copy:
--
--   TITLE  a title frame (fc 0): every console column is drawn at its
--          header's placement and the panel is visible (attract Task A2:
--          the scene is drawn under the title);
--   PLAY   an early whole-dome play frame (fc 30, before the first missile
--          launches at fc 59): all 20 columns' SCB1 tile + palette words,
--          SCB2 (0x0fff), SCB3 (Y, height, sticky bit clear) and SCB4 (X)
--          must equal build/console_map.h's numbers, and the panel's
--          opaque pixels that no other sprite or fix tile covers must show
--          con_pal's colour.
--
-- At each snapshot it writes:
--   SNAP <TAG> <n> <fc>
--   PAL <TAG> <16 hex words>          the console bank (PAL_CON 10)
--   C <TAG> <c> <scb2> <scb3> <scb4> <rows words...>
--                                     column c's SCB2/SCB3/SCB4 and its
--                                     con_rows[c] SCB1 (tile, attr) pairs
--   X <TAG> <slot> <scb3> <scb4>      every slot (0..380), so the checker
--                                     can exclude covered pixels
--   F <TAG> <row> <40 chars>          fix rows 15..28 (the panel's bands,
--                                     the HUD's rows 26 and 28 included)
--
-- Every CENSUS_EVERY cart frames it counts the sprites on each scanline from
-- every slot's SCB3 (resolving the sticky chains) and writes
--     CEN <fc> <worst count> <worst line>; at the end the worst frame's raw
-- SCB3 dump (W/w): the sprites-per-scanline proof, recounted by the checker.
--
-- tests/check_console.py compares the header with every dumped column word,
-- proves the console part's base tile in build/console_map.h + the assembled
-- C ROM is the picture, and compares the PLAY snapshot's clean panel pixels
-- with the generator's own picture.
--
-- Env: OUT, FRAMES (1600), CON_FRAMECNT_ADDR / HUD_FRAMECNT_ADDR,
-- CENSUS_EVERY (10), SG_BEGIN/SG_END (600..604).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "1600")
local framecnt_addr = tonumber(os.getenv("CON_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local every = tonumber(os.getenv("CENSUS_EVERY") or "10")

local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local PAL_CON = 10                         -- src/console.h
local PAL_BASE = 0x400000

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local CON0, CON_COUNT = S.CON_SPRITE, S.CON_COUNT

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
local title_snap, play_snap = false, false
local worst_count, worst_line, worst_fc, worst_raw = 0, -1, 0, nil

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

-- the console header, evaluated by the checker; the probe needs only CON_COLS
-- (from the slot map: CON_COUNT) and con_rows (the dump length). It reads
-- con_rows from build/console_map.h through a tiny lua parse: the header's
-- arrays are plain comma lists, one per line.
local function header_array(name)
    local path = (os.getenv("REPO") or ".") .. "/build/console_map.h"
    local fh = assert(io.open(path, "r"))
    local txt = fh:read("*a")
    fh:close()
    local body = txt:match("static const u8 " .. name .. "%[CON_COLS%] = {(.-)};")
    local t = {}
    if body then
        for v in body:gmatch("%d+") do t[#t + 1] = tonumber(v) end
    end
    return t
end
local CON_ROWS = header_array("con_rows")

local function pal16()
    local i, line = "", ""
    for i = 0, 15 do
        line = line .. string.format(" %04x",
            sp:read_u16(PAL_BASE + (PAL_CON * 16 + i) * 2))
    end
    return line
end

local function dump_slots(tag)
    local s
    for s = 0, 380 do
        f:write(string.format("X %s %d %04x %04x\n", tag, s,
                              vread(SCB3 + s), vread(SCB4 + s)))
    end
    -- the slots ABOVE the console (the front missiles, the explosions and
    -- the radar) also get their SCB1 tile rows, so the checker can tell a
    -- panel pixel those sprites really cover from one they do not (a box is
    -- not a picture): only their non-transparent pixels draw.
    for s = CON0 + CON_COUNT, 380 do
        local scb3 = vread(SCB3 + s)
        local h = scb3 & 0x3f
        if h > 0 then
            local line = string.format("U %s %d %04x %04x", tag, s, scb3,
                                       vread(SCB4 + s))
            for r = 0, h - 1 do
                line = line .. string.format(" %04x",
                    vread(SCB1 + s * 64 + r * 2))
            end
            f:write(line .. "\n")
        end
    end
end

local function dump_fix(tag)
    local r
    for r = 15, 28 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            if tile > 0xff then line = line .. "?" else line = line .. string.char(tile) end
        end
        f:write(string.format("F %s %d %s\n", tag, r, line))
    end
end

local function dump_columns(tag)
    for c = 0, CON_COUNT - 1 do
        local rows = CON_ROWS and CON_ROWS[c + 1] or 0
        local line = string.format("C %s %d %04x %04x %04x", tag, c,
                                   vread(SCB2 + CON0 + c), vread(SCB3 + CON0 + c),
                                   vread(SCB4 + CON0 + c))
        for r = 0, rows - 1 do
            local a = SCB1 + (CON0 + c) * 64 + r * 2
            line = line .. string.format(" %04x %04x", vread(a), vread(a + 1))
        end
        f:write(line .. "\n")
    end
end

local function snapshot(tag, fc)
    machine.video:snapshot()
    f:write(string.format("SNAP %s %d %d\n", tag, n, fc))
    f:write("PAL " .. tag .. pal16() .. "\n")
    dump_columns(tag)
    dump_slots(tag)
    dump_fix(tag)
end

-- the sprites-per-scanline census: the sticky chains resolved as hardware does
local function scan()
    local rows = {}
    local raw = {}
    local prev_top, prev_h = 0, 0
    for s = 0, 380 do
        local scb3 = vread(SCB3 + s)
        local h = scb3 & 0x3f
        local top
        if (scb3 & 0x40) ~= 0 then
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

-- the centred policy, as the collapse/ground legs' drive()
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
        f:write(string.format("I %d %d %d %d\n", rec, fc,
                              sp:read_u8(0x10fd96), sp:read_u8(0x10fd97)))
        drive(fc)

        -- the title frame: snapshotted once, before any game
        if not title_snap and n >= 200 and fc == 0 then
            snapshot("TITLE", fc)
            title_snap = true
        end

        if SG.game_started(fc) then
            -- the early whole-dome play frame: no missile exists yet
            if not play_snap and fc >= 30 then
                snapshot("PLAY", fc)
                play_snap = true
            end
            if fc % every == 0 then
                local c, line, raw = scan()
                f:write(string.format("CEN %d %d %d\n", fc, c, line))
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
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d title=%d play=%d\n",
                              in_cart, n, rec, title_snap and 1 or 0,
                              play_snap and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__console = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
