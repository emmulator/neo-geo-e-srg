-- leftover_probe.lua: for the M3 "no leftovers below a shrunk sprite" fix.
--
-- Plays to frame FRAMES. Once, before the first missile appears (frame
-- LEFT_PLANT_AT), it plants a visible, non-blank tile into SCB1 rows 0..31 of
-- every missile/bullet/explosion slot, so that any row
-- the game does not overwrite is loud garbage instead of a lucky blank.
-- From frame 600 it fires A every LEFT_FIRE_EVERY frames, so bullets (always
-- drawn shrunk to half size) and missiles at several sizes are on screen.
-- From frame 615 to 635 it holds Right, so the dome turns while the first
-- bullets fly: the bolt picture must follow the line's new screen angle.
--
-- On many frames it reads SCB2/SCB3/SCB4, the 32 SCB1 rows and their
-- attributes of every shown slot, and writes:
--     F <frame> <lspc_counter>
--     S <slot> <scb2> <scb3> <scb4> <tile0>..<tile31> <attr0>..<attr31>
-- Every frame it also writes the two bullets' words (B) and the three
-- missiles' state/ring/phi/r (M). The first frame that shows a bolt is
-- snapshotted and marked with "SNAP <frame> <seq>"; after that, pairs of
-- snapshots of one front missile are marked with "RPAIR" (the R2 flame
-- flicker proof). tests/check_leftovers.py checks the rows, the missile
-- words, the bullet words and both snapshots.
--
-- Env: FRAMES (1500), LEFT_PLANT_AT (520), LEFT_FIRE_EVERY (5),
--      LEFT_SAMPLE_EVERY (8), OUT (the probe dump).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local frames = tonumber(os.getenv("FRAMES") or "1500")
local plant_at = tonumber(os.getenv("LEFT_PLANT_AT") or "520")
local fire_every = tonumber(os.getenv("LEFT_FIRE_EVERY") or "5")
local sample_every = tonumber(os.getenv("LEFT_SAMPLE_EVERY") or "8")
local out = os.getenv("OUT")
local ship_addr = tonumber(os.getenv("SHIP_ADDR") or "0")
local mis_addr = tonumber(os.getenv("MIS_ADDR") or "0")
local framecnt_addr = tonumber(os.getenv("HUD_FRAMECNT_ADDR") or "0")

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")

-- Task H2: the bolt tiles (build/ship_map.h). A bullet is a slot whose SCB1
-- row 0 tile is in SHIP_BOLT_TILE .. + BOLT_ANGLES*BOLT_FRAMES-1, so this is
-- how the probe finds the bullet to snapshot.
local BOLT0, NBOLT = 0, 0
do
    local h = io.open((os.getenv("REPO") or ".") .. "/build/ship_map.h")
    if h then
        local text = h:read("*a")
        h:close()
        local function define(name)
            local n = text:match("#define%s+" .. name .. "%s+(%d+)")
            return n and tonumber(n) or nil
        end
        BOLT0 = define("SHIP_BOLT_TILE") or 0
        local angles = define("BOLT_ANGLES") or 0
        local frames = define("BOLT_FRAMES") or 0
        NBOLT = angles * frames
    end
end

-- Task S3: mis_obj_t's byte size and the bullet slots (NMIS 3, NBUL 2,
-- MIS_COLS_MAX 3: src/missiles.h, src/mis_gfx.h)
local OBJ = 14
local NMIS = 3
local BUL0 = 3
local NBUL = 2
local COLS_MAX = 3
local KIND_MISSILE = 0

-- CROM tiles 0..255 are the zero padding before the first game tile (4672),
-- so a tile number < 256 is fully transparent: that is what "blank" means.
-- The planted garbage must be a real, visible tile with a real palette.
local GARBAGE_TILE = 4672
local GARBAGE_ATTR = 3 * 0x100    -- palette 3 (missile), no flips

-- VRAM is read (and, by the leftover probe, written) through MAME's own copy
-- of it, never through the LSPC registers at 0x3c0000/2: writing the address
-- register from a frame callback changes the cart's VRAM pointer under it, and
-- the cart's next writes land at the probe's address (it zeroed title rows).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(addr)
    return vram:read(addr)
end

local function vwrite(addr, val)
    vram:write(addr, val)
end

-- the missile/bullet/explosion slots (everything that ever shrinks): behind
-- the dome, in front of it, the explosions, and the radar's heading slots
-- (M5 Task 4: the headings are 1-tile sprites shrunk by SCB2 every frame,
-- so the rows of their SCB1 column below the picture must be re-blanked
-- each show; the radar's frame and stick slots never shrink, so they are
-- not planted).
local slots = {}
for s = S.MIS_BEHIND_SPRITE, S.MIS_BEHIND_SPRITE + S.MIS_BEHIND_COUNT - 1 do
    slots[#slots + 1] = s
end
for s = S.MIS_FRONT_SPRITE, S.MIS_FRONT_SPRITE + S.MIS_FRONT_COUNT - 1 do
    slots[#slots + 1] = s
end
for s = S.EXPL_SPRITE, S.EXPL_SPRITE + S.EXPL_COUNT - 1 do
    slots[#slots + 1] = s
end
-- the radar's used heading slots: RADAR_SPRITE + 4 (frame) + i*5 + 1
for i = 0, 2 do
    slots[#slots + 1] = S.RADAR_SPRITE + 4 + i * 5 + 1
end

local function plant()
    for _, s in ipairs(slots) do
        local base = s * 64
        for r = 0, 31 do
            vwrite(base + r * 2, GARBAGE_TILE)
            vwrite(base + r * 2 + 1, GARBAGE_ATTR)
        end
    end
end

local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local n, in_cart, planted, snapped = 0, 0, false, false
local snap_seq = 0
local rocket_pairs, rocket_pending = 0, nil
local f = assert(io.open(out, "w"))
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1). The leftover probe's planting and fire keys are absolute MAME
-- frames, unchanged — the game begins just after the Start here, so a
-- bullet is still on screen by the first post-title sample.
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local function slot_words(s)
    return vread(0x8000 + s), vread(0x8200 + s), vread(0x8400 + s), vread(s * 64)
end

-- a shown slot's screen rectangle (x0, y0, x1, y1), from SCB2/3/4
local function slot_rect(s)
    local scb2, scb3, scb4 = vread(0x8000 + s), vread(0x8200 + s), vread(0x8400 + s)
    local height = scb3 & 0x3f
    if height == 0 then
        return nil
    end
    local hz = (scb2 >> 8) & 0x0f
    local x = scb4 >> 7
    local y = 496 - (scb3 >> 7)
    return { x, y, x + hz, y + height * 16 - 1 }
end

local function union(a, b)
    if not a then return b end
    if not b then return a end
    return { math.min(a[1], b[1]), math.min(a[2], b[2]),
             math.max(a[3], b[3]), math.max(a[4], b[4]) }
end

local function intersects(a, b)
    return a[1] <= b[3] and b[1] <= a[3] and a[2] <= b[4] and b[2] <= a[4]
end

local function on_screen(r)
    if not (r and r[1] and r[2] and r[3] and r[4]) then
        return false
    end
    return r[4] >= 0 and r[2] < 224 and r[3] >= 0 and r[1] < 320
end

-- the highest front missile whose picture has no higher slot over it (the
-- radar and an explosion draw over the front missiles; other missiles only
-- cover a lower object). Its snapshot pixels are then the rocket alone.
local function front_missile()
    local best = nil
    for i = 0, NMIS - 1 do
        local o = mis_addr + i * OBJ
        if mis_addr ~= 0 and sp:read_u8(o) == 1
                and sp:read_u8(o + 1) == KIND_MISSILE then
            local rect, maxslot = nil, S.MIS_FRONT_SPRITE + i * COLS_MAX + COLS_MAX - 1
            for c = 0, COLS_MAX - 1 do
                local s = S.MIS_FRONT_SPRITE + i * COLS_MAX + c
                rect = union(rect, slot_rect(s))
            end
            if rect and on_screen(rect) then
                local covered = false
                for s = maxslot + 1, 380 do
                    local r = slot_rect(s)
                    if r and on_screen(r) and intersects(rect, r) then
                        covered = true
                        break
                    end
                end
                if not covered then
                    best = i
                end
            end
        end
    end
    return best
end

local function lspc_counter()
    -- REG_LSPCMODE bits 2-0: the LSPC's 3-bit auto-animation counter.
    return sp:read_u16(0x3c0006)
end

local function dump_frame()
    local records = {}
    for _, s in ipairs(slots) do
        local scb2 = vread(0x8000 + s)
        local scb3 = vread(0x8200 + s)
        local scb4 = vread(0x8400 + s)
        if (scb3 & 0x3f) ~= 0 then               -- height 0: not drawn
            local line = string.format("S %d %04x %04x %04x", s, scb2, scb3, scb4)
            local t = {}
            for r = 0, 31 do
                t[r + 1] = vread(s * 64 + r * 2)
                line = line .. string.format(" %04x", t[r + 1])
            end
            for r = 0, 31 do
                line = line .. string.format(" %04x", vread(s * 64 + r * 2 + 1))
            end
            records[#records + 1] = line
        end
    end
    f:write(string.format("F %d %04x\n", n, lspc_counter()))
    for _, line in ipairs(records) do f:write(line .. "\n") end
    -- Task S3: the ship's slots at this sampled frame, for the snapshot's
    -- ship-palette pixel mask (the bolt shares PAL_SHIP with the ship).
    -- H <n> <scb3_0> <scb2_0> <scb2_1> <scb4_0> <t00> <t01> <t10> <t11>
    local ship = S.SHIP_SPRITE
    f:write(string.format("H %d %04x %04x %04x %04x %04x %04x %04x %04x\n", n,
                          vread(0x8200 + ship), vread(0x8000 + ship),
                          vread(0x8000 + ship + 1), vread(0x8400 + ship),
                          vread(ship * 64), vread(ship * 64 + 2),
                          vread((ship + 1) * 64), vread((ship + 1) * 64 + 2)))
    -- Task H2: first frame that shows a bolt (its SCB1 row 0 tile is in
    -- SHIP_BOLT_TILE .. +64): also snapshot it
    if not snapped and n >= 600 then
        for _, line in ipairs(records) do
            local tile = tonumber(line:match("S %d+ %x+ %x+ %x+ (%x+)"), 16)
            if tile and BOLT0 > 0 and NBOLT > 0
                    and tile >= BOLT0 and tile < BOLT0 + NBOLT then
                machine.video:snapshot()
                f:write(string.format("SNAP %d %d\n", n, snap_seq))
                snap_seq = snap_seq + 1
                snapped = true
                break
            end
        end
    end

    -- R2: the rockets flicker on the LSPC's global counter, so take two
    -- snapshots of the same missile (a lone front missile, unobscured) 8+
    -- frames apart and record the counter each time. Up to a few pairs, so
    -- the checker can pick one whose flame actually changes between frames.
    if snapped and rocket_pairs < 3 then
        if rocket_pending then
            local p = rocket_pending
            local i = front_missile()
            if i == p.obj and n > p.frame then
                local c = lspc_counter()
                machine.video:snapshot()
                f:write(string.format("RPAIR %d %d %d %d %04x %04x %d\n",
                                      p.seq, snap_seq, p.frame, n,
                                      p.counter, c, p.obj))
                snap_seq = snap_seq + 1
                rocket_pairs = rocket_pairs + 1
                rocket_pending = nil
            else
                rocket_pending = nil              -- orphan first snapshot
            end
        end
        if not rocket_pending then
            local i = front_missile()
            if i then
                local c = lspc_counter()
                machine.video:snapshot()
                f:write(string.format("RSNAP %d %d %04x %d\n",
                                      snap_seq, n, c, i))
                rocket_pending = { seq = snap_seq, frame = n,
                                   counter = c, obj = i }
                snap_seq = snap_seq + 1
            end
        end
    end
end

-- Task H2: the two bullet objects and the bullet base slots' words every
-- frame, so the checker can hold the displayed SCB words to the bolt model
-- and the shimmer to (fc + slot) & 1.
-- B <n> <fc> <da> then per bullet i=0,1:
--   <i> <state> <ring> <phi> <r> <behind scb2/3/4/tile> <front scb2/3/4/tile>
local function dump_bullets()
    local da = ship_addr ~= 0 and sp:read_u8(ship_addr) or 0
    local fc = framecnt_addr ~= 0 and sp:read_u32(framecnt_addr) or 0
    local line = string.format("B %d %d %d", n, fc, da)
    for i = 0, NBUL - 1 do
        local o = mis_addr + (BUL0 + i) * OBJ
        local state = mis_addr ~= 0 and sp:read_u8(o) or 0
        local ring = mis_addr ~= 0 and sp:read_u8(o + 2) or 0
        local phi = mis_addr ~= 0 and sp:read_u8(o + 3) or 0
        local r = mis_addr ~= 0 and sp:read_u32(o + 6) or 0
        local b2, b3, b4, bt = slot_words(S.MIS_BEHIND_SPRITE + (BUL0 + i) * COLS_MAX)
        local f2, f3, f4, ft = slot_words(S.MIS_FRONT_SPRITE + (BUL0 + i) * COLS_MAX)
        line = line .. string.format(" %d %d %d %d %d %04x %04x %04x %04x %04x %04x %04x %04x",
                                     i, state, ring, phi, r, b2, b3, b4, bt, f2, f3, f4, ft)
    end
    f:write(line .. "\n")
end

-- R2: every missile object's state and flight parameters every frame, so
-- the checker can hold the displayed missile SCB1 words (tile + 4-frame
-- animation attribute) and SCB2/3/4 to the old dart placement model.
-- M <n> <da> then per missile i=0,1,2: <i> <state> <kind> <ring> <phi> <r>
local function dump_missiles()
    local da = ship_addr ~= 0 and sp:read_u8(ship_addr) or 0
    local line = string.format("M %d %d", n, da)
    for i = 0, NMIS - 1 do
        local o = mis_addr + i * OBJ
        local state = mis_addr ~= 0 and sp:read_u8(o) or 0
        local kind = mis_addr ~= 0 and sp:read_u8(o + 1) or 0
        local ring = mis_addr ~= 0 and sp:read_u8(o + 2) or 0
        local phi = mis_addr ~= 0 and sp:read_u8(o + 3) or 0
        local r = mis_addr ~= 0 and sp:read_u32(o + 6) or 0
        line = line .. string.format(" %d %d %d %d %d %d",
                                     i, state, kind, ring, phi, r)
    end
    f:write(line .. "\n")
end

local function tick()
    n = n + 1
    SG.sg_apply(n)
    if cpu.state["PC"].value < 0x100000 then
        in_cart = 1
        if not planted and n >= plant_at then
            plant()
            planted = true
        end
        if n >= 600 then
            if (n - 600) % fire_every == 0 then
                joy.fields["P1 A"]:set_value(1)
            else
                joy.fields["P1 A"]:set_value(0)
            end
            -- Task H2 Review Focus 1: turn the dome after the first shot so
            -- a bolt in flight is seen across a dome turn
            joy.fields["P1 Right"]:set_value((n >= 615 and n <= 635) and 1 or 0)
        end
        if n >= 600 and (n - 600) % sample_every == 0 then
            dump_frame()
        end
        -- start a frame early: the first sample (600) reads frame 599's
        -- prepared words, which the checker needs
        if n >= 598 then
            dump_bullets()
            dump_missiles()
        end
    end
    if n == frames then
        f:write(string.format("pc_in_cart=%d frames=%d snapped=%d\n", in_cart, n, snapped and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__leftover = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
