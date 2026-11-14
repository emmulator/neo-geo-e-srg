-- tear_probe.lua (the orchestrator's diagnosis, 10-25; plan Tasks 18 and 18b
-- build their leg from it):
-- VRAM writes land while the raster is inside the sprite they change?
--
-- Taps the LSPC registers (0x3c0000 address, 0x3c0002 data, 0x3c0004 modulo)
-- to follow the cart's VRAM pointer, and for every data write to ANY sprite
-- slot (SCB1 tiles, SCB2, SCB3, SCB4) records the raster line at that moment
-- (LSPCMODE's line counter, as src/flow.c lspc_vpos). Every frame it also
-- records each shown slot's on-screen line span (from VRAM at the frame's
-- end), and it taps palette RAM writes for the radar's blink entry.
--
-- TEAR_DRIVE picks the input:
--   spin — the props leg's spin: walk to the peak, turn the dome left through
--          a whole turn, then right back to 0 (Task 18's drive).
--   fire — the collapse leg's centred policy: stick centred, A every 11 cart
--          frames (Task 18b's drive: missiles land, the radar locks and
--          blinks, explosions play). The normal cart never aims a missile at
--          the resting ship's cell (outside the spawn rings), so the probe
--          forces the first missile there at a visible range, exactly as the
--          RADAR_TEST cart's hook does (see force_first_missile).
--   title — attract Task A2: the cart is left on the title for 600 frames
--          (logged from MAME frame 41 to 640). It checks the scene's vblank
--          writes and every title fix write (the F records).
--
--   W <fc> <da> <slot> <reg> <vpos>      a slot write (reg 1..4 = SCB1..4)
--   S <fc> <da> <slot> <top> <bottom>    a shown slot's span (screen lines)
--   C <fc> <start> <commit>              the frame's work-start and the last
--                                        commit's end (vpos; the FRAME_MARK
--                                        cart's marks)
--   P <fc> <vpos> <word>                 a write to palette RAM's radar blink
--                                        entry (bank 20, entry 1)
--   F <tick> <col> <row> <vpos>        a fix-layer write (ADDR_FIXMAP)
--   TEAR_DRIVE <spin|fire|title>
local machine = manager.machine
local cpu = machine.devices[":maincpu"]
local sp = cpu.spaces["program"]
local out = os.getenv("OUT")
local run_len = tonumber(os.getenv("FRAMES") or "1600")
local drive_mode = os.getenv("TEAR_DRIVE") or "spin"
local title_drive = drive_mode == "title"
local framecnt_addr = tonumber(os.getenv("PROPS_FRAMECNT_ADDR") or "0")
local ship_addr = tonumber(os.getenv("PROPS_SHIP_ADDR") or "0")
local start_addr = tonumber(os.getenv("START_ADDR") or "0")
local commit_addr = tonumber(os.getenv("COMMIT_ADDR") or "0")
-- the fire drive's RADAR_TEST-style poke (see force_first_missile below):
-- the static `mis`, and the missile tables' const arrays in ROM
local mis_addr = tonumber(os.getenv("MIS_ADDR") or "0")
local r_spawn_addr = tonumber(os.getenv("MIS_R_SPAWN_ADDR") or "0")
local cell_ring_addr = tonumber(os.getenv("MIS_CELL_RING_ADDR") or "0")
local cell_phi_addr = tonumber(os.getenv("MIS_CELL_PHI_ADDR") or "0")
local S = dofile((os.getenv("REPO") or ".") .. "/build/slots.lua")
local vram = emu.item(machine.devices[":spritegen"].items["0/m_videoram"])
local joy = machine.ioport.ports[":ctrl1:joy:JOY"]
local SG = dofile((os.getenv("REPO") or ".") .. "/scripts/start_game.lua")
local f = assert(io.open(out, "w"))

f:write(string.format("TEAR_DRIVE %s\n", drive_mode))

-- Task 18b: palette RAM's radar blink entry, MMAP_PALBANK1[20 * 16 + 1]
-- (src/radar_gfx.h RADAR_PAL_BANK). Palette RAM starts at 0x400000, one u16
-- per entry: 0x400000 + (20 * 16 + 1) * 2.
local RADAR_PAL_ENTRY = 0x400000 + (20 * 16 + 1) * 2

local cur, mod = 0, 1
local n, in_cart = 0, false
local fc_now, da_now, tick_now = 0, 0, 0
-- the title drive logs only once the title has settled (MAME frame 40 on),
-- so the boot fix_clear / scene entry writes are not counted; 600 title
-- frames then run to frame 640.
local LOG_FROM = 40
local function logging()
    return in_cart and (fc_now > 0 or (title_drive and n >= LOG_FROM))
end
local function vpos()
    -- src/flow.c lspc_vpos: ((LSPCMODE >> 7) & 0x1ff) - 0x100
    local v = ((sp:read_u16(0x3c0006) >> 7) & 0x1ff) - 0x100
    return v
end
local function on_write(offset, data, mask)
    local reg = offset & 0x6
    if reg == 0 then
        cur = data
    elseif reg == 4 then
        mod = data
    elseif reg == 2 then
        local a = cur
        local kind, slot = 0, -1
        if a < 0x7000 then kind, slot = 1, a // 64
        elseif a >= 0x8000 and a < 0x8200 then kind, slot = 2, a - 0x8000
        elseif a >= 0x8200 and a < 0x8400 then kind, slot = 3, a - 0x8200
        elseif a >= 0x8400 and a < 0x8600 then kind, slot = 4, a - 0x8400 end
        if kind > 0 and logging() then
            f:write(string.format("W %d %d %d %d %d\n", tick_now, da_now, slot, kind, vpos()))
        elseif a >= 0x7000 and a < 0x7500 and logging() then
            local d = a - 0x7000
            f:write(string.format("F %d %d %d %d\n", tick_now, d // 32,
                                  d % 32, vpos()))
        end
        -- the LSPC's auto-increment, within the zone (as the hardware)
        if a >= 0x8000 then
            cur = 0x8000 + ((a - 0x8000 + mod) & 0x7ff)
        else
            cur = (a + mod) & 0x7fff
        end
    end
    return data
end
_G.__tap = sp:install_write_tap(0x3c0000, 0x3c0005, "lspc", on_write)

local function on_pal_write(offset, data, mask)
    if offset == RADAR_PAL_ENTRY and logging() then
        f:write(string.format("P %d %d %04x\n", tick_now, vpos(), data))
    end
    return data
end
_G.__paltap = sp:install_write_tap(0x400000, 0x401fff, "pal", on_pal_write)

local reached239, done_right = false, false

-- Task 18b's fire drive: the normal cart's centred policy never targets the
-- resting ship's cell (cell 27 is outside the missile spawn rings), so no
-- missile ever locks or is hit within 3000 frames. Force the first missile of
-- the game to the start cell at a visible range, and clear the bullets already
-- in flight, so the radar locks/blinks for more than one blink period and the
-- fresh shot's hit plays a visible explosion. This is a test-only input, the
-- same kind as the RADAR_TEST cart's hook (src/flow.c radar_test_spawn).
local OBJ = 14                  -- mis_obj_t's byte size on m68k
local radar_test_done = false
local function force_first_missile()
    if radar_test_done or mis_addr == 0 or r_spawn_addr == 0
        or cell_ring_addr == 0 or cell_phi_addr == 0 then
        return
    end
    for i = 0, 2 do
        local o = mis_addr + i * OBJ
        if sp:read_u8(o) == 1 and sp:read_u8(o + 1) == 0 then     -- a flying missile
            local ring = sp:read_u8(o + 2)
            if sp:read_u32(o + 6) == sp:read_u32(r_spawn_addr + ring * 4) then
                local nr = sp:read_u8(cell_ring_addr + 27)
                local np = sp:read_u8(cell_phi_addr + 27)
                sp:write_u8(o + 2, nr)
                sp:write_u8(o + 3, np)
                -- a visible range, not the ring's spawn range: the spawn
                -- range is off-screen (and its hit's explosion is culled),
                -- so this makes the hit's explosion actually play
                sp:write_u32(o + 6, 900000)
                -- clear the bullets already in flight: otherwise one that
                -- is already past the missile hits it next frame, before the
                -- radar's 5-frame blink can happen; a fresh shot hits later
                for j = 3, 4 do
                    sp:write_u8(mis_addr + j * OBJ, 0)
                end
                radar_test_done = true
                return
            end
        end
    end
end
local function da() return ship_addr ~= 0 and sp:read_u8(ship_addr) or 0 end
local function cell() return ship_addr ~= 0 and sp:read_u8(ship_addr + 2) or 27 end
local function release_dirs()
    joy.fields["P1 Up"]:set_value(0)
    joy.fields["P1 Left"]:set_value(0)
    joy.fields["P1 Right"]:set_value(0)
    joy.fields["P1 Down"]:set_value(0)
end
local function drive(fc)
    if title_drive then
        release_dirs()
        joy.fields["P1 A"]:set_value(0)
        return
    end
    if not SG.game_started(fc) then return end
    if drive_mode == "fire" then
        -- the collapse leg's centred policy: the ship rests on the start
        -- cell (27), A (fire) every 11 cart frames. At 3000 MAME frames that
        -- is far short of the collapse leg's game over, so the taps keep
        -- going for the whole run.
        release_dirs()
        joy.fields["P1 A"]:set_value((fc % 11) == 0 and 1 or 0)
        return
    end
    local up, left, right = 0, 0, 0
    if cell() ~= 0 then up = 1
    elseif not reached239 then
        if da() == 239 then reached239 = true; right = 1 else left = 1 end
    elseif not done_right then
        if da() == 0 then done_right = true else right = 1 end
    end
    release_dirs()
    joy.fields["P1 Up"]:set_value(up)
    joy.fields["P1 Left"]:set_value(left)
    joy.fields["P1 Right"]:set_value(right)
    joy.fields["P1 A"]:set_value(0)
end

local function tick()
    n = n + 1
    if not in_cart and cpu.state["PC"].value >= 0x100000 then in_cart = true end
    SG.sg_apply(n)
    if in_cart then
        local fc = framecnt_addr ~= 0 and sp:read_u32(framecnt_addr) or 0
        -- the spans of the frame that just ran
        if fc > 0 or (title_drive and n >= LOG_FROM) then
            for s = 1, 380 do
                local w2, w3 = vram:read(0x8000 + s), vram:read(0x8200 + s)
                local h = w3 & 0x3f
                if h > 0 then
                    local top = (496 - (w3 >> 7)) & 0x1ff
                    if top >= 256 then top = top - 512 end
                    local lines = (h * 16 * ((w2 & 0xff) + 1)) // 256
                    f:write(string.format("S %d %d %d %d %d\n", n, da_now, s, top, top + lines - 1))
                end
            end
            -- the FRAME_MARK cart's work-start and the last commit's end
            -- for this frame (the W records of this frame use tick n too)
            if start_addr ~= 0 and commit_addr ~= 0 then
                f:write(string.format("C %d %d %d\n", n,
                                      sp:read_u16(start_addr),
                                      sp:read_u16(commit_addr)))
            end
        end
        fc_now, da_now, tick_now = fc, da(), n + 1
        drive(fc)
        if drive_mode == "fire" and SG.game_started(fc) then
            force_first_missile()
        end
    end
    if n >= run_len then
        machine.video:snapshot()
        f:write(string.format("pc_in_cart=%d frames=%d\n", in_cart and 1 or 0, n))
        f:close()
        machine:exit()
    end
end
if emu.add_machine_frame_notifier then
    _G.__props = emu.add_machine_frame_notifier(tick)
else
    emu.register_frame(tick)
end
