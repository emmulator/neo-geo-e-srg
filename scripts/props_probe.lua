-- props_probe.lua: the dome-scenery Task 12/13/14/15 props boot-test.
--
-- Boots the normal cart, presses Start, walks the ship up to the peak cell
-- (0), spins the dome left through the whole turn (dome_angle 0..239) and
-- back right to 0, then plays the centred game (stick centred, A every 11
-- cart frames) for the rest of the run. The trees and rocks, the dome, the
-- ship, the console and the missiles are all on screen. At four frames it
-- snapshots and dumps, from MAME's own VRAM copy:
--
--   TITLE  a title frame (fc 0): both pools' slots are the fresh game's
--          start-cell layout (attract Task A2: the props are drawn under the
--          title).
--   PLAY   an early whole-dome play frame (fc 30, before the first missile
--          launches at fc 59): both pools' slots' SCB1 rows (tile + attr),
--          SCB2, SCB3 and SCB4, every prop's palette bank, and the frame's
--          ship.dome_angle. tests/check_props.py compares every shown slot
--          with tests/props_model.py at that angle, and each shown prop's
--          bank with prop_pal[i][0] and prop_shadow[0][y].
--   DARK   a spin frame at DARK_DA (90), where prop 21 (the near tree)
--          is shown and prop_dark[21][90] is 1: the same dumps plus the
--          slots ABOVE the back pool, so the checker can prove prop 21's
--          uncovered pixels use prop_pal[21][1] (and prop_shadow[1][y] for
--          entries 1 and 13).
--   FRONT  a spin frame at FRONT_DA (189), where prop 14 is in the front
--          pool and covers the dome's base, with the ship at the peak: the
--          same dumps, plus the slots ABOVE the front pool (the ship, the
--          console, the front missiles, the explosions, the radar) so the
--          checker can prove prop 14's pixels over the dome and the ship's
--          own pixels.
--
-- Task 13/15: on every play frame whose dome_angle differs from the previous
-- sampled frame, it also dumps BOTH pools' every slot's SCB1 rows
-- 0..PROP_MAX_ROWS-1 (5), SCB2, SCB3 and SCB4. Task 14: it also samples on
-- every change of the ground's bank (PAL_GROUND 8: ground_pal while the dome
-- is whole, ground_pal_noshadow otherwise) and every 10 frames while the
-- dome is not whole, so the collapse's frames are covered. Each sample has
-- every shown prop's whole 16-word bank and the ground bank:
--   A <fc> <da>                       an angle sample
--   g <fc> <16 hex words>             the ground bank (PAL_GROUND 8)
--   p <fc> <pool> <k> <scb2> <scb3> <scb4> <tile,attr x 5>
--                                     pool slot k at that angle (0 = back,
--                                     1 = front)
--   q <fc> <i> <16 hex words>         shown prop i's whole palette bank
--   a <fc> <da>                       EVERY play frame's ship.dome_angle
--   h <fc> <state>                    every play frame's ground bank state
--                                     (1 = ground_pal, 0 = noshadow), so
--                                     check_props.py can use frame fc-1's
--                                     angle and whole state (Task 18's lag)
--
-- At each snapshot it writes:
--   SNAP <TAG> <n> <fc>
--   D <TAG> <fc> <da>                 ship.dome_angle (src/ship.h)
--   PAL <TAG> <16 hex words>          the ground bank (PAL_GROUND 8)
--   B <TAG> <i> <16 hex words>        prop i's palette bank (22 + i)
--   P <TAG> <pool> <k> <scb2> <scb3> <scb4> <tile,attr x 5>
--                                     pool slot k's SCB2/SCB3/SCB4 and its
--                                     SCB1 rows 0..4
--   X <TAG> <slot> <scb3> <scb4>      every slot (0..380), so the checker
--                                     can exclude covered pixels
--   U <TAG> <slot> <x> <y> <h> <tiles...>
--                                     every slot ABOVE the snapshot's pool
--                                     (for PLAY/DARK: above the back pool;
--                                     for FRONT: the ship and everything
--                                     after it, the front pool included;
--                                     10-26 the ship is under it) that
--                                     draws, with its box resolved (sticky
--                                     chains included) and its SCB1 tiles, so
--                                     the checker can tell a prop pixel a
--                                     higher sprite really covers from one it
--                                     does not
--   F <TAG> <row> <40 chars>          fix rows 0..29
--
-- Every CENSUS_EVERY cart frames it counts the sprites on each scanline from
-- every slot's SCB3 (resolving the sticky chains) and writes
--     CEN <fc> <worst count> <worst line>; at the end the worst frame's raw
-- SCB3 dump (W/w): the sprites-per-scanline proof, recounted by the checker.
--
-- Env: OUT, FRAMES (28100), PROPS_FRAMECNT_ADDR / HUD_FRAMECNT_ADDR,
-- PROPS_SHIP_ADDR (the static `ship` in build/rom.elf), CENSUS_EVERY (10).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "28100")
local framecnt_addr = tonumber(os.getenv("PROPS_FRAMECNT_ADDR")
                              or os.getenv("HUD_FRAMECNT_ADDR") or "0")
local ship_addr = tonumber(os.getenv("PROPS_SHIP_ADDR") or "0")
local every = tonumber(os.getenv("CENSUS_EVERY") or "10")

local FR = 0x7000
local SCB1, SCB2, SCB3, SCB4 = 0x0000, 0x8000, 0x8200, 0x8400
local PROP_PAL_BANK = 22                   -- src/props.h
local PROP_MAX_ROWS = 5                    -- src/props.h
local DARK_DA = 90                         -- prop 21 is dark and shown here
local FRONT_DA = 189                       -- a spin frame where prop 14 is front
local PAL_GROUND = 8                       -- src/ground.h
local PAL_BASE = 0x400000
local NOT_WHOLE_EVERY = 10                 -- sample every 10 frames while gone

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
-- the two props pools: 0 = back (under the dome), 1 = front (over the dome)
local POOLS = {
    { base = S.PROP_SPRITE, count = S.PROP_BACK_COUNT },
    { base = S.PROP_FRONT_SPRITE, count = S.PROP_FRONT_COUNT },
}
local BACK_END = POOLS[1].base + POOLS[1].count - 1
local FRONT_END = POOLS[2].base + POOLS[2].count - 1

-- the props' generated header, for NPROPS
local function header_define(name)
    local path = (os.getenv("REPO") or ".") .. "/build/props_map.h"
    local fh = assert(io.open(path, "r"))
    local txt = fh:read("*a")
    fh:close()
    return tonumber(txt:match("#define " .. name .. " (%d+)"))
end
local NPROPS = header_define("NPROPS")

-- the ground's two banks (build/ground_map.h), so the probe can tell whether
-- this frame has the dome whole (ground_pal) or not (ground_pal_noshadow).
local function ground_header_words(name)
    local path = (os.getenv("REPO") or ".") .. "/build/ground_map.h"
    local fh = assert(io.open(path, "r"))
    local txt = fh:read("*a")
    fh:close()
    local body = txt:match("static const u16 " .. name .. "%[16%] = {([^}]*)}")
    assert(body, name)
    local out = {}
    for w in body:gmatch("0x%x+") do
        -- Lua 5.4 rejects "0x8000" when a base is given; the prefix-less
        -- conversion accepts the hex numeral and is what MAME's Lua has.
        out[#out + 1] = tonumber(w)
    end
    assert(#out == 16, name)
    return out
end
local GROUND_PAL = ground_header_words("ground_pal")
local GROUND_NOSHADOW = ground_header_words("ground_pal_noshadow")

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
local title_snap, play_snap, dark_snap, front_snap = false, false, false, false
local worst_count, worst_line, worst_fc, worst_raw = 0, -1, 0, nil
local last_sampled_da = -1
local last_ground_state = nil
local not_whole_next = 0
local reached239, done_right = false, false

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

local function dump_banks(tag)
    local i
    for i = 0, NPROPS - 1 do
        f:write(string.format("B %s %d%s\n", tag, i, pal16(PROP_PAL_BANK + i)))
    end
end

local function dump_props(tag)
    local pool, k, r
    for pool = 0, 1 do
        local P = POOLS[pool + 1]
        for k = 0, P.count - 1 do
            local slot = P.base + k
            local line = string.format("P %s %d %d %04x %04x %04x", tag,
                                       pool, k, vread(SCB2 + slot),
                                       vread(SCB3 + slot), vread(SCB4 + slot))
            for r = 0, 4 do
                local a = SCB1 + slot * 64 + r * 2
                line = line .. string.format(" %04x %04x", vread(a), vread(a + 1))
            end
            f:write(line .. "\n")
        end
    end
end

local function ground_words()
    local i, out = 0, {}
    for i = 0, 15 do
        out[i + 1] = sp:read_u16(PAL_BASE + (PAL_GROUND * 16 + i) * 2)
    end
    return out
end

local function words_equal(a, b)
    local i
    for i = 1, 16 do
        if a[i] ~= b[i] then
            return false
        end
    end
    return true
end

-- 1 = ground_pal (the dome is whole), 0 = ground_pal_noshadow (not whole),
-- -1 = neither (never seen: the cart writes one of the two every frame).
local function ground_state()
    local w = ground_words()
    if words_equal(w, GROUND_PAL) then
        return 1
    end
    if words_equal(w, GROUND_NOSHADOW) then
        return 0
    end
    return -1
end

local function words_hex(w)
    local i, line = "", ""
    for i = 1, 16 do
        line = line .. string.format(" %04x", w[i])
    end
    return line
end

-- Task 13/14/15: one sampled frame's every slot of both pools, every shown
-- prop's whole 16-word bank and the ground bank. A prop counts as shown
-- when a slot with height > 0 carries its palette bank in the SCB1
-- attribute.
local function dump_angle(fc, d)
    local shown = {}
    local pool, k, r, i

    f:write(string.format("A %d %d\n", fc, d))
    f:write(string.format("g %d%s\n", fc, words_hex(ground_words())))
    for pool = 0, 1 do
        local P = POOLS[pool + 1]
        for k = 0, P.count - 1 do
            local slot = P.base + k
            local scb2 = vread(SCB2 + slot)
            local scb3 = vread(SCB3 + slot)
            local scb4 = vread(SCB4 + slot)
            local line = string.format("p %d %d %d %04x %04x %04x", fc,
                                       pool, k, scb2, scb3, scb4)
            for r = 0, PROP_MAX_ROWS - 1 do
                local a = SCB1 + slot * 64 + r * 2
                local tile, attr = vread(a), vread(a + 1)
                line = line .. string.format(" %04x %04x", tile, attr)
                if r == 0 and (scb3 & 0x3f) ~= 0 then
                    local bank = attr >> 8
                    if bank >= PROP_PAL_BANK and bank < PROP_PAL_BANK + NPROPS then
                        shown[bank - PROP_PAL_BANK] = true
                    end
                end
            end
            f:write(line .. "\n")
        end
    end
    for i = 0, NPROPS - 1 do
        if shown[i] then
            f:write(string.format("q %d %d%s\n", fc, i,
                                  pal16(PROP_PAL_BANK + i)))
        end
    end
end

local function dump_slots(tag, above)
    local s
    for s = 0, 380 do
        f:write(string.format("X %s %d %04x %04x\n", tag, s,
                              vread(SCB3 + s), vread(SCB4 + s)))
    end
    -- the slots ABOVE the snapshot's pool also get their SCB1 tile rows and
    -- their box resolved (sticky chains: inherit the previous slot's Y/height
    -- and sit 16 px right), so the checker can tell a prop pixel those
    -- sprites really cover from one they do not. For PLAY the threshold is
    -- the back pool's end (the missiles behind the dome, the dome, the
    -- overlays, the front pool, the ship, the console, the front missiles,
    -- the explosions and the radar); for PLAY/DARK it is the back pool's
    -- end; for FRONT it is just below the ship, so the ship, the front pool
    -- (over the ship since 10-26) and everything after them (the dome and
    -- overlays are BELOW the front pool and must not be treated as
    -- occluders; the checker drops the ship when it masks the front pool).
    local prev_x, prev_y, prev_h = 0, 0, 0
    for s = 0, 380 do
        local scb3 = vread(SCB3 + s)
        local h = scb3 & 0x3f
        local x, y
        if (scb3 & 0x40) ~= 0 then
            x, y, h = prev_x + 16, prev_y, prev_h
        else
            x, y = vread(SCB4 + s) >> 7, 496 - (scb3 >> 7)
        end
        prev_x, prev_y, prev_h = x, y, h
        if s > above and h > 0 then
            local line = string.format("U %s %d %d %d %d", tag, s, x, y, h)
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
    for r = 0, 29 do
        local line = ""
        for c = 0, 39 do
            local tile = vread(FR + c * 32 + r) & 0x0fff
            if tile > 0xff then line = line .. "?" else line = line .. string.char(tile) end
        end
        f:write(string.format("F %s %d %s\n", tag, r, line))
    end
end

local function snapshot(tag, fc, above)
    machine.video:snapshot()
    f:write(string.format("SNAP %s %d %d\n", tag, n, fc))
    f:write(string.format("D %s %d %d\n", tag, fc, da()))
    f:write(string.format("PAL %s%s\n", tag, words_hex(ground_words())))
    dump_banks(tag)
    dump_props(tag)
    dump_slots(tag, above)
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

-- the drive: walk the ship up to the peak cell (0) like
-- mountains_probe.lua, spin the dome left through the whole turn (0..239),
-- then back right to 0, then play the centred game (A every 11 frames) for
-- the rest of the run. The flags are updated from the frame that just ran,
-- before the next frame's input is chosen, so the left spin stops on 239
-- without wrapping to 0 and the right spin stops on 0 without wrapping to
-- 239.
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
            right = 1                 -- the first step back right
        else
            left = 1
        end
    elseif not done_right then
        if da() == 0 then
            done_right = true         -- the turn is over: centred game
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
        f:write(string.format("I %d %d %d %d\n", rec, fc,
                              sp:read_u8(0x10fd96), sp:read_u8(0x10fd97)))
        drive(fc)

        -- the title frame: snapshotted once, before any game
        if not title_snap and n >= 200 and fc == 0 then
            snapshot("TITLE", fc, BACK_END)
            title_snap = true
        end

        if SG.game_started(fc) then
            -- Task 13/14/15: every play frame whose dome_angle differs from
            -- the previous sampled frame, every frame whose ground bank
            -- changes (whole -> not whole at the collapse's first split, and
            -- back at the respawn), and every 10 frames while not whole.
            -- The spin changes the angle one step at a time; the climb's
            -- moves change it too, and those frames are valid samples.
            local d = da()
            local gs = ground_state()
            -- Task 18's one-frame lag: props_commit runs at the NEXT frame's
            -- vblank, so the words this frame's end reads are the previous
            -- frame's prepared layout. Record every play frame's angle and
            -- ground bank so check_props.py can use frame fc-1's.
            f:write(string.format("a %d %d\n", fc, d))
            f:write(string.format("h %d %d\n", fc, gs))
            local sample = (d ~= last_sampled_da)
            if last_ground_state ~= nil and gs >= 0
                and gs ~= last_ground_state then
                sample = true              -- the whole/not-whole switch
            end
            if gs == 0 and fc >= not_whole_next then
                sample = true              -- the collapse's frames
                not_whole_next = fc + NOT_WHOLE_EVERY
            end
            if sample then
                dump_angle(fc, d)
                last_sampled_da = d
            end
            if gs >= 0 then
                last_ground_state = gs
            end

            -- Task 14: the snapshot at a spin angle where prop 21 is dark
            -- and shown. Taken after the frame ran, so the PNG is this
            -- frame's picture.
            if not dark_snap and d == DARK_DA then
                snapshot("DARK", fc, BACK_END)
                dark_snap = true
            end

            -- Task 15: the snapshot at a spin angle where prop 14 is in the
            -- front pool (the ship is at the peak then). Taken after the
            -- frame ran, so the PNG is this frame's picture.
            if not front_snap and d == FRONT_DA then
                snapshot("FRONT", fc, S.SHIP_SPRITE - 1)
                front_snap = true
            end

            -- the early whole-dome play frame: no missile exists yet
            if not play_snap and fc >= 30 then
                snapshot("PLAY", fc, BACK_END)
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
        f:write(string.format("pc_in_cart=%d frames=%d rec=%d title=%d play=%d dark=%d front=%d\n",
                              in_cart, n, rec, title_snap and 1 or 0,
                              play_snap and 1 or 0, dark_snap and 1 or 0,
                              front_snap and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__props = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
