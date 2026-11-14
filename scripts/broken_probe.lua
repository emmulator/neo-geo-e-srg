-- broken_probe.lua: for the M4-fixes Task 3 broken-tiles boot-test.
--
-- Boots the -DCRACK_TEST cart (which starts with all 38 broken cells; the
-- main loop parks the ship on cell 27 every frame, so the dome never
-- rotates by itself). Runs FRAMES frames. On sampled frames it reads back
-- every shown overlay slot (BROKEN_SLOT_BASE..BROKEN_SLOT_AFTER-1):
-- SCB2/3/4, the attribute word, and the SCB1 tile rows 0..15 of the
-- column (a stone per row; the picture is h rows x w columns, full size).
-- Output per sampled frame:
--     F <frame> <dome_angle>
--     S <slot> <scb2> <scb3> <scb4> <attr> <tile0> ... <tile15>
-- It snapshots the first sampled frame where a FRONT missile's on-screen
-- box overlaps a broken overlay's box (the draw-order proof needs the
-- missile's pixels over a broken cell's black hole). The overlap is
-- detected from the very VRAM reads above (each overlay slot is a 16-px
-- stone column; each front missile is an object's 1..4 slot columns), so
-- the snapshot tracks the real flight, whichever frame that is. The first
-- landing (which breaks a WHOLE cell beyond the fixed 38) happens at
-- cart fc 752, so the overlap happens before the scene changes; the probe
-- exits at FRAMES even if no overlap fired. tests/check_broken.py checks
-- the reads and the snapshot.
--
-- Permutation coverage (the task's proof 2 needs a dome_angle >= 48): the
-- probe sets src/cracks.c's test-only BSS override `cracks_test_angle`
-- (address CRACK_ANGLE_ADDR, from the crack-test ELF) to CRACK_ANGLE each
-- sampled frame; cracks_show then uses that angle for its view and 5-fold
-- permutation. The dome picture itself stays at view 0 (the test cart
-- parks the ship without rotating), and check_broken.py builds the
-- expected picture from exactly what the cart draws: the view-0 dome plus
-- the overlays at CRACK_ANGLE's permutation — so a run with
-- CRACK_ANGLE >= 48 exercises the permutation's tile numbers and canvas
-- offsets on screen. CRACK_ANGLE 0 (default) = no override (the real
-- dome_angle 0).
--
-- Env: FRAMES (1500), BROKEN_SAMPLE_EVERY (8), OUT, HUD_FRAMECNT_ADDR
-- (the cart's BSS frame counter; the probe samples only once the cart's
-- main loop is running, so the BIOS preamble's sprites are never read),
-- CRACK_ANGLE (0), CRACK_ANGLE_ADDR (0 = none).
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local frames = tonumber(os.getenv("FRAMES") or "1500")
local sample_every = tonumber(os.getenv("BROKEN_SAMPLE_EVERY") or "8")
local fc_addr = tonumber(os.getenv("HUD_FRAMECNT_ADDR") or "0")
local out = os.getenv("OUT")
local angle = tonumber(os.getenv("CRACK_ANGLE") or "0")
local angle_addr = tonumber(os.getenv("CRACK_ANGLE_ADDR") or "0")
local rules_addr = tonumber(os.getenv("CRACK_RULES_ADDR") or "0")
-- dome-scenery Task 12: the props follow the CAMERA (ship.dome_angle, the
-- first byte of the ship struct), not cracks_show's test-only overlay
-- override. The checker needs both to composite the picture: `F`'s da is
-- the overlays' angle, `P`'s is the props'/dome's. SHIP_ADDR is the cart
-- BSS `ship`'s address (from the crack-test ELF); 0 = not dumped.
local ship_addr = tonumber(os.getenv("SHIP_ADDR") or "0")

-- the one sprite slot map (M5 Task 1): src/slots.h -> build/slots.lua
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local MIS_BEHIND, MIS_BEHIND_END = S.MIS_BEHIND_SPRITE,
    S.MIS_BEHIND_SPRITE + S.MIS_BEHIND_COUNT - 1
local DOME, DOME_END = S.DOME_SPRITE, S.DOME_SPRITE + S.DOME_COUNT - 1
local BROKEN, BROKEN_END = S.BROKEN_SLOT_BASE, S.BROKEN_SLOT_AFTER - 1
local SHIP, SHIP_END = S.SHIP_SPRITE, S.SHIP_SPRITE + S.SHIP_COUNT - 1
local FRONT, FRONT_END = S.MIS_FRONT_SPRITE,
    S.MIS_FRONT_SPRITE + S.MIS_FRONT_COUNT - 1
local EXPL, EXPL_END = S.EXPL_SPRITE, S.EXPL_SPRITE + S.EXPL_COUNT - 1
-- dome-scenery Task 5: the ground block is the lowest sprite range and
-- draws behind everything. The snapshot's pixel-exact compare needs its
-- tiles too (its picture is the band below the horizon, in the dome box's
-- lower rows).
local GROUND, GROUND_END = S.GROUND_SPRITE, S.GROUND_SPRITE + S.GROUND_COUNT - 1

-- VRAM is read (and, by the leftover probe, written) through MAME's own copy
-- of it, never through the LSPC registers at 0x3c0000/2: writing the address
-- register from a frame callback changes the cart's VRAM pointer under it, and
-- the cart's next writes land at the probe's address (it zeroed title rows).
local vram = emu.item(manager.machine.devices[":spritegen"].items["0/m_videoram"])
local function vread(addr)
    return vram:read(addr)
end

local n, in_cart, done = 0, 0, false
local f = assert(io.open(out, "w"))
-- the cart now boots to a title: this helper presses Start to begin a game
-- (M6 Task 1). The broken probe gates its samples on framecnt() > 0, which
-- is only true once the game (not the title) is running, so the title is
-- never sampled; it only needs the Start press from this helper.
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")

local function framecnt()
    if fc_addr ~= 0 then
        return sp:read_u32(fc_addr)
    end
    return n
end

-- boxes of the shown slots in a group: for overlays each slot is one
-- 16-px-wide stone column; for missiles an object owns 1..4 consecutive
-- slots. Returns a list of {x0, y0, x1, y1}.
local function boxes(begin_, end_)
    local out_boxes = {}
    for s = begin_, end_ do
        local scb3 = vread(0x8200 + s)
        local h = scb3 & 0x3f
        if h ~= 0 then
            local x = vread(0x8400 + s) >> 7
            local y = 496 - (scb3 >> 7)
            out_boxes[#out_boxes + 1] = { x, y, x + 15, y + h * 16 - 1 }
        end
    end
    return out_boxes
end

local function overlaps(ob, sb)
    for _, b in ipairs(ob) do
        for _, m in ipairs(sb) do
            -- b, m = {x0, y0, x1, y1}
            if not (b[1] > m[3] or m[1] > b[3] or b[2] > m[4] or m[2] > b[4]) then
                return true
            end
        end
    end
    return false
end

local function dump()
    -- the effective dome_angle the overlays used this frame (the override,
    -- if the probe set one; otherwise the cart's own, which the test cart
    -- keeps at 0)
    local da = angle
    if angle_addr ~= 0 then
        sp:write_u8(angle_addr, angle == 0 and 0xff or angle)
    end
    local had = false
    local function read_group(begin_, end_, always)
        for s = begin_, end_ do
            local scb3 = vread(0x8200 + s)
            if always or (scb3 & 0x3f) ~= 0 then
                had = true
                local line = string.format("S %d %04x %04x %04x %04x",
                                           s, vread(0x8000 + s), scb3,
                                           vread(0x8400 + s), vread(s * 64 + 1))
                for r = 0, 15 do
                    line = line .. string.format(" %04x", vread(s * 64 + r * 2))
                end
                f:write(line .. "\n")
            end
        end
    end
    f:write(string.format("F %d %d\n", n, da))
    if ship_addr ~= 0 then
        f:write(string.format("P %d %d\n", n, sp:read_u8(ship_addr)))
    end
    if rules_addr ~= 0 then
        local nb = sp:read_u8(rules_addr + 77)
        local b0 = sp:read_u8(rules_addr + 1)
        local b1 = sp:read_u8(rules_addr + 2)
        local dt = sp:read_u8(rules_addr + 80)
        local dd = sp:read_u8(rules_addr + 81)
        local go = sp:read_u8(rules_addr + 82)
        f:write(string.format("R %d %d %d %d %d %d %d\n", framecnt(),
                              nb, b0, b1, dt, dd, go))
    end
    read_group(MIS_BEHIND, MIS_BEHIND_END, false)   -- missiles behind the dome
    read_group(GROUND, GROUND_END, true)             -- dome-scenery Task 5:
                                                     -- the grass (the lowest
                                                     -- sprite range; its
                                                     -- sticky chain needs
                                                     -- all columns dumped)
    read_group(DOME, DOME_END, true)                 -- the dome box (all
                                                     -- columns; the sticky
                                                     -- followers have SCB3
                                                     -- height 0 but their
                                                     -- SCB1 rows are the
                                                     -- picture)
    read_group(BROKEN, BROKEN_END, false)            -- the broken overlays
    read_group(SHIP, SHIP_END, true)                 -- the ship (sticky chain)
    read_group(FRONT, FRONT_END, false)              -- front missiles
    read_group(EXPL, EXPL_END, false)                -- explosions
    return had
end

local function front_missile_over_broken()
    return overlaps(boxes(BROKEN, BROKEN_END), boxes(FRONT, FRONT_END))
end

local function tick()
    n = n + 1
    SG.sg_apply(n)
    if cpu.state["PC"].value >= 0x100000 then in_cart = 1 end
    -- sample only after the cart's main loop has run (framecnt > 0)
    if in_cart and framecnt() > 0 and n >= 120 and (n - 120) % sample_every == 0 then
        local had_slots = dump()
        -- snapshot the first sampled frame where a front missile is drawn
        -- over a broken overlay (the draw-order proof). The first missile
        -- launches ~fc 60; its flight crosses the broken top cells before
        -- the first landing (~fc 752), so this fires well before the
        -- scene changes.
        if not done and had_slots and front_missile_over_broken() then
            machine.video:snapshot()
            f:write(string.format("SNAP %d fc=%d\n", n, framecnt()))
            done = true
        end
    end
    if n == frames then
        f:write(string.format("pc_in_cart=%d frames=%d snap=%d\n", in_cart, n,
                              done and 1 or 0))
        f:close()
        machine:exit()
    end
end

if emu.add_machine_frame_notifier then
    _G.__broken = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
