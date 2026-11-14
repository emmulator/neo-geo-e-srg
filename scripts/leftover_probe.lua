-- leftover_probe.lua: for the M3 "no leftovers below a shrunk sprite" fix.
--
-- Plays to frame FRAMES. Once, before the first missile appears (frame
-- LEFT_PLANT_AT), it plants a visible, non-blank tile into SCB1 rows 0..31 of
-- every missile/bullet/explosion slot, so that any row
-- the game does not overwrite is loud garbage instead of a lucky blank.
-- From frame 600 it fires A every LEFT_FIRE_EVERY frames, so bullets (always
-- drawn shrunk to half size) and missiles at several sizes are on screen.
--
-- On many frames it reads SCB2/SCB3/SCB4 and the 32 SCB1 rows of every shown
-- slot, and writes:
--     F <frame>
--     S <slot> <scb2> <scb3> <scb4> <attr0> <tile0> ... <tile31>
-- The first frame that shows a bullet (palette 4) is snapshotted and marked
-- with "SNAP <frame>" right after its frame block; tests/check_leftovers.py
-- checks the written rows and the snapshot pixels.
--
-- Env: FRAMES (1500), LEFT_PLANT_AT (520), LEFT_FIRE_EVERY (20),
--      LEFT_SAMPLE_EVERY (8), OUT (the probe dump).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local frames = tonumber(os.getenv("FRAMES") or "1500")
local plant_at = tonumber(os.getenv("LEFT_PLANT_AT") or "520")
local fire_every = tonumber(os.getenv("LEFT_FIRE_EVERY") or "20")
local sample_every = tonumber(os.getenv("LEFT_SAMPLE_EVERY") or "8")
local out = os.getenv("OUT")

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")

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
local f = assert(io.open(out, "w"))
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1). The leftover probe's planting and fire keys are absolute MAME
-- frames, unchanged — the game begins just after the Start here, so a
-- bullet is still on screen by the first post-title sample.
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local function dump_frame()
    local records = {}
    for _, s in ipairs(slots) do
        local scb2 = vread(0x8000 + s)
        local scb3 = vread(0x8200 + s)
        local scb4 = vread(0x8400 + s)
        if (scb3 & 0x3f) ~= 0 then               -- height 0: not drawn
            local line = string.format("S %d %04x %04x %04x %04x", s, scb2, scb3, scb4,
                                       vread(s * 64 + 1))   -- attr of row 0
            for r = 0, 31 do
                line = line .. string.format(" %04x", vread(s * 64 + r * 2))
            end
            records[#records + 1] = line
        end
    end
    f:write(string.format("F %d\n", n))
    for _, line in ipairs(records) do f:write(line .. "\n") end
    -- first frame that shows a bullet (palette 4): also snapshot it
    if not snapped and n >= 600 then
        for _, line in ipairs(records) do
            local attr = tonumber(line:match("S %d+ %x+ %x+ %x+ (%x+)"), 16)
            if attr and (attr >> 8) == 4 then
                machine.video:snapshot()
                f:write(string.format("SNAP %d\n", n))
                snapped = true
                break
            end
        end
    end
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
        end
        if n >= 600 and (n - 600) % sample_every == 0 then
            dump_frame()
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
