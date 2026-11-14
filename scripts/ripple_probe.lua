-- ripple_probe.lua: the dome-scenery Task 19 grass-ripple boot-test.
--
-- Boots the normal cart and plays the props leg's spin: walk the ship up to
-- the peak cell (0), turn the dome left through a whole turn (0..239), then
-- back right to 0, then the centred game (A every 11 cart frames) until the
-- dome death and its collapse's gone frames are seen. The drive is copied
-- from scripts/tear_probe.lua's spin (the props leg's), extended with the
-- centred fire that scripts/props_probe.lua uses after the turn; it does not
-- call into either probe.
--
-- The ripple is palette rotation only: src/ground.c prepares each of the 11
-- ripple banks' 12 words (entries 1..12) in game_frame and commits them in
-- the next vblank. So the words shown on cart frame fc are the ones prepared
-- from the previous frame's dome_angle (prev_da), and bank 8 (PAL_GROUND)
-- still carries the whole/gone marker. The probe records, every play frame:
--
--   R <fc> <da> <prev_da> <16 words bank 8> <16 words bank 44> ...
--     ... <16 words bank 54>          (12 x 16 words: 8, 44..54)
--   PW <fc> <count> <maxvpos>         every palette write to bank 8 or
--                                     44..54 that frame: how many, and the
--                                     latest raster line it landed on
--   G <slot> <row> <tile> <attr>      the 160 ground SCB1 words, once
--   SNAP <TAG> <n> <fc> <da> <prev_da>
--   X <TAG> <slot> <scb2> <scb3> <scb4>   every slot, at each snapshot
--   F <TAG> <row> <40 chars>          fix rows 15..29 (the ground's rows)
--   I <rec> <fc> <bi> <chg>           the input/frame log
--
-- Three snapshots are taken during the left turn at dome angles 20, 120 and
-- 220 (their displayed ground is at prev_da). tests/check_ripple.py compares
-- every R frame with build/ground_map.h's ground_ripple_pal at prev_da (gone
-- read from bank 8), every PW's vpos against GROUND_Y + 16, the G words
-- against the ripple banks and the unchanged tile numbers, and each
-- snapshot's uncovered ground pixels with the C ROM tile through the bank.
--
-- Env: OUT, FRAMES (10000: the game starts at MAME ~603; the props leg's
-- spin ends in the first ~600 cart frames, its first dome death is at cart
-- fc 9079 and the collapse's gone frames at ~9179), RIPPLE_FRAMECNT_ADDR /
-- PROPS_FRAMECNT_ADDR (hud_framecnt), RIPPLE_SHIP_ADDR / PROPS_SHIP_ADDR
-- (the static ship; dome_angle at +0, cell at +2), SG_BEGIN/SG_END (600/604).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "10000")
local framecnt_addr = tonumber(os.getenv("RIPPLE_FRAMECNT_ADDR")
                              or os.getenv("PROPS_FRAMECNT_ADDR") or "0")
local ship_addr = tonumber(os.getenv("RIPPLE_SHIP_ADDR")
                          or os.getenv("PROPS_SHIP_ADDR") or "0")

local BI, CHG = 0x10fd96, 0x10fd97
local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local PAL_BASE = 0x400000
local PAL_GROUND = 8                     -- src/ground.h (the whole/gone marker)
local RIPPLE_BANK = 44                   -- src/ground.h RIPPLE_PAL_BANK
local RIPPLE_BANKS = 11                  -- build/ground_map.h
local GROUND_ROWS = 8                    -- build/ground_map.h

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")

-- VRAM through MAME's own copy, never the LSPC registers (writing the
-- address register from a frame callback changes the cart's VRAM pointer).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(a)
    return vram:read(a)
end

local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local f = assert(io.open(out, "w"))
local n, in_cart, rec = 0, 0, 0
local reached239, done_right = false, false
local prev_da = -1
local fc_now = 0
local ground_dumped = false
local snaps = { [20] = false, [120] = false, [220] = false }
local snap_n = 0

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

-- src/flow.c lspc_vpos: ((LSPCMODE >> 7) & 0x1ff) - 0x100
local function vpos()
    local v = ((sp:read_u16(0x3c0006) >> 7) & 0x1ff) - 0x100
    return v
end

-- the palette write tap: count every write to the ripple banks (44..54)
-- and to bank 8 separately (bank 8 is switched directly in game_frame, not
-- by the commit), with the latest raster line.
local pw_ripple, pw_b8, pw_max = 0, 0, -1
local function on_pal_write(offset, data, mask)
    -- palette RAM's bank: 16 words * 2 bytes a bank, from 0x400000
    local bank = (offset - 0x400000) >> 5
    if bank == PAL_GROUND
        or (bank >= RIPPLE_BANK and bank < RIPPLE_BANK + RIPPLE_BANKS) then
        if bank == PAL_GROUND then
            pw_b8 = pw_b8 + 1
        else
            pw_ripple = pw_ripple + 1
        end
        local v = vpos()
        if v > pw_max then
            pw_max = v
        end
    end
    return data
end
_G.__ripple_paltap = sp:install_write_tap(0x400000, 0x401fff, "pal",
                                          on_pal_write)

local function pal_words(bank)
    local i, t = 0, {}
    for i = 0, 15 do
        t[i + 1] = string.format("%04x",
                                 sp:read_u16(PAL_BASE + (bank * 16 + i) * 2))
    end
    return table.concat(t, " ")
end

-- every play frame's shown palette: the 11 ripple banks, with this frame's
-- angle and the previous frame's, plus bank 8's words FROM THE PREVIOUS
-- FRAME. Bank 8 is switched directly in game_frame (not staged), so the
-- ripple banks (committed at this frame's vblank) carry the previous
-- frame's gone state: its bank-8 words are the ones the model needs, the
-- same prev_da lag.
local last_b8 = nil
local function dump_ripple(fc, d)
    local k, line = 0, string.format("R %d %d %d %s", fc, d, prev_da,
                                     last_b8 or pal_words(PAL_GROUND))
    for k = RIPPLE_BANK, RIPPLE_BANK + RIPPLE_BANKS - 1 do
        line = line .. " " .. pal_words(k)
    end
    f:write(line .. "\n")
end

-- once: the 160 ground SCB1 words (tile + attribute per row), so the checker
-- proves the bank attributes and that the tile numbers are unchanged.
local function dump_ground()
    local c, r
    for c = 0, S.GROUND_COUNT - 1 do
        local slot = S.GROUND_SPRITE + c
        for r = 0, GROUND_ROWS - 1 do
            local a = slot * 64 + r * 2
            f:write(string.format("G %d %d %04x %04x\n", slot, r,
                                  vread(a), vread(a + 1)))
        end
    end
end

local function dump_fix(tag)
    local r, c
    for r = 15, 29 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            if tile > 0xff then line = line .. "?" else line = line .. string.char(tile) end
        end
        f:write(string.format("F %s %d %s\n", tag, r, line))
    end
end

local function dump_slots(tag)
    local s
    for s = 0, 380 do
        f:write(string.format("X %s %d %04x %04x %04x\n", tag, s,
                              vread(SCB2 + s), vread(SCB3 + s), vread(SCB4 + s)))
    end
end

local function snapshot(tag, fc, d)
    machine.video:snapshot()
    f:write(string.format("SNAP %s %d %d %d %d\n", tag, snap_n, fc, d, prev_da))
    snap_n = snap_n + 1
    dump_slots(tag)
    dump_fix(tag)
end

-- the props leg's drive (scripts/props_probe.lua): climb to the peak, spin
-- left to 239, right back to 0, then the centred game (A every 11 frames)
-- until the dome death and the collapse's gone frames.
local function drive(fc)
    if not SG.game_started(fc) then
        return
    end
    local up, left, right, fire = 0, 0, 0, 0
    if cell() ~= 0 then
        up = 1
    elseif not reached239 then
        if da() == 239 then
            reached239 = true
            right = 1
        else
            left = 1
        end
    elseif not done_right then
        if da() == 0 then
            done_right = true
        else
            right = 1
        end
    else
        fire = (fc <= 27105 and (fc % 11) == 0) and 1 or 0
    end
    joy.fields["P1 Up"]:set_value(up)
    joy.fields["P1 Left"]:set_value(left)
    joy.fields["P1 Right"]:set_value(right)
    joy.fields["P1 Down"]:set_value(0)
    joy.fields["P1 A"]:set_value(fire)
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
        local d = da()
        f:write(string.format("I %d %d %d %d\n", rec, fc, sp:read_u8(BI),
                              sp:read_u8(CHG)))
        -- the writes during the frame that just ran were committed for
        -- fc_now (the previous frame's cart counter); flush them before
        -- fc_now moves on.
        if pw_ripple > 0 or pw_b8 > 0 then
            f:write(string.format("PW %d %d %d %d\n", fc_now, pw_ripple,
                                  pw_b8, pw_max))
            pw_ripple, pw_b8, pw_max = 0, 0, -1
        end
        drive(fc)

        if SG.game_started(fc) then
            if not ground_dumped then
                dump_ground()
                ground_dumped = true
            end
            -- prev_da is the previous tick's dome_angle: the words in the
            -- palette now were prepared from it, before this frame's commit.
            dump_ripple(fc, d)
            -- three snapshots at different angles during the left turn (the
            -- displayed frame is the one that just ran, at prev_da)
            if cell() == 0 and not reached239 and snaps[d] == false then
                snaps[d] = true
                snapshot("A" .. tostring(d), fc, d)
            end
        end
        -- the next frame's commit will be keyed by this frame's counter.
        last_b8 = pal_words(PAL_GROUND)
        prev_da = d
        fc_now = fc
    end
    if n >= run_len then
        if pw_ripple > 0 or pw_b8 > 0 then
            f:write(string.format("PW %d %d %d %d\n", fc_now, pw_ripple,
                                  pw_b8, pw_max))
        end
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d snaps=%d\n",
                              in_cart, n, rec, snap_n))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__ripple = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
