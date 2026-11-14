-- mountains_probe.lua: the dome-scenery Task 16 mountains boot-test.
--
-- Boots the normal cart, presses Start (the standard start_game.lua window,
-- MAME frames 600..604), walks the ship up to the peak cell (0), then spins
-- the dome left (dome_angle grows) through the panorama and back right
-- (dome_angle falls). At frames whose ship.dome_angle is one of
--   0        the game's opening frame (the whole panorama's start)
--   1        a phase where s & 15 != 0 (s 4, phase 4)
--   160      the window wraps: s 640, s >> 4 = 40, (s >> 4) + 20 >= 60
--   161      the wrap WITH a scroll phase (s 644, phase 4): the pixel proof
--   239      the last angle (s 956)
--   230      reached by turning the other way (right spin after 239)
-- it snapshots (TITLE at fc 0, WINDOW at da 161) and dumps, from MAME's own
-- VRAM copy: the title's mountains are drawn at the fresh game's scroll 0
-- VRAM copy:
--
--   S <fc> <da> <drv scb3> <drv scb4>            the driver's SCB3/SCB4
--   c <fc> <k> <tile0> <attr0> <tile1> <attr1> <tile2> <attr2>
--                                                chain column k's 3 SCB1 rows
--   z <fc> <k> <scb2>                            chain column k's SCB2 zoom
--                                                (full size 0x0fff on every
--                                                column: the followers do not
--                                                inherit horizontal zoom)
--   X <tag> <slot> <scb3> <scb4>                 every slot (0..380), so the
--                                                checker can exclude covered
--                                                pixels
--   F <tag> <row> <40 chars>                     fix rows 6..14 (the band
--                                                y 32..119, covering 52..99)
--   PAL <tag> <16 words>                         the mountain bank (9)
--   SNAP <tag> <n> <fc>
--
-- tests/check_mountains.py computes s = mtn_scroll(da) from
-- tests/mountains_model.py, the model of the C (not a copy), and compares
-- the driver Y/X and all 21 columns' tile words at every S frame; it also
-- compares the WINDOW snapshot's band y 52..99, x 0..319 with the generator's
-- picture shifted by s, on every pixel no other sprite or fix tile covers.
--
-- Env: OUT, FRAMES (1600), MTN_FRAMECNT_ADDR / HUD_FRAMECNT_ADDR,
-- MTN_SHIP_ADDR (the static `ship` in build/rom.elf, found by nm).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "1600")
local framecnt_addr = tonumber(os.getenv("MTN_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local ship_addr = tonumber(os.getenv("MTN_SHIP_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local PAL_MTN = 9                          -- src/mountains.h
local PAL_BASE = 0x400000
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local MTN0, MTN_COUNT = S.MTN_SPRITE, S.MTN_COUNT

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
local title_snap, window_snap = false, false
-- the targets, in the order they occur along the spin (0 at the start;
-- then left from 0 up to 239; then right back down to 230)
local TARGET = { [0] = true, [1] = true, [160] = true, [161] = true,
                 [239] = true, [230] = true }
local seen = {}
local reached239, done_right = false, false
-- Task 18b: the mountains' per-frame driver write now runs in the frame's
-- vblank, using ship.dome_angle from the frame that just ended. The words
-- read at the end of frame N therefore show the PREVIOUS play frame's angle,
-- so the S record's da (and the sampling trigger) is that displayed angle.
local prev_da = nil

local function framecnt()
    if framecnt_addr ~= 0 then
        return sp:read_u32(framecnt_addr)
    end
    return rec
end

local function da()
    return ship_addr ~= 0 and sp:read_u8(ship_addr + 0) or 0
end

local function cell()
    return ship_addr ~= 0 and sp:read_u8(ship_addr + 2) or 27
end

local function pal16()
    local i, line = "", ""
    for i = 0, 15 do
        line = line .. string.format(" %04x",
            sp:read_u16(PAL_BASE + (PAL_MTN * 16 + i) * 2))
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
    local r
    for r = 6, 14 do
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
    dump_fix(tag)
end

-- one sampled frame: the driver's SCB3/SCB4, every chain column's 3 SCB1
-- rows (tile + attribute words) and every column's SCB2 (full-size zoom:
-- a sticky follower does not inherit horizontal zoom, so it must be
-- written per column)
local function dump_frame(fc, d)
    f:write(string.format("S %d %d %04x %04x\n", fc, d,
                          vread(SCB3 + MTN0), vread(SCB4 + MTN0)))
    for k = 0, MTN_COUNT - 1 do
        local a = SCB1 + (MTN0 + k) * 64
        f:write(string.format("c %d %d %04x %04x %04x %04x %04x %04x\n", fc, k,
                              vread(a + 0), vread(a + 1), vread(a + 2),
                              vread(a + 3), vread(a + 4), vread(a + 5)))
        f:write(string.format("z %d %d %04x\n", fc, k,
                              vread(SCB2 + MTN0 + k)))
    end
end

-- the drive: centre until the start, Up until the ship reaches the peak
-- cell, then spin left to 239 and right back to 230. Only the stick is used.
local function drive(fc)
    if not SG.game_started(fc) then
        return
    end
    local up, left, right = 0, 0, 0
    if cell() ~= 0 then
        up = 1
    elseif not reached239 then
        left = 1
    elseif not done_right then
        right = 1
    end
    if da() == 239 then
        reached239 = true
    end
    if reached239 and da() == 230 then
        done_right = true
    end
    joy.fields["P1 Up"]:set_value(up)
    joy.fields["P1 Left"]:set_value(left)
    joy.fields["P1 Right"]:set_value(right)
    joy.fields["P1 Down"]:set_value(0)
    joy.fields["P1 A"]:set_value(0)
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
            -- the displayed angle: the previous play frame's, except on the
            -- first game frame (game_begin's show, where prev_da is nil)
            local d = prev_da or da()
            if TARGET[d] and not seen[d] then
                seen[d] = true
                dump_frame(fc, d)
                -- the pixel proof frame: a wrap WITH a scroll phase
                if d == 161 and not window_snap then
                    snapshot("WINDOW", fc)
                    window_snap = true
                end
            end
            prev_da = da()
        end
    end
    if n >= run_len then
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d title=%d window=%d seen=%d\n",
                              in_cart, n, rec, title_snap and 1 or 0,
                              window_snap and 1 or 0, (function()
                                  local c = 0
                                  for _ in pairs(seen) do c = c + 1 end
                                  return c
                              end)()))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__mountains = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
