-- band_probe.lua: the dome-scenery Task 17 towns-and-forests band boot-test.
--
-- Boots the normal cart, presses Start (the standard start_game.lua window,
-- MAME frames 600..604), walks the ship up to the peak cell (0), then spins
-- the dome left (dome_angle grows) through the panorama and back right
-- (dome_angle falls). At frames whose ship.dome_angle is one of
--   0        the game's opening frame (the whole panorama's start)
--   1        a non-zero scroll phase (s 3, phase 3)
--   60       a mid-panorama frame
--   140      the window wraps at 48 with phase 0 (s 448, s >> 4 = 28)
--   141      a wrap WITH a scroll phase (s 451, phase 3)
--   141      a wrap WITH a scroll phase (s 451, phase 3)
--   232      the wrap + phase where a back prop's pixels reach into the band
--            (s 742, phase 6): the pixel proof (and the draw-order mutation)
--   239      the last angle (s 765)
--   230      reached by turning the other way (right spin after 239)
-- it snapshots (TITLE at fc 0, WINDOW at da 232) and dumps, from MAME's own
-- VRAM copy:
--
--   S <fc> <da> <drv scb3> <drv scb4>            the driver's SCB3/SCB4
--   c <fc> <k> <tile0> <attr0> <tile1> <attr1>   chain column k's 2 SCB1 rows
--   z <fc> <k> <scb2>                            chain column k's SCB2 zoom
--                                                (full size 0x0fff on every
--                                                column: the followers do not
--                                                inherit horizontal zoom)
--   X <tag> <slot> <scb3> <scb4>                 every slot (0..380), so the
--                                                checker can exclude covered
--                                                pixels
--   F <tag> <row> <40 chars>                     fix rows 10..14 (the band
--                                                y 68..99 is rows 10..14)
--   PALB <tag> <16 words>                        the band bank (PAL_BAND 12)
--   PALM <tag> <16 words>                        the mountain bank (PAL_MTN 9)
--   SNAP <tag> <n> <fc>
--
-- Every CENSUS_EVERY cart frames after a game began it counts the sprites on
-- each scanline from every slot's SCB3 (resolving the sticky chains) and
-- writes
--   CEN <fc> <worst count> <worst line> <band worst> <band line>
-- where the band lines are 68..99. At the end the worst frame's raw SCB3
-- dump is written as W/w, and the worst frame's dump on lines 68..99 as B/b;
-- the checker recounts both.
--
-- The title's band is drawn at the fresh game's scroll 0; its snapshot is
-- checked by the same picture method. tests/check_band.py computes
-- s = band_model.band_scroll(da) from
-- tests/band_model.py, the model of the C (not a copy), and compares the
-- driver Y/X and all 21 columns' tile words at every S frame; it also
-- compares the WINDOW snapshot's band y 68..99, x 0..319 with the band's
-- shifted picture where no higher sprite/fix tile covers, and with the
-- mountains' shifted picture in the band's transparent pixels.
--
-- Env: OUT, FRAMES (1600), BAND_FRAMECNT_ADDR / HUD_FRAMECNT_ADDR,
-- BAND_SHIP_ADDR (the static `ship` in build/rom.elf, found by nm),
-- CENSUS_EVERY (10), SG_BEGIN/SG_END (600..604).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "1600")
local framecnt_addr = tonumber(os.getenv("BAND_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local ship_addr = tonumber(os.getenv("BAND_SHIP_ADDR") or "0")
local every = tonumber(os.getenv("CENSUS_EVERY") or "10")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local PAL_BAND, PAL_MTN = 12, 9            -- src/band.h, src/mountains.h
local PAL_BASE = 0x400000
local BAND_Y, BAND_H = 68, 32              -- build/band_map.h
-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local BAND0, BAND_COUNT = S.BAND_SPRITE, S.BAND_COUNT

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
local worst_count, worst_line, worst_fc, worst_raw = 0, -1, 0, nil
local bworst_count, bworst_line, bworst_fc, bworst_raw = 0, -1, 0, nil
-- the targets, in the order they occur along the spin (0 at the start;
-- then left from 0 up to 239; then right back down to 230)
local TARGET = { [0] = true, [1] = true, [60] = true, [140] = true,
                 [141] = true, [232] = true, [239] = true, [230] = true }
local seen = {}
local reached239, done_right = false, false
-- Task 18b: the band's per-frame driver write now runs in the frame's vblank,
-- using ship.dome_angle from the frame that just ended. The words read at the
-- end of frame N therefore show the PREVIOUS play frame's angle, so the S
-- record's da (and the sampling trigger) is that displayed angle.
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

local function pal16(bank)
    local i, line = "", ""
    for i = 0, 15 do
        line = line .. string.format(" %04x",
            sp:read_u16(PAL_BASE + (bank * 16 + i) * 2))
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
    for r = 10, 14 do
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
    f:write("PALB " .. tag .. pal16(PAL_BAND) .. "\n")
    f:write("PALM " .. tag .. pal16(PAL_MTN) .. "\n")
    dump_slots(tag)
    dump_fix(tag)
end

-- one sampled frame: the driver's SCB3/SCB4, every chain column's 2 SCB1
-- rows (tile + attribute words) and every column's SCB2 (full-size zoom:
-- a sticky follower does not inherit horizontal zoom, so it must be
-- written per column)
local function dump_frame(fc, d)
    f:write(string.format("S %d %d %04x %04x\n", fc, d,
                          vread(SCB3 + BAND0), vread(SCB4 + BAND0)))
    for k = 0, BAND_COUNT - 1 do
        local a = SCB1 + (BAND0 + k) * 64
        f:write(string.format("c %d %d %04x %04x %04x %04x\n", fc, k,
                              vread(a + 0), vread(a + 1), vread(a + 2),
                              vread(a + 3)))
        f:write(string.format("z %d %d %04x\n", fc, k,
                              vread(SCB2 + BAND0 + k)))
    end
end

-- the sprites-per-scanline census: the sticky chains resolved as hardware
-- does; returns the worst line overall, the worst line in the band's rows
-- (68..99) and the raw SCB3 dump for the checker's recount
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
    local bw, bwl = 0, -1
    for y = 0, 223 do
        local c = rows[y] or 0
        if c > best then best, bestline = c, y end
        if y >= BAND_Y and y <= BAND_Y + BAND_H - 1 and c > bw then
            bw, bwl = c, y
        end
    end
    return best, bestline, bw, bwl, raw
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
                -- the pixel proof frame: a wrap with a scroll phase where
                -- a back prop's pixels reach into the band (da 232)
                if d == 232 and not window_snap then
                    snapshot("WINDOW", fc)
                    window_snap = true
                end
            end
            prev_da = da()
            if fc % every == 0 then
                local c, line, bw, bwl, raw = scan()
                f:write(string.format("CEN %d %d %d %d %d\n", fc, c, line,
                                      bw, bwl))
                if c > worst_count then
                    worst_count, worst_line, worst_fc, worst_raw = c, line, fc, raw
                end
                if bw > bworst_count then
                    bworst_count, bworst_line, bworst_fc, bworst_raw = bw, bwl, fc, raw
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
        if bworst_raw then
            f:write(string.format("B %d %d %d\n", bworst_fc, bworst_count, bworst_line))
            for s = 0, 380 do
                f:write(string.format("b %d %04x\n", s, bworst_raw[s]))
            end
        end
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
    _G.__band = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
